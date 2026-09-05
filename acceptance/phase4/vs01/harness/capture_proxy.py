"""Gate-owned HTTP capture proxy for externally driven VS01 evidence.

The external scenario driver is intentionally given only :attr:`origin` and its
own output path.  It receives unpredictable capture receipts in HTTP response
headers, while the corresponding response bytes and metadata remain in this
process's private, in-memory ledger.  A driver can therefore name an observation,
but cannot author the observation that the acceptance gate evaluates.

This is acceptance infrastructure.  It neither imports Product code nor creates
business responses.  Every eligible response is streamed from one fixed upstream
origin, without following redirects.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import re
import secrets
import socket
import ssl
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import quote, unquote, urlsplit

CAPTURE_ID_HEADER = "X-VS01-Capture-ID"
CAPTURE_SESSION_HEADER = "X-VS01-Capture-Session"
SSE_FRAME_CUTOFF_HEADER = "X-VS01-Capture-Cut-After-Complete-Frames"
MAX_SSE_FRAME_CUTOFF = 10_000
DEFAULT_MAX_REQUEST_BYTES = 8 * 1024 * 1024
DEFAULT_MAX_RESPONSE_BYTES = 32 * 1024 * 1024

_CAPTURE_RECEIPT_HEADERS = frozenset({CAPTURE_ID_HEADER.lower(), CAPTURE_SESSION_HEADER.lower()})
_GATE_CONTROL_HEADERS = frozenset({SSE_FRAME_CUTOFF_HEADER.lower()})
_SENSITIVE_REQUEST_HEADER_NAME = re.compile(
    r"(?:authorization|cookie|api[-_]?key|secret|password|(?:access|refresh)?[-_]?token)",
    re.IGNORECASE,
)
_STATIC_HOP_BY_HOP_HEADERS = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
)
_VALID_PERCENT_ESCAPE = re.compile(r"%(?P<hex>[0-9A-Fa-f]{2})")
_INVALID_PERCENT_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})")
_EVIDENCE_PATH = re.compile(r"^/api/research-runs/(?P<run>[^/?]+)/(?P<kind>projection|events)$")


class CaptureProxyError(RuntimeError):
    """The proxy cannot establish trustworthy evidence provenance."""


class CaptureVerificationError(CaptureProxyError):
    """Driver capture references do not close against the gate-owned ledger."""


class _RequestRejected(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_origin(value: str, *, label: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise CaptureProxyError(f"{label} must be an origin-level absolute HTTP(S) URL")
    try:
        port = parsed.port
    except ValueError as exc:
        raise CaptureProxyError(f"{label} has an invalid port") from exc
    default_port = 443 if parsed.scheme == "https" else 80
    rendered_port = "" if port in {None, default_port} else f":{port}"
    host = parsed.hostname.lower()
    if ":" in host:
        host = f"[{host}]"
    return f"{parsed.scheme.lower()}://{host}{rendered_port}"


def _canonical_target(value: str) -> str:
    if not value or not value.startswith("/") or value.startswith("//"):
        raise _RequestRejected(400, "request target must use origin form")
    if any(
        ord(character) < 0x20 or ord(character) > 0x7E or character == "\\" for character in value
    ):
        raise _RequestRejected(400, "request target contains forbidden characters")
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or parsed.fragment:
        raise _RequestRejected(400, "request target must not name another origin")
    if _INVALID_PERCENT_ESCAPE.search(value):
        raise _RequestRejected(400, "request target contains an invalid percent escape")
    normalized = _VALID_PERCENT_ESCAPE.sub(lambda match: f"%{match.group('hex').upper()}", value)
    for segment in parsed.path.split("/"):
        try:
            decoded = unquote(segment, errors="strict")
        except UnicodeDecodeError as exc:
            raise _RequestRejected(400, "request target is not valid UTF-8") from exc
        if decoded in {".", ".."}:
            raise _RequestRejected(400, "request target contains a dot segment")
    return normalized


def _header_values(headers: Sequence[tuple[str, str]], name: str) -> tuple[str, ...]:
    selected = name.lower()
    return tuple(value for key, value in headers if key.lower() == selected)


def _sensitive_request_header(name: str) -> bool:
    return _SENSITIVE_REQUEST_HEADER_NAME.search(name) is not None


class _SSEFrameBoundaryScanner:
    """Locate complete SSE dispatch boundaries without consuming partial frames.

    The scanner follows the EventSource line-ending rules (LF, CRLF, or CR) and
    mirrors the harness parser's definition of a frame: a block containing at
    least one ``data`` line or comment and terminated by a blank line.  A CR at
    the end of a transport chunk remains pending until the next byte or EOF, so
    CRLF is never miscounted as two line endings.
    """

    def __init__(self, target_frames: int | None = None) -> None:
        self.target_frames = target_frames
        self.complete_frames = 0
        self.last_complete_frame_end: int | None = None
        self._line = bytearray()
        self._pending_cr = False
        self._block_has_data = False
        self._block_has_comment = False
        self._block_has_any_line = False
        self._first_line = True

    def _end_line(self, absolute_end: int) -> bool:
        line = bytes(self._line)
        self._line.clear()
        if self._first_line:
            line = line.removeprefix(b"\xef\xbb\xbf")
            self._first_line = False
        if line:
            self._block_has_any_line = True
            if line.startswith(b":"):
                self._block_has_comment = True
            elif line.partition(b":")[0] == b"data":
                self._block_has_data = True
            return False

        dispatched = self._block_has_data or self._block_has_comment
        self._block_has_data = False
        self._block_has_comment = False
        self._block_has_any_line = False
        if not dispatched:
            return False
        self.complete_frames += 1
        self.last_complete_frame_end = absolute_end
        return self.target_frames is not None and self.complete_frames == self.target_frames

    def feed(self, chunk: bytes, *, absolute_start: int) -> int | None:
        """Return the exact prefix length ending the requested frame, if reached."""

        for index, value in enumerate(chunk):
            if self._pending_cr:
                self._pending_cr = False
                if value == 10:
                    if self._end_line(absolute_start + index + 1):
                        return index + 1
                    continue
                if self._end_line(absolute_start + index):
                    return index
            if value == 13:
                self._pending_cr = True
            elif value == 10:
                if self._end_line(absolute_start + index + 1):
                    return index + 1
            else:
                self._line.append(value)
        return None

    def finish_at_eof(self, *, absolute_end: int) -> None:
        if self._pending_cr:
            self._pending_cr = False
            self._end_line(absolute_end)

    def has_partial_frame(self) -> bool:
        return bool(
            self._pending_cr
            or self._line
            or self._block_has_any_line
            or self._block_has_data
            or self._block_has_comment
        )

    def ends_at_complete_frame(self, *, absolute_end: int) -> bool:
        return self.last_complete_frame_end == absolute_end and not self.has_partial_frame()


def _analyze_complete_sse_prefix(value: bytes) -> tuple[int, bool]:
    scanner = _SSEFrameBoundaryScanner()
    scanner.feed(value, absolute_start=0)
    scanner.finish_at_eof(absolute_end=len(value))
    return scanner.complete_frames, scanner.ends_at_complete_frame(absolute_end=len(value))


@dataclass(frozen=True, slots=True)
class CaptureRecord:
    """One immutable request/response observation owned by the gate process."""

    session_id: str
    capture_id: str
    order: int
    started_at: str
    started_monotonic_ns: int
    completed_at: str
    completed_monotonic_ns: int
    method: str
    canonical_path_query: str
    canonical_proxy_url: str
    canonical_upstream_url: str
    request_headers: tuple[tuple[str, str], ...]
    upstream_request_headers: tuple[tuple[str, str], ...]
    sensitive_request_header_names: tuple[str, ...]
    request_body_length: int
    upstream_status_code: int | None
    upstream_response_headers: tuple[tuple[str, str], ...]
    status_code: int
    response_headers: tuple[tuple[str, str], ...]
    response_body: bytes
    response_sha256: str
    requested_sse_frame_cutoff: int | None
    complete_sse_frames: int
    upstream_complete: bool
    downstream_complete: bool
    truncated: bool
    termination: str
    error: str | None

    def request_header_values(self, name: str) -> tuple[str, ...]:
        return _header_values(self.request_headers, name)

    def response_header_values(self, name: str) -> tuple[str, ...]:
        return _header_values(self.response_headers, name)

    def upstream_request_header_values(self, name: str) -> tuple[str, ...]:
        return _header_values(self.upstream_request_headers, name)

    def upstream_header_values(self, name: str) -> tuple[str, ...]:
        return _header_values(self.upstream_response_headers, name)

    @property
    def complete(self) -> bool:
        return (
            self.upstream_complete
            and self.downstream_complete
            and not self.truncated
            and self.error is None
            and self.upstream_status_code == self.status_code
        )

    @property
    def deliberate_sse_cut(self) -> bool:
        return (
            self.termination == "GATE_SSE_FRAME_CUTOFF"
            and isinstance(self.requested_sse_frame_cutoff, int)
            and self.requested_sse_frame_cutoff > 0
            and self.complete_sse_frames == self.requested_sse_frame_cutoff
            and not self.upstream_complete
            and self.downstream_complete
            and not self.truncated
            and self.error is None
            and self.upstream_status_code == self.status_code
        )


@dataclass(frozen=True, slots=True)
class CaptureSession:
    """Sealed immutable ledger snapshot and its unique trust boundary."""

    session_id: str
    proxy_origin: str
    upstream_origin: str
    created_at: str
    created_monotonic_ns: int
    sealed_at: str
    sealed_monotonic_ns: int
    records: tuple[CaptureRecord, ...]


@dataclass(slots=True)
class _PendingCapture:
    session_id: str
    capture_id: str
    order: int
    started_at: str
    started_monotonic_ns: int
    method: str
    canonical_path_query: str
    canonical_proxy_url: str
    canonical_upstream_url: str
    request_headers: tuple[tuple[str, str], ...]
    sensitive_request_header_names: tuple[str, ...]


class _CaptureLedger:
    def __init__(self, *, session_id: str) -> None:
        self.session_id = session_id
        self._condition = threading.Condition()
        self._accepting = True
        self._sealed = False
        self._next_order = 1
        self._active = 0
        self._records: list[CaptureRecord] = []

    def begin(
        self,
        *,
        method: str,
        target: str,
        proxy_origin: str,
        upstream_origin: str,
        request_headers: tuple[tuple[str, str], ...],
        sensitive_names: tuple[str, ...],
    ) -> _PendingCapture:
        with self._condition:
            if not self._accepting:
                raise CaptureProxyError("capture ledger intake is closed")
            order = self._next_order
            self._next_order += 1
            self._active += 1
        return _PendingCapture(
            session_id=self.session_id,
            capture_id=f"CAP-{secrets.token_hex(24).upper()}",
            order=order,
            started_at=_utc_now(),
            started_monotonic_ns=time.monotonic_ns(),
            method=method,
            canonical_path_query=target,
            canonical_proxy_url=f"{proxy_origin}{target}",
            canonical_upstream_url=f"{upstream_origin}{target}",
            request_headers=request_headers,
            sensitive_request_header_names=sensitive_names,
        )

    def finish(self, pending: _PendingCapture, **values: Any) -> None:
        completed_monotonic_ns = time.monotonic_ns()
        record = CaptureRecord(
            session_id=pending.session_id,
            capture_id=pending.capture_id,
            order=pending.order,
            started_at=pending.started_at,
            started_monotonic_ns=pending.started_monotonic_ns,
            method=pending.method,
            canonical_path_query=pending.canonical_path_query,
            canonical_proxy_url=pending.canonical_proxy_url,
            canonical_upstream_url=pending.canonical_upstream_url,
            request_headers=pending.request_headers,
            sensitive_request_header_names=pending.sensitive_request_header_names,
            completed_at=_utc_now(),
            completed_monotonic_ns=completed_monotonic_ns,
            **values,
        )
        with self._condition:
            if any(item.capture_id == record.capture_id for item in self._records):
                raise CaptureProxyError("capture ID was finalized more than once")
            self._records.append(record)
            self._active -= 1
            self._condition.notify_all()

    def close_intake(self) -> None:
        with self._condition:
            self._accepting = False

    def seal(self, *, timeout_seconds: float) -> tuple[CaptureRecord, ...]:
        deadline = time.monotonic() + timeout_seconds
        with self._condition:
            self._accepting = False
            while self._active:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise CaptureProxyError("capture handlers did not reach a finite cutoff")
                self._condition.wait(remaining)
            self._sealed = True
            return tuple(sorted(self._records, key=lambda item: item.order))


class _FreshThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = False
    daemon_threads = True
    block_on_close = False


class _ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "VS01CaptureProxy"
    sys_version = ""

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return

    def do_GET(self) -> None:  # noqa: N802
        self._proxy_request()

    def do_POST(self) -> None:  # noqa: N802
        self._proxy_request()

    def do_PUT(self) -> None:  # noqa: N802
        self._proxy_request()

    def do_PATCH(self) -> None:  # noqa: N802
        self._proxy_request()

    def do_DELETE(self) -> None:  # noqa: N802
        self._proxy_request()

    def do_HEAD(self) -> None:  # noqa: N802
        self._proxy_request()

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._proxy_request()

    def do_CONNECT(self) -> None:  # noqa: N802
        self.send_error(405, "CONNECT is forbidden")

    @property
    def _proxy(self) -> AuditedCaptureProxy:
        return self.server.capture_proxy  # type: ignore[attr-defined,no-any-return]

    def _send_headers(
        self,
        status_code: int,
        headers: Sequence[tuple[str, str]],
    ) -> None:
        self.send_response_only(status_code)
        for name, value in headers:
            self.send_header(name, value)
        self.end_headers()

    def _safe_error(
        self,
        pending: _PendingCapture,
        *,
        status_code: int,
        message: str,
        request_body_length: int = 0,
        upstream_request_headers: tuple[tuple[str, str], ...] = (),
        upstream_status_code: int | None = None,
        upstream_headers: tuple[tuple[str, str], ...] = (),
        requested_sse_frame_cutoff: int | None = None,
        complete_sse_frames: int = 0,
        termination: str,
    ) -> None:
        body = json.dumps(
            {"error": "VS01_CAPTURE_PROXY_REJECTED", "message": message},
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        headers = (
            ("Content-Type", "application/json; charset=utf-8"),
            ("Content-Length", str(len(body))),
            (CAPTURE_SESSION_HEADER, pending.session_id),
            (CAPTURE_ID_HEADER, pending.capture_id),
            ("Connection", "close"),
        )
        downstream_complete = True
        try:
            self._send_headers(status_code, headers)
            if self.command != "HEAD":
                self.wfile.write(body)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            downstream_complete = False
        self.close_connection = True
        self._proxy._ledger.finish(
            pending,
            request_body_length=request_body_length,
            upstream_request_headers=upstream_request_headers,
            upstream_status_code=upstream_status_code,
            upstream_response_headers=upstream_headers,
            status_code=status_code,
            response_headers=headers,
            response_body=body if self.command != "HEAD" else b"",
            response_sha256=_sha256(body if self.command != "HEAD" else b""),
            requested_sse_frame_cutoff=requested_sse_frame_cutoff,
            complete_sse_frames=complete_sse_frames,
            upstream_complete=False,
            downstream_complete=downstream_complete,
            truncated=False,
            termination=termination,
            error=message,
        )

    def _request_body(self) -> bytes:
        transfer_encoding = self.headers.get("Transfer-Encoding")
        if transfer_encoding is not None:
            raise _RequestRejected(400, "chunked request bodies are forbidden")
        lengths = self.headers.get_all("Content-Length", failobj=[])
        if len(lengths) > 1:
            raise _RequestRejected(400, "ambiguous Content-Length is forbidden")
        if not lengths:
            if self.command in {"POST", "PUT", "PATCH"}:
                raise _RequestRejected(411, "Content-Length is required")
            return b""
        try:
            length = int(lengths[0])
        except (TypeError, ValueError) as exc:
            raise _RequestRejected(400, "Content-Length is invalid") from exc
        if length < 0 or length > self._proxy.max_request_bytes:
            raise _RequestRejected(413, "request body exceeds the gate limit")
        body = self.rfile.read(length)
        if len(body) != length:
            raise _RequestRejected(400, "request body ended before Content-Length")
        return body

    def _requested_sse_frame_cutoff(self) -> int | None:
        values = self.headers.get_all(SSE_FRAME_CUTOFF_HEADER, failobj=[])
        if not values:
            return None
        if len(values) != 1:
            raise _RequestRejected(400, "SSE frame cutoff header must occur exactly once")
        value = values[0].strip()
        if not re.fullmatch(r"[1-9][0-9]{0,4}", value):
            raise _RequestRejected(400, "SSE frame cutoff must be a positive integer")
        cutoff = int(value)
        if cutoff > MAX_SSE_FRAME_CUTOFF:
            raise _RequestRejected(400, "SSE frame cutoff exceeds the gate limit")
        if self.command != "GET":
            raise _RequestRejected(400, "SSE frame cutoff is valid only for GET")
        return cutoff

    def _forward_headers(self) -> tuple[tuple[str, str], ...]:
        raw = tuple((str(name), str(value)) for name, value in self.headers.raw_items())
        connection_tokens = {
            token.strip().lower()
            for value in self.headers.get_all("Connection", failobj=[])
            for token in value.split(",")
            if token.strip()
        }
        forbidden = (
            _STATIC_HOP_BY_HOP_HEADERS
            | connection_tokens
            | {
                "host",
                "accept-encoding",
                "content-length",
                *_CAPTURE_RECEIPT_HEADERS,
                *_GATE_CONTROL_HEADERS,
            }
        )
        return tuple((name, value) for name, value in raw if name.lower() not in forbidden)

    def _upstream_connection(self) -> http.client.HTTPConnection:
        parsed = urlsplit(self._proxy.upstream_origin)
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        if parsed.scheme == "https":
            return http.client.HTTPSConnection(
                parsed.hostname,
                port,
                timeout=self._proxy.upstream_timeout_seconds,
                context=ssl.create_default_context(),
            )
        return http.client.HTTPConnection(
            parsed.hostname,
            port,
            timeout=self._proxy.upstream_timeout_seconds,
        )

    def _proxy_request(self) -> None:
        try:
            target = _canonical_target(self.path)
        except _RequestRejected as exc:
            self.send_error(exc.status_code, exc.message)
            return
        raw_request_headers = tuple(
            (str(name), str(value)) for name, value in self.headers.raw_items()
        )
        spoofed = {name.lower() for name, _ in raw_request_headers} & _CAPTURE_RECEIPT_HEADERS
        if spoofed:
            self.send_error(400, "capture receipt headers are gate-owned")
            return
        retained_request_headers = tuple(
            (name, value)
            for name, value in raw_request_headers
            if not _sensitive_request_header(name)
        )
        sensitive_names = tuple(
            sorted(
                {name.lower() for name, _ in raw_request_headers if _sensitive_request_header(name)}
            )
        )
        try:
            pending = self._proxy._ledger.begin(
                method=self.command.upper(),
                target=target,
                proxy_origin=self._proxy.origin,
                upstream_origin=self._proxy.upstream_origin,
                request_headers=retained_request_headers,
                sensitive_names=sensitive_names,
            )
        except CaptureProxyError:
            self.send_error(503, "capture session is sealed")
            return

        body = b""
        connection: http.client.HTTPConnection | None = None
        response: http.client.HTTPResponse | None = None
        upstream_request_headers: tuple[tuple[str, str], ...] = ()
        upstream_headers: tuple[tuple[str, str], ...] = ()
        downstream_headers: tuple[tuple[str, str], ...] = ()
        captured = bytearray()
        response_started = False
        requested_sse_frame_cutoff: int | None = None
        sse_scanner: _SSEFrameBoundaryScanner | None = None
        try:
            requested_sse_frame_cutoff = self._requested_sse_frame_cutoff()
            body = self._request_body()
            connection = self._upstream_connection()
            self._proxy._register_upstream(connection)
            parsed_upstream = urlsplit(self._proxy.upstream_origin)
            host = parsed_upstream.hostname or ""
            default_port = 443 if parsed_upstream.scheme == "https" else 80
            if parsed_upstream.port not in {None, default_port}:
                host = f"{host}:{parsed_upstream.port}"
            connection.putrequest(
                self.command.upper(),
                target,
                skip_host=True,
                skip_accept_encoding=True,
            )
            forward_headers = self._forward_headers()
            connection.putheader("Host", host)
            connection.putheader("Accept-Encoding", "identity")
            for name, value in forward_headers:
                connection.putheader(name, value)
            length_headers: tuple[tuple[str, str], ...] = ()
            if body:
                connection.putheader("Content-Length", str(len(body)))
                length_headers = (("Content-Length", str(len(body))),)
            elif self.command in {"POST", "PUT", "PATCH"}:
                connection.putheader("Content-Length", "0")
                length_headers = (("Content-Length", "0"),)
            connection.putheader("Connection", "close")
            upstream_request_headers = (
                (("Host", host), ("Accept-Encoding", "identity"))
                + tuple(
                    (name, value)
                    for name, value in forward_headers
                    if not _sensitive_request_header(name)
                )
                + length_headers
                + (("Connection", "close"),)
            )
            connection.endheaders(body if body else None)
            response = connection.getresponse()
            upstream_headers = tuple(
                (str(name), str(value)) for name, value in response.getheaders()
            )
            if response.status in range(300, 400):
                self._safe_error(
                    pending,
                    status_code=502,
                    message="upstream redirects are forbidden",
                    request_body_length=len(body),
                    upstream_request_headers=upstream_request_headers,
                    upstream_status_code=response.status,
                    upstream_headers=upstream_headers,
                    requested_sse_frame_cutoff=requested_sse_frame_cutoff,
                    termination="UPSTREAM_REDIRECT_REJECTED",
                )
                return
            if {name.lower() for name, _ in upstream_headers} & _CAPTURE_RECEIPT_HEADERS:
                self._safe_error(
                    pending,
                    status_code=502,
                    message="upstream attempted to forge capture receipts",
                    request_body_length=len(body),
                    upstream_request_headers=upstream_request_headers,
                    upstream_status_code=response.status,
                    upstream_headers=upstream_headers,
                    requested_sse_frame_cutoff=requested_sse_frame_cutoff,
                    termination="UPSTREAM_RECEIPT_COLLISION",
                )
                return
            if requested_sse_frame_cutoff is not None:
                content_types = _header_values(upstream_headers, "Content-Type")
                content_encodings = _header_values(upstream_headers, "Content-Encoding")
                is_sse = (
                    len(content_types) == 1
                    and content_types[0].partition(";")[0].strip().lower() == "text/event-stream"
                )
                identity_encoded = not content_encodings or (
                    len(content_encodings) == 1
                    and content_encodings[0].strip().lower() == "identity"
                )
                if not is_sse or not identity_encoded:
                    self._safe_error(
                        pending,
                        status_code=502,
                        message="SSE frame cutoff requires an identity-encoded text/event-stream",
                        request_body_length=len(body),
                        upstream_request_headers=upstream_request_headers,
                        upstream_status_code=response.status,
                        upstream_headers=upstream_headers,
                        requested_sse_frame_cutoff=requested_sse_frame_cutoff,
                        termination="SSE_FRAME_CUTOFF_CONTENT_TYPE_REJECTED",
                    )
                    return
                sse_scanner = _SSEFrameBoundaryScanner(requested_sse_frame_cutoff)
            connection_tokens = {
                token.strip().lower()
                for value in _header_values(upstream_headers, "Connection")
                for token in value.split(",")
                if token.strip()
            }
            omitted = (
                _STATIC_HOP_BY_HOP_HEADERS
                | connection_tokens
                | {
                    "content-length",
                    "transfer-encoding",
                }
            )
            downstream_headers = tuple(
                (name, value) for name, value in upstream_headers if name.lower() not in omitted
            ) + (
                (CAPTURE_SESSION_HEADER, pending.session_id),
                (CAPTURE_ID_HEADER, pending.capture_id),
                ("Connection", "close"),
            )
            self._send_headers(response.status, downstream_headers)
            response_started = True
            upstream_complete = False
            downstream_complete = True
            truncated = False
            termination = "UPSTREAM_EOF"
            error: str | None = None
            if self.command != "HEAD":
                while True:
                    remaining = self._proxy.max_response_bytes - len(captured)
                    # ``read`` may wait for the entire requested amount on an
                    # open SSE response. ``read1`` preserves streaming while
                    # retaining the exact decoded HTTP entity bytes.
                    chunk = response.read1(min(64 * 1024, remaining + 1))
                    if not chunk:
                        upstream_complete = True
                        if sse_scanner is not None:
                            sse_scanner.finish_at_eof(absolute_end=len(captured))
                            if sse_scanner.complete_frames < requested_sse_frame_cutoff:
                                truncated = sse_scanner.has_partial_frame()
                                termination = "UPSTREAM_EOF_BEFORE_SSE_FRAME_CUTOFF"
                                error = (
                                    "upstream ended before the requested number of complete "
                                    "SSE frames"
                                )
                            else:
                                termination = "UPSTREAM_EOF_AT_SSE_FRAME_CUTOFF"
                        break
                    if len(chunk) > remaining:
                        chunk = chunk[:remaining]
                        truncated = True
                        termination = "GATE_RESPONSE_BYTE_LIMIT"
                    cutoff_at = (
                        sse_scanner.feed(chunk, absolute_start=len(captured))
                        if sse_scanner is not None
                        else None
                    )
                    if cutoff_at is not None:
                        chunk = chunk[:cutoff_at]
                    captured.extend(chunk)
                    if chunk:
                        try:
                            self.wfile.write(chunk)
                            self.wfile.flush()
                        except (BrokenPipeError, ConnectionResetError, OSError):
                            downstream_complete = False
                            truncated = True
                            termination = "DOWNSTREAM_DISCONNECT"
                            error = "downstream disconnected before response completion"
                            break
                    if cutoff_at is not None:
                        upstream_complete = False
                        downstream_complete = True
                        truncated = False
                        termination = "GATE_SSE_FRAME_CUTOFF"
                        error = None
                        break
                    if truncated:
                        error = "response exceeded the gate byte limit"
                        break
            else:
                upstream_complete = True
            self.close_connection = True
            response_bytes = bytes(captured)
            self._proxy._ledger.finish(
                pending,
                request_body_length=len(body),
                upstream_request_headers=upstream_request_headers,
                upstream_status_code=response.status,
                upstream_response_headers=upstream_headers,
                status_code=response.status,
                response_headers=downstream_headers,
                response_body=response_bytes,
                response_sha256=_sha256(response_bytes),
                requested_sse_frame_cutoff=requested_sse_frame_cutoff,
                complete_sse_frames=(sse_scanner.complete_frames if sse_scanner is not None else 0),
                upstream_complete=upstream_complete,
                downstream_complete=downstream_complete,
                truncated=truncated,
                termination=termination,
                error=error,
            )
        except _RequestRejected as exc:
            self._safe_error(
                pending,
                status_code=exc.status_code,
                message=exc.message,
                request_body_length=len(body),
                upstream_request_headers=upstream_request_headers,
                requested_sse_frame_cutoff=requested_sse_frame_cutoff,
                complete_sse_frames=(sse_scanner.complete_frames if sse_scanner is not None else 0),
                termination="REQUEST_REJECTED",
            )
        except (OSError, TimeoutError, http.client.HTTPException) as exc:
            message = f"upstream transport failed: {type(exc).__name__}"
            if response_started and response is not None:
                self.close_connection = True
                response_bytes = bytes(captured)
                self._proxy._ledger.finish(
                    pending,
                    request_body_length=len(body),
                    upstream_request_headers=upstream_request_headers,
                    upstream_status_code=response.status,
                    upstream_response_headers=upstream_headers,
                    status_code=response.status,
                    response_headers=downstream_headers,
                    response_body=response_bytes,
                    response_sha256=_sha256(response_bytes),
                    requested_sse_frame_cutoff=requested_sse_frame_cutoff,
                    complete_sse_frames=(
                        sse_scanner.complete_frames if sse_scanner is not None else 0
                    ),
                    upstream_complete=False,
                    downstream_complete=False,
                    truncated=True,
                    termination="UPSTREAM_TRANSPORT_ERROR_AFTER_HEADERS",
                    error=message,
                )
            else:
                self._safe_error(
                    pending,
                    status_code=502,
                    message=message,
                    request_body_length=len(body),
                    upstream_request_headers=upstream_request_headers,
                    upstream_status_code=response.status if response is not None else None,
                    upstream_headers=upstream_headers,
                    requested_sse_frame_cutoff=requested_sse_frame_cutoff,
                    complete_sse_frames=(
                        sse_scanner.complete_frames if sse_scanner is not None else 0
                    ),
                    termination="UPSTREAM_TRANSPORT_ERROR",
                )
        except Exception as exc:  # pragma: no cover - last-resort ledger closure
            message = f"capture proxy failed closed: {type(exc).__name__}"
            if response_started and response is not None:
                self.close_connection = True
                response_bytes = bytes(captured)
                self._proxy._ledger.finish(
                    pending,
                    request_body_length=len(body),
                    upstream_request_headers=upstream_request_headers,
                    upstream_status_code=response.status,
                    upstream_response_headers=upstream_headers,
                    status_code=response.status,
                    response_headers=downstream_headers,
                    response_body=response_bytes,
                    response_sha256=_sha256(response_bytes),
                    requested_sse_frame_cutoff=requested_sse_frame_cutoff,
                    complete_sse_frames=(
                        sse_scanner.complete_frames if sse_scanner is not None else 0
                    ),
                    upstream_complete=False,
                    downstream_complete=False,
                    truncated=True,
                    termination="INTERNAL_ERROR_AFTER_HEADERS",
                    error=message,
                )
            else:
                self._safe_error(
                    pending,
                    status_code=502,
                    message=message,
                    request_body_length=len(body),
                    upstream_request_headers=upstream_request_headers,
                    upstream_status_code=response.status if response is not None else None,
                    upstream_headers=upstream_headers,
                    requested_sse_frame_cutoff=requested_sse_frame_cutoff,
                    complete_sse_frames=(
                        sse_scanner.complete_frames if sse_scanner is not None else 0
                    ),
                    termination="INTERNAL_ERROR",
                )
        finally:
            if response is not None:
                response.close()
            if connection is not None:
                self._proxy._unregister_upstream(connection)
                connection.close()


class CaptureVerifier:
    """Fail-closed resolver for untrusted driver-reported capture IDs."""

    def __init__(self, session: CaptureSession) -> None:
        self.session = session
        self._records = {record.capture_id: record for record in session.records}
        if len(self._records) != len(session.records):
            raise CaptureVerificationError("capture ledger contains duplicate IDs")
        expected_orders = tuple(range(1, len(session.records) + 1))
        if tuple(record.order for record in session.records) != expected_orders:
            raise CaptureVerificationError("capture ledger order is not contiguous")
        for record in session.records:
            if (
                record.session_id != session.session_id
                or not record.canonical_proxy_url.startswith(f"{session.proxy_origin}/")
                or not record.canonical_upstream_url.startswith(f"{session.upstream_origin}/")
                or record.started_monotonic_ns < session.created_monotonic_ns
                or record.completed_monotonic_ns < record.started_monotonic_ns
                or record.completed_monotonic_ns > session.sealed_monotonic_ns
                or record.response_sha256 != _sha256(record.response_body)
            ):
                raise CaptureVerificationError("capture ledger boundary is inconsistent")
            cutoff_headers = record.request_header_values(SSE_FRAME_CUTOFF_HEADER)
            if record.requested_sse_frame_cutoff is None:
                if cutoff_headers and record.error is None:
                    raise CaptureVerificationError("capture cutoff header was not interpreted")
            elif (
                cutoff_headers != (str(record.requested_sse_frame_cutoff),)
                or not 1 <= record.requested_sse_frame_cutoff <= MAX_SSE_FRAME_CUTOFF
                or record.upstream_request_header_values(SSE_FRAME_CUTOFF_HEADER)
            ):
                raise CaptureVerificationError("capture cutoff boundary is inconsistent")

    @staticmethod
    def _valid_sse_cut_record(record: CaptureRecord) -> bool:
        if record.requested_sse_frame_cutoff is None:
            return False
        content_types = record.upstream_header_values("Content-Type")
        content_encodings = record.upstream_header_values("Content-Encoding")
        media_type_ok = (
            len(content_types) == 1
            and content_types[0].partition(";")[0].strip().lower() == "text/event-stream"
        )
        encoding_ok = not content_encodings or (
            len(content_encodings) == 1 and content_encodings[0].strip().lower() == "identity"
        )
        frame_count, ends_at_frame = _analyze_complete_sse_prefix(record.response_body)
        return (
            media_type_ok
            and encoding_ok
            and ends_at_frame
            and frame_count == record.requested_sse_frame_cutoff
            and record.complete_sse_frames == frame_count
        )

    @staticmethod
    def _evidence_identity(record: CaptureRecord) -> tuple[str, str] | None:
        path = urlsplit(record.canonical_path_query)
        matched = _EVIDENCE_PATH.fullmatch(path.path)
        if record.method != "GET" or matched is None:
            return None
        if path.query:
            raise CaptureVerificationError("evidence reads must not use query parameters")
        encoded_run_id = matched.group("run")
        try:
            run_id = unquote(encoded_run_id, errors="strict")
        except UnicodeDecodeError as exc:
            raise CaptureVerificationError("evidence Run ID is not valid UTF-8") from exc
        if not run_id or quote(run_id, safe="") != encoded_run_id:
            raise CaptureVerificationError("evidence Run ID is not canonically encoded")
        return matched.group("kind"), run_id

    def derive_admitted_run_ids(self) -> frozenset[str]:
        """Derive Run identities only from complete successful Confirm responses."""

        run_ids: set[str] = set()
        for record in self.session.records:
            if (
                record.method != "POST"
                or record.canonical_path_query != "/api/research-runs"
                or record.status_code not in {200, 201}
                or not record.complete
            ):
                continue
            try:
                body = json.loads(record.response_body)
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if not isinstance(body, dict) or body.get("schema_version") != (
                "phase4-confirm-response/v1"
            ):
                continue
            admission = body.get("admission")
            if not isinstance(admission, dict):
                continue
            run_id = admission.get("run_id")
            if isinstance(run_id, str) and run_id:
                run_ids.add(run_id)
        return frozenset(run_ids)

    def verify_driver_capture_ids(
        self,
        references: Mapping[str, str],
        *,
        seed_run_ids: Sequence[str] = (),
        reject_unused_evidence_reads: bool = True,
    ) -> dict[str, CaptureRecord]:
        """Resolve untrusted labels to real, complete, exact-Run observations.

        The caller must consume bytes from the returned records; a driver's own
        response value or digest is intentionally not accepted by this API.
        """

        if not references or not all(
            isinstance(label, str) and label and isinstance(capture_id, str) and capture_id
            for label, capture_id in references.items()
        ):
            raise CaptureVerificationError("driver capture references are malformed")
        capture_ids = tuple(references.values())
        if len(capture_ids) != len(set(capture_ids)):
            raise CaptureVerificationError("driver reused a capture ID")
        missing = sorted(set(capture_ids) - set(self._records))
        if missing:
            raise CaptureVerificationError("driver named a capture absent from the ledger")

        allowed_run_ids = {
            run_id for run_id in seed_run_ids if isinstance(run_id, str) and run_id
        } | set(self.derive_admitted_run_ids())
        resolved: dict[str, CaptureRecord] = {}
        for label, capture_id in references.items():
            record = self._records[capture_id]
            identity = self._evidence_identity(record)
            if identity is None:
                raise CaptureVerificationError(
                    f"driver reference {label!r} is not an exact projection/SSE read"
                )
            evidence_kind, run_id = identity
            if run_id not in allowed_run_ids:
                raise CaptureVerificationError(
                    f"driver reference {label!r} names a Run without admission provenance"
                )
            deliberate_cut = record.deliberate_sse_cut
            finite_requested_cut = (
                record.complete
                and record.requested_sse_frame_cutoff is not None
                and record.termination == "UPSTREAM_EOF_AT_SSE_FRAME_CUTOFF"
            )
            if deliberate_cut or finite_requested_cut:
                if evidence_kind != "events" or not self._valid_sse_cut_record(record):
                    raise CaptureVerificationError(
                        f"driver reference {label!r} has an invalid SSE frame cutoff"
                    )
            elif not record.complete:
                raise CaptureVerificationError(
                    f"driver reference {label!r} is incomplete or truncated"
                )
            if record.response_header_values(CAPTURE_SESSION_HEADER) != (
                self.session.session_id,
            ) or record.response_header_values(CAPTURE_ID_HEADER) != (record.capture_id,):
                raise CaptureVerificationError(f"driver reference {label!r} lacks its gate receipt")
            resolved[label] = record

        if reject_unused_evidence_reads:
            evidence_ids = {
                record.capture_id
                for record in self.session.records
                if self._evidence_identity(record) is not None
            }
            if set(capture_ids) != evidence_ids:
                raise CaptureVerificationError(
                    "driver omitted or substituted a gate-observed evidence read"
                )
        return resolved


class AuditedCaptureProxy:
    """Context-managed fresh localhost reverse proxy with a private ledger."""

    def __init__(
        self,
        upstream_origin: str,
        *,
        listen_host: str = "127.0.0.1",
        listen_port: int = 0,
        upstream_timeout_seconds: float = 30.0,
        max_request_bytes: int = DEFAULT_MAX_REQUEST_BYTES,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    ) -> None:
        if listen_host != "127.0.0.1":
            raise CaptureProxyError("capture proxy must bind IPv4 localhost")
        if isinstance(listen_port, bool) or not 0 <= listen_port <= 65535:
            raise CaptureProxyError("capture proxy listen port is invalid")
        if upstream_timeout_seconds <= 0:
            raise CaptureProxyError("upstream timeout must be positive")
        if max_request_bytes <= 0 or max_response_bytes <= 0:
            raise CaptureProxyError("capture byte limits must be positive")
        self.upstream_origin = _canonical_origin(upstream_origin, label="upstream_origin")
        self.listen_host = listen_host
        self.listen_port = listen_port
        self.upstream_timeout_seconds = float(upstream_timeout_seconds)
        self.max_request_bytes = int(max_request_bytes)
        self.max_response_bytes = int(max_response_bytes)
        self.session_id = f"SESSION-{secrets.token_hex(24).upper()}"
        self.created_at = _utc_now()
        self.created_monotonic_ns = time.monotonic_ns()
        self._ledger = _CaptureLedger(session_id=self.session_id)
        self._server: _FreshThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._origin: str | None = None
        self._sealed_session: CaptureSession | None = None
        self._active_lock = threading.Lock()
        self._active_upstreams: set[http.client.HTTPConnection] = set()

    @property
    def origin(self) -> str:
        if self._origin is None:
            raise CaptureProxyError("capture proxy has not started")
        return self._origin

    @property
    def session(self) -> CaptureSession:
        if self._sealed_session is None:
            raise CaptureProxyError("capture session is not sealed")
        return self._sealed_session

    def verifier(self) -> CaptureVerifier:
        return CaptureVerifier(self.session)

    def _register_upstream(self, connection: http.client.HTTPConnection) -> None:
        with self._active_lock:
            self._active_upstreams.add(connection)

    def _unregister_upstream(self, connection: http.client.HTTPConnection) -> None:
        with self._active_lock:
            self._active_upstreams.discard(connection)

    def _close_active_upstreams(self) -> None:
        with self._active_lock:
            active = tuple(self._active_upstreams)
        for connection in active:
            connection.close()

    def start(self) -> AuditedCaptureProxy:
        if self._server is not None or self._sealed_session is not None:
            raise CaptureProxyError("capture proxy cannot be started twice")
        if self.listen_port:
            probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            probe.settimeout(0.2)
            try:
                if probe.connect_ex((self.listen_host, self.listen_port)) == 0:
                    raise CaptureProxyError(
                        "capture proxy address already has a responding listener"
                    )
            finally:
                probe.close()
        try:
            server = _FreshThreadingHTTPServer((self.listen_host, self.listen_port), _ProxyHandler)
        except OSError as exc:
            raise CaptureProxyError("capture proxy could not claim a fresh listener") from exc
        server.capture_proxy = self  # type: ignore[attr-defined]
        self._server = server
        port = int(server.server_address[1])
        self._origin = f"http://{self.listen_host}:{port}"
        self._thread = threading.Thread(
            target=server.serve_forever,
            name=f"vs01-capture-{self.session_id[-8:]}",
            daemon=True,
        )
        self._thread.start()
        return self

    def seal(self, *, timeout_seconds: float = 10.0) -> CaptureSession:
        if self._sealed_session is not None:
            return self._sealed_session
        if self._server is None or self._thread is None:
            raise CaptureProxyError("capture proxy has not started")
        self._ledger.close_intake()
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=min(timeout_seconds, 5.0))
        if self._thread.is_alive():
            raise CaptureProxyError("capture listener did not stop at the cutoff")
        self._close_active_upstreams()
        records = self._ledger.seal(timeout_seconds=timeout_seconds)
        sealed_monotonic_ns = time.monotonic_ns()
        self._sealed_session = CaptureSession(
            session_id=self.session_id,
            proxy_origin=self.origin,
            upstream_origin=self.upstream_origin,
            created_at=self.created_at,
            created_monotonic_ns=self.created_monotonic_ns,
            sealed_at=_utc_now(),
            sealed_monotonic_ns=sealed_monotonic_ns,
            records=records,
        )
        return self._sealed_session

    def __enter__(self) -> AuditedCaptureProxy:
        return self.start()

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> bool:
        try:
            self.seal()
        except CaptureProxyError:
            if exc is None:
                raise
        return False


__all__ = [
    "AuditedCaptureProxy",
    "CAPTURE_ID_HEADER",
    "CAPTURE_SESSION_HEADER",
    "MAX_SSE_FRAME_CUTOFF",
    "SSE_FRAME_CUTOFF_HEADER",
    "CaptureProxyError",
    "CaptureRecord",
    "CaptureSession",
    "CaptureVerificationError",
    "CaptureVerifier",
]
