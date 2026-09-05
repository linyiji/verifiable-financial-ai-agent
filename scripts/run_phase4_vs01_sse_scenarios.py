#!/usr/bin/env python3
"""Capture real Phase 4 VS01 projection/SSE scenario receipts through the gate proxy.

The driver writes only gate-issued capture identifiers.  Response bodies remain in
the gate-owned in-memory ledger and are reconstructed and validated by X.
"""

from __future__ import annotations

import json
import os
import secrets
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


class DriverError(RuntimeError):
    pass


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
        name: draft.get(name)
        for name in ("draft_id", "draft_version", "draft_hash", "object_id")
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

    success_object = _object_id(base_url, "NVDA", "NVIDIA Corporation")
    success_run = _admit_run(base_url, success_object, "success")
    watcher = EventWatcher(base_url, success_run)
    watcher.start()

    scenarios: dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=12) as pool:
        growth = watcher.wait_for(
            lambda event: event.get("type") == "calculation.completed"
            and str(event.get("task_id", "")).endswith(":fundamentals")
            and str(event.get("payload", {}).get("calculation_id", "")).endswith("-GROWTH")
        )
        watcher.wait_idle_after(growth["sequence"])
        correction_before = _parallel_projections(pool, base_url, success_run, 3)
        correction_sequence = _projection_sequence(correction_before[0][1])
        correction_streams: list[Future[str]] = [
            pool.submit(_capture_stream, base_url, success_run, correction_sequence, cut_frames=2)
            for _ in range(3)
        ]
        watcher.wait_for(lambda event: event.get("type") == "task.correction_resolved")
        correction_after = _parallel_projections(pool, base_url, success_run, 3)
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

        build_started = watcher.wait_for(
            lambda event: event.get("type") == "capability.build_started"
        )
        watcher.wait_idle_after(build_started["sequence"])
        heartbeat_before = _capture_projection(base_url, success_run)
        heartbeat_sequence = _projection_sequence(heartbeat_before[1])
        heartbeat_future = pool.submit(
            _capture_stream,
            base_url,
            success_run,
            heartbeat_sequence,
            cut_frames=1,
        )

        risk_started = watcher.wait_for(
            lambda event: event.get("type") == "task.started"
            and str(event.get("task_id", "")).endswith(":risk")
        )
        pre_request_sequence = watcher.wait_idle_after(risk_started["sequence"])
        request_before = _parallel_projections(pool, base_url, success_run, 2)
        if _projection_sequence(request_before[0][1]) != pre_request_sequence:
            raise DriverError("pre-Replan projection missed its exact watermark")
        request_streams = [
            pool.submit(_capture_stream, base_url, success_run, pre_request_sequence, cut_frames=1)
            for _ in range(2)
        ]
        requested = watcher.wait_for(
            lambda event: event.get("type") == "replan.requested",
            after_sequence=pre_request_sequence,
        )
        pending_projections = _parallel_projections(pool, base_url, success_run, 2)
        pending_sequence = _projection_sequence(pending_projections[0][1])
        if pending_sequence != requested["sequence"]:
            raise DriverError("pending Replan projection missed its exact watermark")
        approved_stream = pool.submit(
            _capture_stream, base_url, success_run, pending_sequence, cut_frames=6
        )
        approved = watcher.wait_for(
            lambda event: event.get("type") == "replan.approved",
            after_sequence=pending_sequence,
        )
        approved_projection = _capture_projection(base_url, success_run)
        if _projection_sequence(approved_projection[1]) != approved["sequence"]:
            raise DriverError("approved Replan projection missed its exact watermark")

        last_edge = watcher.wait_for(
            lambda event: event.get("type") == "graph.edge_added"
            and str(event.get("task_id", "")).endswith(":synthesis"),
            after_sequence=approved["sequence"],
        )
        sparse_before = _capture_projection(base_url, success_run)
        if _projection_sequence(sparse_before[1]) != last_edge["sequence"]:
            raise DriverError("sparse graph projection missed its exact watermark")
        sparse_stream = pool.submit(
            _capture_stream, base_url, success_run, last_edge["sequence"], cut_frames=1
        )
        version = watcher.wait_for(
            lambda event: event.get("type") == "graph.version_changed",
            after_sequence=last_edge["sequence"],
        )
        final_replan = _parallel_projections(pool, base_url, success_run, 2)
        if _projection_sequence(final_replan[0][1]) != version["sequence"]:
            raise DriverError("graph-version projection missed its exact watermark")

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

    if _wait_terminal(base_url, success_run) != "RELEASED":
        raise DriverError("real success scenario did not release")
    success_inventory = watcher.finish()

    failure_object = _object_id(base_url, "ZZVS01", "VS01 Invalid Symbol Probe")
    failure_run = _admit_run(base_url, failure_object, "failure")
    failure_status = _wait_terminal(base_url, failure_run)
    if failure_status != "FAILED":
        raise DriverError("controlled invalid-symbol Run did not fail closed")
    scenarios["terminal_failure"] = {
        "stream": _capture_stream(base_url, failure_run, 0),
    }

    inventory_streams = [success_inventory, _capture_stream(base_url, failure_run, 0)]
    already = {success_run, failure_run}
    for run_id in _all_run_ids(base_url):
        if run_id in already:
            continue
        _wait_terminal(base_url, run_id)
        inventory_streams.append(_capture_stream(base_url, run_id, 0))
        if len(inventory_streams) == 64:
            break
    scenarios["event_inventory"] = {"streams": inventory_streams}

    result = {
        "schema_version": "phase4-vs01-runtime-sse-capture-index/v1",
        "scenarios": scenarios,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


if __name__ == "__main__":
    run()
