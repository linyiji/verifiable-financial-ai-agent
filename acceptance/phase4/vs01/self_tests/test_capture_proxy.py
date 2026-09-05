from __future__ import annotations

import hashlib
import http.client
import json
import queue
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit

import pytest

from acceptance.phase4.vs01.harness.capture_proxy import (
    CAPTURE_ID_HEADER,
    CAPTURE_SESSION_HEADER,
    SSE_FRAME_CUTOFF_HEADER,
    AuditedCaptureProxy,
    CaptureProxyError,
    CaptureVerificationError,
    _analyze_complete_sse_prefix,
    _SSEFrameBoundaryScanner,
)


class _ProductSurface(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    streaming_first_sent = threading.Event()
    streaming_release = threading.Event()

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return

    def _write(
        self,
        status: int,
        body: bytes,
        *,
        content_type: str = "application/json",
        extra_headers: tuple[tuple[str, str], ...] = (),
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for name, value in extra_headers:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()

    def do_POST(self) -> None:  # noqa: N802
        size = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(size)
        if self.path != "/api/research-runs":
            self._write(404, b"{}")
            return
        body = json.dumps(
            {
                "schema_version": "phase4-confirm-response/v1",
                "admission": {"run_id": "RUN-PROXIED-ONE"},
            },
            separators=(",", ":"),
        ).encode()
        self._write(201, body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/api/research-runs/RUN-PROXIED-ONE/events-streaming":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(b": first\n\n")
            self.wfile.flush()
            self.streaming_first_sent.set()
            self.streaming_release.wait(timeout=2)
            self.wfile.write(b": second\n\n")
            self.wfile.flush()
            return
        if self.path == "/api/research-runs/RUN-PARTIAL/events":
            self._write(200, b"data: unfinished", content_type="text/event-stream")
            return
        if self.path.endswith("/projection"):
            body = b'{"projection_sequence":7,"run_id":"RUN-PROXIED-ONE"}'
            self._write(
                200,
                body,
                extra_headers=(("X-Duplicate", "first"), ("X-Duplicate", "second")),
            )
            return
        if self.path.endswith("/events"):
            body = (
                b'id: 8\nevent: task.started\ndata: {"run_id":"RUN-PROXIED-ONE",'
                b'"sequence":8}\n\n: keep-alive\n\n'
            )
            self._write(
                200,
                body,
                content_type="text/event-stream",
                extra_headers=(
                    (
                        "X-Upstream-Saw-Cutoff",
                        "yes" if self.headers.get(SSE_FRAME_CUTOFF_HEADER) else "no",
                    ),
                ),
            )
            return
        if self.path == "/redirect":
            self._write(302, b"redirect", extra_headers=(("Location", "/projection"),))
            return
        if self.path.endswith("/large"):
            self._write(200, b"abcdefgh")
            return
        self._write(404, b"{}")


class _Server(ThreadingHTTPServer):
    daemon_threads = True


@contextmanager
def _product_server() -> Iterator[str]:
    server = _Server(("127.0.0.1", 0), _ProductSurface)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _request(
    origin: str,
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
) -> tuple[int, list[tuple[str, str]], bytes]:
    parsed = urlsplit(origin)
    connection = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=3)
    try:
        connection.request(method, path, headers=headers or {}, body=body)
        response = connection.getresponse()
        return response.status, response.getheaders(), response.read()
    finally:
        connection.close()


def _header(headers: list[tuple[str, str]], name: str) -> str:
    values = [value for key, value in headers if key.lower() == name.lower()]
    assert len(values) == 1
    return values[0]


def test_proxy_streams_exact_bytes_and_seals_immutable_metadata() -> None:
    with _product_server() as upstream:
        with AuditedCaptureProxy(upstream) as proxy:
            status, headers, body = _request(
                proxy.origin,
                "GET",
                "/api/research-runs/RUN-PROXIED-ONE/events",
                headers={
                    "Accept": "text/event-stream",
                    "Last-Event-ID": "7",
                    "X-Phase4-Contract-Version": "phase4-core/v1",
                    "Authorization": "Bearer must-not-be-retained",
                    "X-Private-Token": "must-not-be-retained-either",
                },
            )
            capture_id = _header(headers, CAPTURE_ID_HEADER)
            assert _header(headers, CAPTURE_SESSION_HEADER) == proxy.session_id
            assert status == 200
            assert body.endswith(b": keep-alive\n\n")

        session = proxy.session
        assert session.proxy_origin == proxy.origin
        assert session.upstream_origin == upstream
        assert len(session.records) == 1
        record = session.records[0]
        assert record.capture_id == capture_id
        assert record.order == 1
        assert record.complete
        assert record.termination == "UPSTREAM_EOF"
        assert record.response_body == body
        assert record.response_sha256 == hashlib.sha256(body).hexdigest()
        assert record.request_header_values("Last-Event-ID") == ("7",)
        assert record.request_header_values("X-Phase4-Contract-Version") == ("phase4-core/v1",)
        assert record.request_header_values("Authorization") == ()
        assert record.request_header_values("X-Private-Token") == ()
        assert record.upstream_request_header_values("Authorization") == ()
        assert record.upstream_request_header_values("X-Private-Token") == ()
        assert record.upstream_request_header_values("Accept-Encoding") == ("identity",)
        assert record.upstream_request_header_values("Last-Event-ID") == ("7",)
        assert record.sensitive_request_header_names == (
            "authorization",
            "x-private-token",
        )
        with pytest.raises(CaptureProxyError, match="cannot be started twice"):
            proxy.start()


def test_open_sse_response_is_forwarded_incrementally_while_captured() -> None:
    _ProductSurface.streaming_first_sent = threading.Event()
    _ProductSurface.streaming_release = threading.Event()
    observed: queue.Queue[tuple[int, list[tuple[str, str]], bytes]] = queue.Queue()
    client_failure: queue.Queue[BaseException] = queue.Queue()
    with _product_server() as upstream:
        with AuditedCaptureProxy(upstream) as proxy:

            def consume() -> None:
                parsed = urlsplit(proxy.origin)
                connection = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=3)
                try:
                    connection.request(
                        "GET",
                        "/api/research-runs/RUN-PROXIED-ONE/events-streaming",
                    )
                    response = connection.getresponse()
                    first = bytearray()
                    while len(first) < len(b": first\n\n"):
                        first.extend(response.read1(len(b": first\n\n") - len(first)))
                    observed.put((response.status, response.getheaders(), bytes(first)))
                    remainder = response.read()
                    observed.put((response.status, [], remainder))
                except BaseException as exc:  # pragma: no cover - asserted below
                    client_failure.put(exc)
                finally:
                    connection.close()

            thread = threading.Thread(target=consume, daemon=True)
            thread.start()
            assert _ProductSurface.streaming_first_sent.wait(timeout=1)
            status, headers, first = observed.get(timeout=1)
            assert status == 200
            assert first == b": first\n\n"
            capture_id = _header(headers, CAPTURE_ID_HEADER)
            _ProductSurface.streaming_release.set()
            _, _, remainder = observed.get(timeout=1)
            thread.join(timeout=1)
            assert not thread.is_alive()
            assert client_failure.empty()
            assert remainder == b": second\n\n"

        record = proxy.session.records[0]
        assert record.capture_id == capture_id
        assert record.complete
        assert record.response_body == b": first\n\n: second\n\n"


def test_sse_cutoff_handles_mixed_line_endings_chunks_and_excludes_partial() -> None:
    scanner = _SSEFrameBoundaryScanner(target_frames=3)
    chunks = (
        b": one\r",
        b"\r",
        b"d",
        b"ata: two\r",
        b"\n\r",
        b"\n",
        b"data: three\n",
        b"\npartial-must-not-cross-cutoff",
    )
    retained = bytearray()
    for chunk in chunks:
        cutoff = scanner.feed(chunk, absolute_start=len(retained))
        retained.extend(chunk if cutoff is None else chunk[:cutoff])
        if cutoff is not None:
            break
    expected = b": one\r\rdata: two\r\n\r\ndata: three\n\n"
    assert bytes(retained) == expected
    assert scanner.complete_frames == 3
    assert scanner.ends_at_complete_frame(absolute_end=len(retained))
    assert _analyze_complete_sse_prefix(bytes(retained)) == (3, True)


def test_gate_owned_sse_cutoff_is_exact_stripped_and_verifier_admissible() -> None:
    with _product_server() as upstream:
        with AuditedCaptureProxy(upstream) as proxy:
            status, headers, body = _request(
                proxy.origin,
                "GET",
                "/api/research-runs/RUN-PROXIED-ONE/events",
                headers={
                    SSE_FRAME_CUTOFF_HEADER: "1",
                    "Last-Event-ID": "7",
                },
            )
            capture_id = _header(headers, CAPTURE_ID_HEADER)
            assert status == 200
            assert body == (
                b'id: 8\nevent: task.started\ndata: {"run_id":"RUN-PROXIED-ONE","sequence":8}\n\n'
            )

        record = proxy.session.records[0]
        assert record.capture_id == capture_id
        assert record.request_header_values(SSE_FRAME_CUTOFF_HEADER) == ("1",)
        assert record.upstream_request_header_values(SSE_FRAME_CUTOFF_HEADER) == ()
        assert record.upstream_header_values("X-Upstream-Saw-Cutoff") == ("no",)
        assert record.requested_sse_frame_cutoff == 1
        assert record.complete_sse_frames == 1
        assert record.termination == "GATE_SSE_FRAME_CUTOFF"
        assert not record.upstream_complete
        assert record.downstream_complete
        assert not record.truncated
        assert record.error is None
        assert record.deliberate_sse_cut
        assert not record.complete
        resolved = proxy.verifier().verify_driver_capture_ids(
            {"stream": capture_id}, seed_run_ids=("RUN-PROXIED-ONE",)
        )
        assert resolved["stream"] == record


def test_cutoff_never_counts_or_admits_an_eof_partial_frame() -> None:
    with _product_server() as upstream:
        with AuditedCaptureProxy(upstream) as proxy:
            status, headers, body = _request(
                proxy.origin,
                "GET",
                "/api/research-runs/RUN-PARTIAL/events",
                headers={SSE_FRAME_CUTOFF_HEADER: "1"},
            )
            capture_id = _header(headers, CAPTURE_ID_HEADER)
            assert status == 200
            assert body == b"data: unfinished"

        record = proxy.session.records[0]
        assert record.complete_sse_frames == 0
        assert record.truncated
        assert record.error is not None
        assert record.termination == "UPSTREAM_EOF_BEFORE_SSE_FRAME_CUTOFF"
        assert not record.deliberate_sse_cut
        with pytest.raises(CaptureVerificationError, match="incomplete or truncated"):
            proxy.verifier().verify_driver_capture_ids(
                {"stream": capture_id}, seed_run_ids=("RUN-PARTIAL",)
            )


@pytest.mark.parametrize("value", ["0", "-1", "10001", "not-a-number"])
def test_invalid_sse_cutoff_fails_before_upstream(value: str) -> None:
    with _product_server() as upstream:
        with AuditedCaptureProxy(upstream) as proxy:
            status, _, body = _request(
                proxy.origin,
                "GET",
                "/api/research-runs/RUN-PROXIED-ONE/events",
                headers={SSE_FRAME_CUTOFF_HEADER: value},
            )
            assert status == 400
            assert b"SSE frame cutoff" in body
        record = proxy.session.records[0]
        assert record.upstream_status_code is None
        assert record.termination == "REQUEST_REJECTED"


def test_sse_cutoff_rejects_non_event_stream_response() -> None:
    with _product_server() as upstream:
        with AuditedCaptureProxy(upstream) as proxy:
            status, _, body = _request(
                proxy.origin,
                "GET",
                "/api/research-runs/RUN-PROXIED-ONE/projection",
                headers={SSE_FRAME_CUTOFF_HEADER: "1"},
            )
            assert status == 502
            assert b"text/event-stream" in body
        record = proxy.session.records[0]
        assert record.requested_sse_frame_cutoff == 1
        assert record.upstream_request_header_values(SSE_FRAME_CUTOFF_HEADER) == ()
        assert record.termination == "SSE_FRAME_CUTOFF_CONTENT_TYPE_REJECTED"


def test_verifier_roots_values_in_ledger_and_proxied_admission() -> None:
    with _product_server() as upstream:
        with AuditedCaptureProxy(upstream) as proxy:
            admission_status, _, _ = _request(
                proxy.origin,
                "POST",
                "/api/research-runs",
                headers={"Content-Type": "application/json"},
                body=b"{}",
            )
            assert admission_status == 201
            projection_status, projection_headers, projection_body = _request(
                proxy.origin,
                "GET",
                "/api/research-runs/RUN-PROXIED-ONE/projection",
            )
            stream_status, stream_headers, stream_body = _request(
                proxy.origin,
                "GET",
                "/api/research-runs/RUN-PROXIED-ONE/events",
                headers={"Last-Event-ID": "7"},
            )
            assert (projection_status, stream_status) == (200, 200)
            projection_id = _header(projection_headers, CAPTURE_ID_HEADER)
            stream_id = _header(stream_headers, CAPTURE_ID_HEADER)

        verifier = proxy.verifier()
        assert verifier.derive_admitted_run_ids() == frozenset({"RUN-PROXIED-ONE"})
        resolved = verifier.verify_driver_capture_ids(
            {"before": projection_id, "stream": stream_id}
        )
        assert resolved["before"].response_body == projection_body
        assert resolved["stream"].response_body == stream_body
        assert resolved["before"].upstream_header_values("X-Duplicate") == (
            "first",
            "second",
        )
        with pytest.raises(CaptureVerificationError, match="reused"):
            verifier.verify_driver_capture_ids({"before": projection_id, "stream": projection_id})
        with pytest.raises(CaptureVerificationError, match="omitted or substituted"):
            verifier.verify_driver_capture_ids({"before": projection_id})
        with pytest.raises(CaptureVerificationError, match="absent"):
            verifier.verify_driver_capture_ids(
                {"before": projection_id, "stream": "CAP-FABRICATED"}
            )


def test_direct_backend_read_cannot_be_substituted_for_proxy_evidence() -> None:
    with _product_server() as upstream:
        direct_status, _, direct_body = _request(
            upstream, "GET", "/api/research-runs/RUN-PROXIED-ONE/projection"
        )
        assert direct_status == 200
        with AuditedCaptureProxy(upstream) as proxy:
            _, headers, proxied_body = _request(
                proxy.origin,
                "GET",
                "/api/research-runs/RUN-PROXIED-ONE/projection",
            )
            real_capture_id = _header(headers, CAPTURE_ID_HEADER)
            assert direct_body == proxied_body

        verifier = proxy.verifier()
        with pytest.raises(CaptureVerificationError, match="absent"):
            verifier.verify_driver_capture_ids(
                {"projection": "CAP-SELF-AUTHORED-FROM-DIRECT-BYTES"},
                seed_run_ids=("RUN-PROXIED-ONE",),
            )
        resolved = verifier.verify_driver_capture_ids(
            {"projection": real_capture_id},
            seed_run_ids=("RUN-PROXIED-ONE",),
        )
        assert resolved["projection"].response_body == direct_body


def test_truncated_evidence_is_recorded_but_never_admitted() -> None:
    with _product_server() as upstream:
        with AuditedCaptureProxy(upstream, max_response_bytes=4) as proxy:
            status, headers, body = _request(
                proxy.origin,
                "GET",
                "/api/research-runs/RUN-PROXIED-ONE/projection/large",
            )
            capture_id = _header(headers, CAPTURE_ID_HEADER)
            assert status == 200
            assert body == b"abcd"

        record = proxy.session.records[0]
        assert record.capture_id == capture_id
        assert record.truncated
        assert record.termination == "GATE_RESPONSE_BYTE_LIMIT"
        assert not record.complete


def test_evidence_route_truncation_is_rejected() -> None:
    with _product_server() as upstream:
        with AuditedCaptureProxy(upstream, max_response_bytes=4) as proxy:
            _, headers, _ = _request(
                proxy.origin,
                "GET",
                "/api/research-runs/RUN-PROXIED-ONE/projection",
            )
            capture_id = _header(headers, CAPTURE_ID_HEADER)
        with pytest.raises(CaptureVerificationError, match="incomplete or truncated"):
            proxy.verifier().verify_driver_capture_ids(
                {"projection": capture_id}, seed_run_ids=("RUN-PROXIED-ONE",)
            )


def test_upstream_redirect_is_not_forwarded() -> None:
    with _product_server() as upstream:
        with AuditedCaptureProxy(upstream) as proxy:
            status, headers, body = _request(proxy.origin, "GET", "/redirect")
            capture_id = _header(headers, CAPTURE_ID_HEADER)
            assert status == 502
            assert b"redirects are forbidden" in body
            assert not any(name.lower() == "location" for name, _ in headers)
        record = proxy.session.records[0]
        assert record.capture_id == capture_id
        assert record.upstream_status_code == 302
        assert record.status_code == 502
        assert record.termination == "UPSTREAM_REDIRECT_REJECTED"
        assert not record.complete


def test_explicit_port_rejects_a_preexisting_listener() -> None:
    with _product_server() as upstream:
        port = urlsplit(upstream).port
        assert port is not None
        proxy = AuditedCaptureProxy(upstream, listen_port=port)
        with pytest.raises(CaptureProxyError, match="already has a responding listener"):
            proxy.start()
