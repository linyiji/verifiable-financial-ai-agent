#!/usr/bin/env python3
"""Capture real Phase 4 VS01 projection/SSE scenario receipts through the gate proxy.

The driver writes only gate-issued capture identifiers.  Response bodies remain in
the gate-owned in-memory ledger and are reconstructed and validated by X.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

CORE_VERSION = "phase4-core/v1"
EVENT_VERSION = "phase4-runtime-event/v1"
CAPTURE_HEADER = "X-VS01-Capture-ID"
TIMEOUT_SECONDS = 880.0
FAILURE_CHECKPOINT_SCHEMA_VERSION = "phase4-vs01-runtime-sse-failure-checkpoint/v1"
TERMINAL_RUN_STATUSES = frozenset({"RELEASED", "FAILED", "CANCELLED"})
KNOWN_RUN_STATUSES = frozenset(
    {
        "DRAFT",
        "SCHEME_GENERATING",
        "AWAITING_CONFIRMATION",
        "PLANNING",
        "RUNNING",
        "REVIEW",
        "PROVING",
        *TERMINAL_RUN_STATUSES,
    }
)
_SAFE_EVENT_NAME = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}")
_SAFE_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,159}")


class DriverError(RuntimeError):
    pass


def _candidate_sha() -> str:
    observation = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
    )
    candidate = observation.stdout.strip()
    return candidate if re.fullmatch(r"[0-9a-f]{40}", candidate) else "UNKNOWN"


def _checkpoint_path(output_path: Path) -> Path:
    return output_path.with_suffix(".failure.json")


def _atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
        os.replace(temporary_path, path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def _write_final_index(output_path: Path, result: dict[str, Any]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _safe_exception(error: BaseException) -> tuple[str, str]:
    exception_class = type(error).__name__
    if isinstance(error, DriverError):
        message = str(error)
    elif isinstance(error, TimeoutError):
        message = "driver operation timed out"
    elif isinstance(error, HTTPError):
        message = f"HTTP request failed with status {error.code}"
    elif isinstance(error, OSError):
        message = "driver operating-system operation failed"
    else:
        message = "driver stage failed"

    for name, value in os.environ.items():
        normalized = name.upper()
        if value and any(
            marker in normalized
            for marker in ("API_KEY", "PASSWORD", "SECRET", "TOKEN", "DATABASE_URL")
        ):
            message = message.replace(value, "<redacted>")
    message = re.sub(
        r"(?i)([?&](?:api[_-]?key|token|password|secret)=)[^&\s]+",
        r"\1<redacted>",
        message,
    )
    message = re.sub(r"(?i)(://[^:/\s]+:)[^@\s]+(@)", r"\1<redacted>\2", message)
    message = re.sub(
        r"(?i)\b(api[_-]?key|token|password|secret)\b\s*[:=]\s*[^\s,;]+",
        r"\1=<redacted>",
        message,
    )
    return exception_class, message[:512]


class FailureCheckpoint:
    """Durable, secret-free diagnostics for an incomplete tracked SSE capture."""

    def __init__(self, output_path: Path, *, candidate_sha: str) -> None:
        self.path = _checkpoint_path(output_path)
        self.candidate_sha = candidate_sha
        self.scenario_id = "bootstrap"
        self.run_id = "UNKNOWN"
        self.current_stage = "INITIALIZE_DRIVER"
        self.expected = "validated driver environment"
        self.run_status = "UNKNOWN"
        self.safe_failure_stage = "NONE"
        self.safe_failure_code = "NONE"
        self.history: list[dict[str, Any]] = []

    def start_stage(
        self,
        stage: str,
        expected: str,
        *,
        scenario_id: str,
        run_id: str | None = None,
        watcher: EventWatcher | None = None,
    ) -> None:
        previous_scenario = self.scenario_id
        previous_run = self.run_id
        self.scenario_id = scenario_id
        self.current_stage = stage
        self.expected = expected
        if run_id is not None and _SAFE_IDENTIFIER.fullmatch(run_id):
            self.run_id = run_id
        elif scenario_id != previous_scenario:
            self.run_id = "UNKNOWN"
        if self.run_id != previous_run:
            self.run_status = "UNKNOWN"
            self.safe_failure_stage = "NONE"
            self.safe_failure_code = "NONE"
        self._record("WAITING", watcher=watcher)

    def pass_stage(self, *, watcher: EventWatcher | None = None) -> None:
        self._record("PASS", watcher=watcher)

    def update_run_status(self, run_status: str) -> None:
        self.run_status = run_status if run_status in KNOWN_RUN_STATUSES else "UNKNOWN"

    def fail(
        self,
        error: BaseException,
        *,
        watcher: EventWatcher | None = None,
        run_status: str = "UNKNOWN",
        safe_failure_stage: str = "NONE",
        safe_failure_code: str = "NONE",
    ) -> None:
        self.update_run_status(run_status)
        self.safe_failure_stage = (
            safe_failure_stage if _SAFE_IDENTIFIER.fullmatch(safe_failure_stage) else "NONE"
        )
        self.safe_failure_code = (
            safe_failure_code if _SAFE_IDENTIFIER.fullmatch(safe_failure_code) else "NONE"
        )
        exception_class, safe_error = _safe_exception(error)
        self._record(
            "FAIL",
            watcher=watcher,
            exception_class=exception_class,
            safe_error=safe_error,
        )

    def discard(self) -> None:
        self.path.unlink(missing_ok=True)

    def _record(
        self,
        status: str,
        *,
        watcher: EventWatcher | None,
        exception_class: str | None = None,
        safe_error: str | None = None,
    ) -> None:
        last_sequence, observed_names, last_event = (
            watcher.diagnostic_snapshot() if watcher is not None else (None, [], "NONE")
        )
        entry: dict[str, Any] = {
            "scenario_id": self.scenario_id,
            "run_id": self.run_id,
            "stage": self.current_stage,
            "expected_event_or_condition": self.expected,
            "last_observed_sse_sequence": last_sequence,
            "observed_event_names": observed_names,
            "last_observed_event": last_event,
            "run_status": self.run_status,
            "run_terminal": self.run_status in TERMINAL_RUN_STATUSES,
            "status": status,
        }
        if exception_class is not None:
            entry["exception_class"] = exception_class
        if safe_error is not None:
            entry["safe_error"] = safe_error
        self.history.append(entry)
        document = {
            "schema_version": FAILURE_CHECKPOINT_SCHEMA_VERSION,
            "candidate_sha": self.candidate_sha,
            "scenario_id": self.scenario_id,
            "run_id": self.run_id,
            "current_stage": self.current_stage,
            "expected_event_or_condition": self.expected,
            "last_observed_sse_sequence": last_sequence,
            "observed_event_names": observed_names,
            "last_observed_event": last_event,
            "run_status": self.run_status,
            "run_terminal": self.run_status in TERMINAL_RUN_STATUSES,
            "status": status,
            "failure_stage": self.current_stage if status == "FAIL" else "NONE",
            "safe_failure_stage": self.safe_failure_stage,
            "safe_failure_code": self.safe_failure_code,
            "exception_class": exception_class or "NONE",
            "safe_error": safe_error or "NONE",
            "stages": self.history,
        }
        _atomic_write_json(self.path, document)


def _capture_id(headers: Any) -> str:
    value = headers.get(CAPTURE_HEADER)
    if not isinstance(value, str) or not value:
        raise DriverError("gate proxy response omitted its capture identifier")
    return value


def _request(
    base_url: str,
    method: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
) -> tuple[int, Any, bytes]:
    request_headers = {
        "Accept": "application/json",
        "X-Phase4-Contract-Version": CORE_VERSION,
        **(headers or {}),
    }
    payload = None
    if body is not None:
        payload = json.dumps(body, separators=(",", ":")).encode()
        request_headers["Content-Type"] = "application/json"
    request = Request(
        f"{base_url.rstrip('/')}{path}",
        data=payload,
        headers=request_headers,
        method=method,
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.status, response.headers, response.read()
    except HTTPError as error:
        return error.code, error.headers, error.read()


def _json_request(
    base_url: str,
    method: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> tuple[int, Any, dict[str, Any]]:
    headers = {} if idempotency_key is None else {"Idempotency-Key": idempotency_key}
    status, response_headers, raw = _request(
        base_url,
        method,
        path,
        body=body,
        headers=headers,
    )
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DriverError(f"{method} {path} did not return JSON") from error
    if not isinstance(value, dict):
        raise DriverError(f"{method} {path} did not return a JSON object")
    return status, response_headers, value


def _find_string(value: Any, name: str) -> str | None:
    if isinstance(value, dict):
        candidate = value.get(name)
        if isinstance(candidate, str) and candidate:
            return candidate
        for child in value.values():
            found = _find_string(child, name)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_string(child, name)
            if found is not None:
                return found
    return None


def _object_id(base_url: str, symbol: str, company_name: str) -> str:
    token = f"vs01-driver-object-{symbol.lower()}"
    status, _, value = _json_request(
        base_url,
        "POST",
        "/api/objects",
        body={
            "symbol": symbol,
            "company_name": company_name,
            "exchange": "NASDAQ",
            "currency": "USD",
        },
        idempotency_key=token,
    )
    if status in {200, 201}:
        found = _find_string(value, "object_id")
        if found is not None:
            return found
    status, _, value = _json_request(
        base_url,
        "GET",
        f"/api/objects?{urlencode({'symbol': symbol, 'limit': 10})}",
    )
    if status != 200:
        raise DriverError(f"could not resolve the {symbol} research object")
    items = value.get("items")
    if not isinstance(items, list):
        raise DriverError("object collection did not contain items")
    for item in items:
        found = _find_string(item, "object_id")
        if found is not None:
            return found
    raise DriverError(f"the {symbol} research object is unavailable")


def _admit_run(base_url: str, object_id: str, label: str) -> str:
    mutation_nonce = secrets.token_hex(12)
    status, _, draft = _json_request(
        base_url,
        "POST",
        "/api/research-runs/prepare",
        body={
            "research_object_id": object_id,
            "research_goal": (
                "Produce a verifiable full-company research report with material risks, "
                "deterministic financial calculations, and explicit verification limits."
            ),
            "as_of": "2026-09-05",
            "preferences": {},
        },
        idempotency_key=f"vs01-driver-prepare-{label}-{mutation_nonce}",
    )
    if status != 201:
        raise DriverError(f"could not prepare {label} Run")
    required = {
        name: draft.get(name) for name in ("draft_id", "draft_version", "draft_hash", "object_id")
    }
    if (
        not isinstance(required["draft_id"], str)
        or type(required["draft_version"]) is not int
        or not isinstance(required["draft_hash"], str)
    ):
        raise DriverError("prepared draft omitted frozen confirmation fields")
    status, _, admitted = _json_request(
        base_url,
        "POST",
        "/api/research-runs",
        body={
            "draft_id": required["draft_id"],
            "draft_version": required["draft_version"],
            "draft_hash": required["draft_hash"],
            "research_object_id": object_id,
            "confirm_scheme": True,
        },
        idempotency_key=f"vs01-driver-confirm-{label}-{mutation_nonce}",
    )
    run_id = _find_string(admitted, "run_id")
    if status != 201 or run_id is None:
        raise DriverError(f"could not confirm {label} Run")
    return run_id


def _capture_projection(base_url: str, run_id: str) -> tuple[str, dict[str, Any]]:
    status, headers, value = _json_request(
        base_url,
        "GET",
        f"/api/research-runs/{quote(run_id, safe='')}/projection",
    )
    if status != 200:
        raise DriverError("exact-Run projection capture failed")
    return _capture_id(headers), value


def _capture_stream(
    base_url: str,
    run_id: str,
    cursor: int,
    *,
    cut_frames: int | None = None,
) -> str:
    headers = {
        "Accept": "text/event-stream",
        "X-Phase4-Event-Contract-Version": EVENT_VERSION,
        "Last-Event-ID": str(cursor),
    }
    if cut_frames is not None:
        headers["X-VS01-Capture-Cut-After-Complete-Frames"] = str(cut_frames)
    status, response_headers, _ = _request(
        base_url,
        "GET",
        f"/api/research-runs/{quote(run_id, safe='')}/events",
        headers=headers,
        timeout=TIMEOUT_SECONDS,
    )
    if status != 200:
        raise DriverError("exact-Run SSE capture failed")
    return _capture_id(response_headers)


def _projection_sequence(value: dict[str, Any]) -> int:
    sequence = value.get("projection_sequence")
    if type(sequence) is not int or sequence < 0:
        raise DriverError("projection omitted its durable sequence")
    return sequence


class EventWatcher:
    def __init__(self, base_url: str, run_id: str) -> None:
        self.base_url = base_url
        self.run_id = run_id
        self.events: list[dict[str, Any]] = []
        self.capture_id: str | None = None
        self.error: BaseException | None = None
        self.done = False
        self.condition = threading.Condition()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def diagnostic_snapshot(self) -> tuple[int | None, list[str], str]:
        with self.condition:
            observed_names: list[str] = []
            last_sequence: int | None = None
            last_event = "NONE"
            for event in self.events:
                event_name = event.get("type")
                sequence = event.get("sequence")
                if isinstance(event_name, str) and _SAFE_EVENT_NAME.fullmatch(event_name):
                    if event_name not in observed_names:
                        observed_names.append(event_name)
                    last_event = event_name
                if type(sequence) is int:
                    last_sequence = sequence
            return last_sequence, observed_names, last_event

    def _run(self) -> None:
        request = Request(
            f"{self.base_url.rstrip('/')}/api/research-runs/{quote(self.run_id, safe='')}/events",
            headers={
                "Accept": "text/event-stream",
                "X-Phase4-Contract-Version": CORE_VERSION,
                "X-Phase4-Event-Contract-Version": EVENT_VERSION,
                "Last-Event-ID": "0",
            },
            method="GET",
        )
        try:
            with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                capture_id = _capture_id(response.headers)
                data_lines: list[str] = []
                for raw_line in response:
                    line = raw_line.decode("utf-8").rstrip("\r\n")
                    if not line:
                        if data_lines:
                            event = json.loads("\n".join(data_lines))
                            if isinstance(event, dict):
                                with self.condition:
                                    self.events.append(event)
                                    self.condition.notify_all()
                        data_lines = []
                    elif line.startswith("data:"):
                        data_lines.append(line[5:].lstrip(" "))
                with self.condition:
                    self.capture_id = capture_id
        except BaseException as error:  # propagated to the main driver thread
            with self.condition:
                self.error = error
        finally:
            with self.condition:
                self.done = True
                self.condition.notify_all()

    def wait_for(
        self,
        predicate: Callable[[dict[str, Any]], bool],
        *,
        after_sequence: int = 0,
        timeout: float = 300.0,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        with self.condition:
            while True:
                for event in self.events:
                    sequence = event.get("sequence")
                    if type(sequence) is int and sequence > after_sequence and predicate(event):
                        return event
                if self.error is not None:
                    raise DriverError("inventory SSE watcher failed") from self.error
                remaining = deadline - time.monotonic()
                if remaining <= 0 or self.done:
                    raise DriverError("timed out waiting for a real runtime event")
                self.condition.wait(min(remaining, 0.1))

    def wait_idle_after(self, sequence: int, *, idle_seconds: float = 0.2) -> int:
        deadline = time.monotonic() + 5.0
        current = sequence
        while time.monotonic() < deadline:
            with self.condition:
                later = [
                    event["sequence"]
                    for event in self.events
                    if type(event.get("sequence")) is int and event["sequence"] > current
                ]
            if later:
                current = max(later)
                time.sleep(idle_seconds)
                continue
            time.sleep(idle_seconds)
            with self.condition:
                if not any(
                    type(event.get("sequence")) is int and event["sequence"] > current
                    for event in self.events
                ):
                    return current
        raise DriverError("runtime did not reach the expected bounded idle window")

    def finish(self) -> str:
        self.thread.join(TIMEOUT_SECONDS)
        if self.thread.is_alive():
            raise DriverError("success inventory stream did not terminate")
        if self.error is not None or self.capture_id is None:
            raise DriverError("success inventory stream failed") from self.error
        return self.capture_id


def _parallel_projections(
    pool: ThreadPoolExecutor,
    base_url: str,
    run_id: str,
    count: int,
) -> list[tuple[str, dict[str, Any]]]:
    futures = [pool.submit(_capture_projection, base_url, run_id) for _ in range(count)]
    results = [future.result(timeout=30) for future in futures]
    sequences = {_projection_sequence(value) for _, value in results}
    if len(sequences) != 1:
        raise DriverError("parallel projection captures crossed a runtime boundary")
    return results


def _wait_terminal(base_url: str, run_id: str, timeout: float = 300.0) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status, _, value = _json_request(
            base_url,
            "GET",
            f"/api/research-runs/{quote(run_id, safe='')}",
        )
        run_status = _find_string(value, "status")
        if status == 200 and run_status in {"RELEASED", "FAILED", "CANCELLED"}:
            return run_status
        time.sleep(0.25)
    raise DriverError("Run did not reach a terminal state")


def _find_mapping(value: Any, name: str) -> dict[str, Any] | None:
    if isinstance(value, dict):
        candidate = value.get(name)
        if isinstance(candidate, dict):
            return candidate
        for child in value.values():
            found = _find_mapping(child, name)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_mapping(child, name)
            if found is not None:
                return found
    return None


def _run_failure_diagnostic(base_url: str, run_id: str) -> tuple[str, str, str]:
    run_status = "UNKNOWN"
    safe_failure_stage = "NONE"
    safe_failure_code = "NONE"
    try:
        status, _, value = _json_request(
            base_url,
            "GET",
            f"/api/research-runs/{quote(run_id, safe='')}",
        )
        candidate = _find_string(value, "status")
        if status == 200 and candidate in KNOWN_RUN_STATUSES:
            run_status = candidate
    except BaseException:
        pass
    try:
        status, _, value = _json_request(
            base_url,
            "GET",
            f"/api/research-runs/{quote(run_id, safe='')}/projection",
        )
        safe_failure = _find_mapping(value, "safe_failure") if status == 200 else None
        if safe_failure is not None:
            stage = safe_failure.get("failure_stage")
            code = safe_failure.get("failure_code")
            if isinstance(stage, str) and _SAFE_IDENTIFIER.fullmatch(stage):
                safe_failure_stage = stage
            if isinstance(code, str) and _SAFE_IDENTIFIER.fullmatch(code):
                safe_failure_code = code
    except BaseException:
        pass
    return run_status, safe_failure_stage, safe_failure_code


def _all_run_ids(base_url: str) -> list[str]:
    status, _, value = _json_request(base_url, "GET", "/api/research-runs?limit=64")
    if status != 200 or not isinstance(value.get("items"), list):
        raise DriverError("Run collection could not be enumerated")
    result: list[str] = []
    for item in value["items"]:
        run_id = _find_string(item, "run_id")
        if run_id is not None and run_id not in result:
            result.append(run_id)
    return result


def run() -> dict[str, Any]:
    base_url = os.environ.get("VS01_BACKEND_URL")
    output_value = os.environ.get("VS01_EVIDENCE_OUTPUT_PATH")
    if not base_url or not output_value:
        raise DriverError("VS01 gate environment is incomplete")
    output_path = Path(output_value)
    if output_path.exists() or output_path.is_symlink():
        raise DriverError("VS01 capture index target must be fresh")
    checkpoint = FailureCheckpoint(output_path, candidate_sha=_candidate_sha())
    active_run: str | None = None
    active_watcher: EventWatcher | None = None

    try:
        checkpoint.start_stage(
            "RESOLVE_SUCCESS_OBJECT",
            "NVDA research object is available",
            scenario_id="success",
        )
        success_object = _object_id(base_url, "NVDA", "NVIDIA Corporation")
        checkpoint.pass_stage()

        checkpoint.start_stage(
            "CONFIRM_SUCCESS_RUN",
            "one admitted NVDA Run",
            scenario_id="success",
        )
        success_run = _admit_run(base_url, success_object, "success")
        active_run = success_run
        checkpoint.pass_stage()

        watcher = EventWatcher(base_url, success_run)
        active_watcher = watcher
        checkpoint.start_stage(
            "OPEN_SUCCESS_INVENTORY_STREAM",
            "exact-Run SSE stream from cursor 0",
            scenario_id="success",
            run_id=success_run,
            watcher=watcher,
        )
        watcher.start()
        checkpoint.pass_stage(watcher=watcher)

        scenarios: dict[str, Any] = {}
        with ThreadPoolExecutor(max_workers=12) as pool:
            checkpoint.start_stage(
                "WAIT_FOR_FUNDAMENTALS_GROWTH_CALCULATION_COMPLETED",
                "calculation.completed for the fundamentals GROWTH calculation",
                scenario_id="success",
                run_id=success_run,
                watcher=watcher,
            )
            growth = watcher.wait_for(
                lambda event: (
                    event.get("type") == "calculation.completed"
                    and str(event.get("task_id", "")).endswith(":fundamentals")
                    and str(event.get("payload", {}).get("calculation_id", "")).endswith("-GROWTH")
                )
            )
            checkpoint.pass_stage(watcher=watcher)

            checkpoint.start_stage(
                "WAIT_FOR_POST_GROWTH_IDLE",
                "0.2-second event-idle window within 5 seconds after GROWTH",
                scenario_id="success",
                run_id=success_run,
                watcher=watcher,
            )
            watcher.wait_idle_after(growth["sequence"])
            checkpoint.pass_stage(watcher=watcher)

            checkpoint.start_stage(
                "CAPTURE_PRE_CORRECTION_PROJECTIONS",
                "three coherent exact-Run projections before correction resolution",
                scenario_id="success",
                run_id=success_run,
                watcher=watcher,
            )
            correction_before = _parallel_projections(pool, base_url, success_run, 3)
            correction_sequence = _projection_sequence(correction_before[0][1])
            checkpoint.pass_stage(watcher=watcher)

            checkpoint.start_stage(
                "OPEN_CORRECTION_REPLAY_STREAMS",
                "three exact-Run streams after the pre-correction watermark",
                scenario_id="success",
                run_id=success_run,
                watcher=watcher,
            )
            correction_streams: list[Future[str]] = [
                pool.submit(
                    _capture_stream,
                    base_url,
                    success_run,
                    correction_sequence,
                    cut_frames=2,
                )
                for _ in range(3)
            ]
            checkpoint.pass_stage(watcher=watcher)

            checkpoint.start_stage(
                "WAIT_FOR_TASK_CORRECTION_RESOLVED",
                "task.correction_resolved",
                scenario_id="success",
                run_id=success_run,
                watcher=watcher,
            )
            watcher.wait_for(lambda event: event.get("type") == "task.correction_resolved")
            checkpoint.pass_stage(watcher=watcher)

            checkpoint.start_stage(
                "CAPTURE_POST_CORRECTION_PROJECTIONS",
                "three coherent exact-Run projections after correction resolution",
                scenario_id="success",
                run_id=success_run,
                watcher=watcher,
            )
            correction_after = _parallel_projections(pool, base_url, success_run, 3)
            checkpoint.pass_stage(watcher=watcher)

            checkpoint.start_stage(
                "COLLECT_CORRECTION_REPLAY_STREAMS",
                "complete ordering, snapshot-race, and self-correction capture receipts",
                scenario_id="success",
                run_id=success_run,
                watcher=watcher,
            )
            scenarios["ordering_recovery"] = {
                "before_projection": correction_before[0][0],
                "stream": correction_streams[0].result(timeout=30),
                "recovered_projection": correction_after[0][0],
            }
            scenarios["snapshot_race"] = {
                "before_projection": correction_before[1][0],
                "stream": correction_streams[1].result(timeout=30),
                "after_projection": correction_after[1][0],
            }
            scenarios["self_correction"] = {
                "before_projection": correction_before[2][0],
                "stream": correction_streams[2].result(timeout=30),
                "after_projection": correction_after[2][0],
            }
            checkpoint.pass_stage(watcher=watcher)

            checkpoint.start_stage(
                "WAIT_FOR_CAPABILITY_BUILD_STARTED",
                "capability.build_started",
                scenario_id="success",
                run_id=success_run,
                watcher=watcher,
            )
            build_started = watcher.wait_for(
                lambda event: event.get("type") == "capability.build_started"
            )
            checkpoint.pass_stage(watcher=watcher)

            checkpoint.start_stage(
                "WAIT_FOR_POST_BUILD_IDLE",
                "0.2-second event-idle window within 5 seconds after capability build start",
                scenario_id="success",
                run_id=success_run,
                watcher=watcher,
            )
            watcher.wait_idle_after(build_started["sequence"])
            checkpoint.pass_stage(watcher=watcher)

            checkpoint.start_stage(
                "CAPTURE_HEARTBEAT_PROJECTION",
                "exact-Run projection at the capability-build watermark",
                scenario_id="success",
                run_id=success_run,
                watcher=watcher,
            )
            heartbeat_before = _capture_projection(base_url, success_run)
            heartbeat_sequence = _projection_sequence(heartbeat_before[1])
            checkpoint.pass_stage(watcher=watcher)

            checkpoint.start_stage(
                "OPEN_HEARTBEAT_STREAM",
                "one post-watermark SSE frame",
                scenario_id="success",
                run_id=success_run,
                watcher=watcher,
            )
            heartbeat_future = pool.submit(
                _capture_stream,
                base_url,
                success_run,
                heartbeat_sequence,
                cut_frames=1,
            )
            checkpoint.pass_stage(watcher=watcher)

            checkpoint.start_stage(
                "WAIT_FOR_RISK_TASK_STARTED",
                "task.started for the exact Run risk task",
                scenario_id="success",
                run_id=success_run,
                watcher=watcher,
            )
            risk_started = watcher.wait_for(
                lambda event: (
                    event.get("type") == "task.started"
                    and str(event.get("task_id", "")).endswith(":risk")
                )
            )
            checkpoint.pass_stage(watcher=watcher)

            checkpoint.start_stage(
                "WAIT_FOR_PRE_REPLAN_IDLE",
                "0.2-second event-idle window within 5 seconds after risk task start",
                scenario_id="success",
                run_id=success_run,
                watcher=watcher,
            )
            pre_request_sequence = watcher.wait_idle_after(risk_started["sequence"])
            checkpoint.pass_stage(watcher=watcher)

            checkpoint.start_stage(
                "CAPTURE_PRE_REPLAN_PROJECTIONS",
                "two exact-Run projections at the pre-Replan watermark",
                scenario_id="success",
                run_id=success_run,
                watcher=watcher,
            )
            request_before = _parallel_projections(pool, base_url, success_run, 2)
            if _projection_sequence(request_before[0][1]) != pre_request_sequence:
                raise DriverError("pre-Replan projection missed its exact watermark")
            checkpoint.pass_stage(watcher=watcher)

            checkpoint.start_stage(
                "OPEN_REPLAN_REQUEST_STREAMS",
                "two exact-Run streams after the pre-Replan watermark",
                scenario_id="success",
                run_id=success_run,
                watcher=watcher,
            )
            request_streams = [
                pool.submit(
                    _capture_stream,
                    base_url,
                    success_run,
                    pre_request_sequence,
                    cut_frames=1,
                )
                for _ in range(2)
            ]
            checkpoint.pass_stage(watcher=watcher)

            checkpoint.start_stage(
                "WAIT_FOR_REPLAN_REQUESTED",
                "replan.requested after the pre-Replan watermark",
                scenario_id="success",
                run_id=success_run,
                watcher=watcher,
            )
            requested = watcher.wait_for(
                lambda event: event.get("type") == "replan.requested",
                after_sequence=pre_request_sequence,
            )
            checkpoint.pass_stage(watcher=watcher)

            checkpoint.start_stage(
                "CAPTURE_REPLAN_PENDING_PROJECTIONS",
                "two exact-Run projections at the requested Replan watermark",
                scenario_id="success",
                run_id=success_run,
                watcher=watcher,
            )
            pending_projections = _parallel_projections(pool, base_url, success_run, 2)
            pending_sequence = _projection_sequence(pending_projections[0][1])
            if pending_sequence != requested["sequence"]:
                raise DriverError("pending Replan projection missed its exact watermark")
            checkpoint.pass_stage(watcher=watcher)

            checkpoint.start_stage(
                "OPEN_REPLAN_APPROVAL_STREAM",
                "exact-Run stream after the requested Replan watermark",
                scenario_id="success",
                run_id=success_run,
                watcher=watcher,
            )
            approved_stream = pool.submit(
                _capture_stream,
                base_url,
                success_run,
                pending_sequence,
                cut_frames=6,
            )
            checkpoint.pass_stage(watcher=watcher)

            checkpoint.start_stage(
                "WAIT_FOR_REPLAN_APPROVED",
                "replan.approved after the requested Replan watermark",
                scenario_id="success",
                run_id=success_run,
                watcher=watcher,
            )
            approved = watcher.wait_for(
                lambda event: event.get("type") == "replan.approved",
                after_sequence=pending_sequence,
            )
            checkpoint.pass_stage(watcher=watcher)

            checkpoint.start_stage(
                "CAPTURE_REPLAN_APPROVED_PROJECTION",
                "exact-Run projection at the approved Replan watermark",
                scenario_id="success",
                run_id=success_run,
                watcher=watcher,
            )
            approved_projection = _capture_projection(base_url, success_run)
            if _projection_sequence(approved_projection[1]) != approved["sequence"]:
                raise DriverError("approved Replan projection missed its exact watermark")
            checkpoint.pass_stage(watcher=watcher)

            checkpoint.start_stage(
                "WAIT_FOR_SYNTHESIS_EDGE_ADDED",
                "graph.edge_added targeting the synthesis task",
                scenario_id="success",
                run_id=success_run,
                watcher=watcher,
            )
            last_edge = watcher.wait_for(
                lambda event: (
                    event.get("type") == "graph.edge_added"
                    and str(event.get("task_id", "")).endswith(":synthesis")
                ),
                after_sequence=approved["sequence"],
            )
            checkpoint.pass_stage(watcher=watcher)

            checkpoint.start_stage(
                "CAPTURE_SPARSE_GRAPH_PROJECTION",
                "exact-Run projection at the last graph-edge watermark",
                scenario_id="success",
                run_id=success_run,
                watcher=watcher,
            )
            sparse_before = _capture_projection(base_url, success_run)
            if _projection_sequence(sparse_before[1]) != last_edge["sequence"]:
                raise DriverError("sparse graph projection missed its exact watermark")
            checkpoint.pass_stage(watcher=watcher)

            checkpoint.start_stage(
                "OPEN_GRAPH_VERSION_STREAM",
                "one exact-Run frame after the last graph edge",
                scenario_id="success",
                run_id=success_run,
                watcher=watcher,
            )
            sparse_stream = pool.submit(
                _capture_stream,
                base_url,
                success_run,
                last_edge["sequence"],
                cut_frames=1,
            )
            checkpoint.pass_stage(watcher=watcher)

            checkpoint.start_stage(
                "WAIT_FOR_GRAPH_VERSION_CHANGED",
                "graph.version_changed after the final graph edge",
                scenario_id="success",
                run_id=success_run,
                watcher=watcher,
            )
            version = watcher.wait_for(
                lambda event: event.get("type") == "graph.version_changed",
                after_sequence=last_edge["sequence"],
            )
            checkpoint.pass_stage(watcher=watcher)

            checkpoint.start_stage(
                "CAPTURE_FINAL_REPLAN_PROJECTIONS",
                "two exact-Run projections at the graph-version watermark",
                scenario_id="success",
                run_id=success_run,
                watcher=watcher,
            )
            final_replan = _parallel_projections(pool, base_url, success_run, 2)
            if _projection_sequence(final_replan[0][1]) != version["sequence"]:
                raise DriverError("graph-version projection missed its exact watermark")
            checkpoint.pass_stage(watcher=watcher)

            checkpoint.start_stage(
                "COLLECT_REPLAN_STREAMS",
                "complete duplicate, Replan, sparse-graph, and heartbeat capture receipts",
                scenario_id="success",
                run_id=success_run,
                watcher=watcher,
            )
            scenarios["duplicate"] = {
                "before_projection": request_before[0][0],
                "stream": request_streams[0].result(timeout=30),
            }
            scenarios["replan_pending"] = {
                "before_projection": request_before[1][0],
                "stream": request_streams[1].result(timeout=30),
                "after_projection": pending_projections[0][0],
            }
            scenarios["replan_approved"] = {
                "before_projection": pending_projections[1][0],
                "stream": approved_stream.result(timeout=30),
                "after_projection": final_replan[0][0],
            }
            scenarios["sparse_graph_refresh"] = {
                "before_projection": sparse_before[0],
                "stream": sparse_stream.result(timeout=30),
                "after_projection": final_replan[1][0],
            }
            scenarios["heartbeat"] = {
                "before_projection": heartbeat_before[0],
                "stream": heartbeat_future.result(timeout=30),
            }
            checkpoint.pass_stage(watcher=watcher)

        checkpoint.start_stage(
            "WAIT_FOR_SUCCESS_RUN_RELEASED",
            "success Run reaches RELEASED",
            scenario_id="success",
            run_id=success_run,
            watcher=watcher,
        )
        success_status = _wait_terminal(base_url, success_run)
        checkpoint.update_run_status(success_status)
        if success_status != "RELEASED":
            raise DriverError("real success scenario did not release")
        checkpoint.pass_stage(watcher=watcher)

        checkpoint.start_stage(
            "FINISH_SUCCESS_INVENTORY_STREAM",
            "success exact-Run inventory stream terminates with a capture identifier",
            scenario_id="success",
            run_id=success_run,
            watcher=watcher,
        )
        success_inventory = watcher.finish()
        checkpoint.pass_stage(watcher=watcher)

        active_watcher = None
        checkpoint.start_stage(
            "RESOLVE_CONTROLLED_FAILURE_OBJECT",
            "invalid-symbol research object is available",
            scenario_id="controlled_failure",
        )
        failure_object = _object_id(base_url, "ZZVS01", "VS01 Invalid Symbol Probe")
        checkpoint.pass_stage()

        checkpoint.start_stage(
            "CONFIRM_CONTROLLED_FAILURE_RUN",
            "one admitted invalid-symbol Run",
            scenario_id="controlled_failure",
        )
        failure_run = _admit_run(base_url, failure_object, "failure")
        active_run = failure_run
        checkpoint.pass_stage()

        checkpoint.start_stage(
            "WAIT_FOR_CONTROLLED_FAILURE_TERMINAL",
            "invalid-symbol Run reaches FAILED",
            scenario_id="controlled_failure",
            run_id=failure_run,
        )
        failure_status = _wait_terminal(base_url, failure_run)
        checkpoint.update_run_status(failure_status)
        if failure_status != "FAILED":
            raise DriverError("controlled invalid-symbol Run did not fail closed")
        checkpoint.pass_stage()

        checkpoint.start_stage(
            "CAPTURE_CONTROLLED_FAILURE_STREAM",
            "complete exact-Run terminal failure stream",
            scenario_id="controlled_failure",
            run_id=failure_run,
        )
        scenarios["terminal_failure"] = {
            "stream": _capture_stream(base_url, failure_run, 0),
        }
        checkpoint.pass_stage()

        checkpoint.start_stage(
            "CAPTURE_EVENT_INVENTORY",
            "terminal exact-Run streams covering the runtime event inventory",
            scenario_id="event_inventory",
            run_id=failure_run,
        )
        inventory_streams = [success_inventory, _capture_stream(base_url, failure_run, 0)]
        already = {success_run, failure_run}
        for run_id in _all_run_ids(base_url):
            if run_id in already:
                continue
            active_run = run_id
            _wait_terminal(base_url, run_id)
            inventory_streams.append(_capture_stream(base_url, run_id, 0))
            if len(inventory_streams) == 64:
                break
        scenarios["event_inventory"] = {"streams": inventory_streams}
        checkpoint.pass_stage()

        result = {
            "schema_version": "phase4-vs01-runtime-sse-capture-index/v1",
            "scenarios": scenarios,
        }
        checkpoint.start_stage(
            "WRITE_FINAL_CAPTURE_INDEX",
            "normal immutable runtime SSE capture index",
            scenario_id="finalize",
            run_id=failure_run,
        )
        _write_final_index(output_path, result)
        checkpoint.pass_stage()
        checkpoint.discard()
        return result
    except BaseException as error:
        run_status = "UNKNOWN"
        safe_failure_stage = "NONE"
        safe_failure_code = "NONE"
        if active_run is not None:
            run_status, safe_failure_stage, safe_failure_code = _run_failure_diagnostic(
                base_url,
                active_run,
            )
        try:
            checkpoint.fail(
                error,
                watcher=active_watcher,
                run_status=run_status,
                safe_failure_stage=safe_failure_stage,
                safe_failure_code=safe_failure_code,
            )
        except BaseException:
            pass
        raise


if __name__ == "__main__":
    run()
