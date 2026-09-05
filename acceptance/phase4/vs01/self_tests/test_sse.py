from __future__ import annotations

import hashlib
import json
from collections.abc import AsyncIterator, Mapping
from copy import deepcopy
from dataclasses import replace
from typing import Any

import pytest

from acceptance.phase4.vs01.harness.sse import (
    CORE_CONTRACT_VERSION,
    ERROR_HTTP_MAP,
    EVENT_CONTRACT_VERSION,
    EVENT_EFFECT,
    RAW_EVENT_TYPES,
    SUPPORTED_V1_EVENTS,
    UNSUPPORTED_V1_EVENTS,
    CursorDisposition,
    EventDisposition,
    IncrementalSSEParser,
    LiveStreamObservation,
    SSEAcceptanceError,
    SSEBusinessFrame,
    SSECommentFrame,
    SSEProjectionOracle,
    assert_controlled_replan,
    assert_cursor_error_response,
    assert_disconnect_retains_business_snapshot,
    assert_exact_run_event_url,
    assert_numeric_opaque_suffix_equal,
    assert_numeric_resume,
    assert_replay_suffix_matches_baseline,
    assert_research_path_projection,
    assert_self_correction_same_task_same_graph,
    assert_sse_success_headers,
    assert_terminal_cursor_response,
    assert_terminal_stream,
    collect_live_sse,
    parse_sse_bytes,
    resolve_cursor,
    validate_error_envelope,
    validate_run_projection,
    validate_runtime_event,
)

RUN_ID = "RUN-A"
OBJECT_ID = "OBJ-A"
NOW = "2026-09-05T07:00:00Z"


PAYLOAD_SAMPLES: dict[str, dict[str, Any]] = {
    "run.created": {"object_id": OBJECT_ID},
    "run.started": {},
    "run.status_changed": {"status": "RUNNING"},
    "run.completed": {"status": "RELEASED"},
    "run.failed": {
        "status": "FAILED",
        "failure_stage": "TASK_EXECUTION",
        "failure_code": "TASK_EXECUTION_FAILED",
    },
    "scheme.generated": {
        "scheme_id": "SCHEME-A",
        "generated_by": "research_lead_agent",
        "generated_at": NOW,
        "generation_stage": "PREPARE",
        "retrospective": False,
    },
    "scheme.confirmed": {"scheme_id": "SCHEME-A"},
    "plan.generated": {"graph_id": "GRAPH-PLAN-A", "task_count": 1},
    "task.created": {"task_type": "fundamental"},
    "task.ready": {},
    "task.started": {"attempt": 1},
    "task.progress": {"progress": 0.25, "progress_scale": "RATIO_0_1"},
    "task.waiting_for_capability": {"gap_id": "GAP-A"},
    "task.resumed": {"gap_id": "GAP-A", "registration_id": "REG-A", "status": "RUNNING"},
    "task.self_correcting": {"problem_code": "PERIOD_MISMATCH"},
    "task.correction_resolved": {"correction_id": "CORRECTION-A"},
    "task.completed": {"attempt": 1, "result_ref": "RESULT-A"},
    "task.failed": {"attempt": 1, "failure_code": "TASK_FAILED"},
    "replan.requested": {"replan_id": "REPLAN-A", "decision": "PENDING"},
    "replan.approved": {"replan_id": "REPLAN-A", "decided_by": "research-lead"},
    "graph.task_added": {"replan_id": "REPLAN-A"},
    "graph.edge_added": {
        "replan_id": "REPLAN-A",
        "source_task_id": "TASK-A",
        "target_task_id": "TASK-B",
    },
    "graph.edge_removed": {
        "replan_id": "REPLAN-A",
        "source_task_id": "TASK-A",
        "target_task_id": "TASK-B",
    },
    "graph.version_changed": {"replan_id": "REPLAN-A", "version_before": 1},
    "evidence.accepted": {"evidence_id": "EVD-A", "field": "revenue"},
    "calculation.started": {"capability_id": "revenue_growth"},
    "calculation.completed": {
        "calculation_id": "CALC-A",
        "capability_id": "revenue_growth",
    },
    "capability.gap_detected": {
        "gap_id": "GAP-A",
        "capability_id": "CAP-A",
        "skill_id": "SKILL-A",
        "requested_by": "TASK-A",
    },
    "capability.build_requested": {
        "gap_id": "GAP-A",
        "build_id": "BUILD-A",
        "attempt": 1,
        "max_attempts": 2,
        "approved_by": "research-lead",
    },
    "capability.build_started": {"build_id": "BUILD-A", "attempt": 1},
    "capability.generated": {
        "build_id": "BUILD-A",
        "generated_capability_id": "GCAP-A",
        "implementation_hash": "sha256:abc",
    },
    "capability.static_validated": {
        "build_id": "BUILD-A",
        "implementation_hash": "sha256:abc",
    },
    "capability.sandbox_started": {
        "build_id": "BUILD-A",
        "implementation_hash": "sha256:abc",
    },
    "capability.test_passed": {
        "build_id": "BUILD-A",
        "implementation_hash": "sha256:abc",
    },
    "capability.test_failed": {
        "build_id": "BUILD-A",
        "attempt": 1,
        "failure_code": "TEST_FAILED",
    },
    "capability.financial_validated": {
        "build_id": "BUILD-A",
        "implementation_hash": "sha256:abc",
    },
    "capability.approved": {
        "build_id": "BUILD-A",
        "registration_id": "REG-A",
        "approved_by": "research-lead",
        "scope": "RUN",
    },
    "capability.registered": {
        "registration_id": "REG-A",
        "capability_id": "CAP-A",
        "capability_version": "1",
        "scope": "RUN",
    },
    "capability.build_failed": {"failure_code": "BUILD_FAILED", "terminal": True},
    "review.started": {},
    "review.resolved": {"review_id": "REVIEW-A", "status": "PASS"},
    "proof.required": {
        "proof_id": "PROOF-A",
        "calculation_id": "CALC-A",
        "formula_id": "FORMULA-A",
        "policy_id": "POLICY-A",
    },
    "proof.started": {"proof_id": "PROOF-A", "backend": "risc0"},
    "proof.generated": {"proof_id": "PROOF-A", "backend": "risc0"},
    "proof.verified": {
        "proof_id": "PROOF-A",
        "image_id": "IMAGE-A",
        "receipt_hash": "sha256:receipt",
        "journal_hash": "sha256:journal",
        "verified": True,
        "dev_mode": False,
    },
    "proof.failed": {"proof_id": "PROOF-A", "failure_code": "PROOF_FAILED", "status": "FAILED"},
    "release.completed": {"canonical_record_id": "CER-A", "result_id": "RELEASED-A"},
}


def _task(
    task_id: str, dependencies: list[str] | None = None, status: str = "RUNNING"
) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "run_id": RUN_ID,
        "status": status,
        "progress": 1.0 if status == "COMPLETED" else 0.25,
        "parent_task_id": None,
        "dependencies": dependencies or [],
        "task_type": "fundamental",
        "goal": "authoritative goal",
    }


def _snapshot(
    *,
    sequence: int = 0,
    revision: int = 1,
    graph_version: int = 1,
    tasks: list[dict[str, Any]] | None = None,
    path_changes: list[dict[str, Any]] | None = None,
    status: str = "RUNNING",
    terminal_event_id: str | None = None,
) -> dict[str, Any]:
    task_rows = deepcopy(tasks or [_task("TASK-A")])
    terminal = status in {"RELEASED", "FAILED", "CANCELLED"}
    outcome = {"RELEASED": "SUCCESS", "FAILED": "FAILURE", "CANCELLED": "CANCELLED"}.get(status)
    planned_tasks = [
        {**deepcopy(task), "status": "CREATED"}
        for task in task_rows
        if not task.get("origin") or task.get("origin") == "PLAN"
    ]
    planned_edges = [
        {"source_task_id": dependency, "target_task_id": task["task_id"]}
        for task in planned_tasks
        for dependency in task["dependencies"]
    ]
    actual_edges = [
        {"source_task_id": dependency, "target_task_id": task["task_id"]}
        for task in task_rows
        for dependency in task["dependencies"]
    ]
    return {
        "projection_schema_version": "phase4-run-projection/v1",
        "projection_revision": revision,
        "projection_sequence": sequence,
        "generated_at": NOW,
        "object": {
            "object_id": OBJECT_ID,
            "symbol": "NVDA",
            "company_name": "NVIDIA",
            "object_type": "public_company",
            "exchange": "NASDAQ",
            "sector": None,
            "currency": "USD",
            "identity_version": 1,
        },
        "run": {
            "run_id": RUN_ID,
            "research_object_id": OBJECT_ID,
            "goal_id": "GOAL-A",
            "scheme_id": "SCHEME-A",
            "status": status,
            "stage": {
                "RUNNING": "RESEARCH",
                "RELEASED": "COMPLETE",
                "FAILED": "FAILED",
                "CANCELLED": "CANCELLED",
            }.get(status, status),
            "as_of": "2026-09-05",
            "planned_graph_id": "GRAPH-PLAN-A",
            "actual_graph_id": "GRAPH-ACTUAL-A",
            "execution_target": "SERVER_SANDBOX",
            "created_at": NOW,
            "started_at": NOW,
            "completed_at": NOW if terminal else None,
            "updated_at": NOW,
        },
        "goal": {"goal_id": "GOAL-A", "research_object_id": OBJECT_ID},
        "confirmed_scheme": {
            "scheme_id": "SCHEME-A",
            "goal_id": "GOAL-A",
            "research_object_id": OBJECT_ID,
            "confirmed_at": NOW,
        },
        "planned_graph": {
            "graph_id": "GRAPH-PLAN-A",
            "run_id": RUN_ID,
            "version": 1,
            "tasks": planned_tasks,
            "edges": planned_edges,
        },
        "actual_graph": {
            "graph_id": "GRAPH-ACTUAL-A",
            "run_id": RUN_ID,
            "version": graph_version,
            "tasks": deepcopy(task_rows),
            "edges": actual_edges,
        },
        "graph_version": graph_version,
        "tasks": task_rows,
        "path_changes": deepcopy(path_changes or []),
        "activity": [],
        "lifecycle": {
            "status": status,
            "stage": {
                "RUNNING": "RESEARCH",
                "RELEASED": "COMPLETE",
                "FAILED": "FAILED",
                "CANCELLED": "CANCELLED",
            }.get(status, status),
            "progress": {
                "method": "ACTUAL_TASK_MEAN_V1",
                "completed_tasks": sum(task["status"] == "COMPLETED" for task in task_rows),
                "total_tasks": len(task_rows),
                "fraction": sum(task["progress"] for task in task_rows) / len(task_rows),
            },
            "terminal": terminal,
            "terminal_outcome": outcome,
            "safe_failure": {"failure_code": "ACCEPTANCE_FAILURE"} if status == "FAILED" else None,
        },
        "review": {
            "availability": {
                "status": "PENDING",
                "reason_code": "RUN_NONTERMINAL",
                "retryable": False,
            },
            "review_id": None,
            "status": None,
        },
        "result": {
            "availability": {
                "status": "PENDING",
                "reason_code": "RUN_NONTERMINAL",
                "retryable": False,
            },
            "released_result_id": None,
            "canonical_record_id": None,
            "released_at": None,
        },
        "artifacts": {
            "availability": {
                "status": "NOT_GENERATED",
                "reason_code": "RUN_NONTERMINAL",
                "retryable": False,
            },
            "report_id": None,
            "representation_ids": [],
        },
        "proof": {
            "availability": {
                "status": "NOT_GENERATED",
                "reason_code": "RUN_NONTERMINAL",
                "retryable": False,
            },
            "policy": "UNKNOWN",
            "status": None,
            "proof_refs": [],
        },
        "execution": {
            "availability": {
                "status": "NOT_GENERATED",
                "reason_code": "RUN_NONTERMINAL",
                "retryable": False,
            },
            "canonical_record_id": None,
        },
        "terminal": {
            "is_terminal": terminal,
            "outcome": outcome,
            "event_id": terminal_event_id if terminal else None,
            "sequence": sequence if terminal else None,
        },
    }


def _path_change(
    source_id: str,
    *,
    source_kind: str,
    change_kind: str,
    decision: str | None,
    task_refs: list[str],
    operations: list[dict[str, Any]] | None = None,
    before: int | None = None,
    after: int | None = None,
) -> dict[str, Any]:
    return {
        "path_change_id": source_id,
        "source_kind": source_kind,
        "source_id": source_id,
        "change_kind": change_kind,
        "status": "RESOLVED" if source_kind == "CORRECTION" else (decision or "PENDING"),
        "decision": decision,
        "reason_code": "ACCEPTANCE_REASON",
        "task_refs": task_refs,
        "operations": operations or [],
        "graph_version_before": before,
        "graph_version_after": after,
        "created_at": NOW,
        "resolved_at": NOW
        if decision in {"APPROVED", "REJECTED"} or source_kind == "CORRECTION"
        else None,
    }


def _event_dict(
    event_type: str,
    sequence: int,
    *,
    payload: Mapping[str, Any] | None = None,
    run_id: str = RUN_ID,
    event_id: str | None = None,
    task_id: str | None = None,
    graph_version: int | None = None,
) -> dict[str, Any]:
    if task_id is None and (
        event_type.startswith("task.")
        or event_type.startswith("capability.")
        or event_type.startswith("replan.")
    ):
        task_id = "TASK-A"
    if graph_version is None and (event_type == "run.started" or event_type.startswith("graph.")):
        graph_version = 2 if event_type.startswith("graph.") else 1
    return {
        "event_contract_version": EVENT_CONTRACT_VERSION,
        "event_id": event_id or f"EVT-{sequence}",
        "run_id": run_id,
        "task_id": task_id,
        "type": event_type,
        "timestamp": NOW,
        "sequence": sequence,
        "payload_schema_version": 1,
        "payload": deepcopy(dict(payload if payload is not None else PAYLOAD_SAMPLES[event_type])),
        "graph_version": graph_version,
        "effect": EVENT_EFFECT.get(event_type, "OBSERVATION_ONLY"),
        "projection_refresh_required": EVENT_EFFECT.get(event_type)
        in {
            "REFRESH_PROJECTION",
            "TERMINAL",
        },
    }


def _frame(
    event_type: str,
    sequence: int,
    **kwargs: Any,
) -> SSEBusinessFrame:
    event = _event_dict(event_type, sequence, **kwargs)
    data = json.dumps(event, sort_keys=True, separators=(",", ":"))
    raw = f"id: {sequence}\nevent: {event_type}\ndata: {data}\n\n".encode()
    parsed = parse_sse_bytes([raw])
    assert len(parsed) == 1 and isinstance(parsed[0], SSEBusinessFrame)
    return parsed[0]


def _validated(event_type: str, sequence: int, **kwargs: Any):
    return validate_runtime_event(_frame(event_type, sequence, **kwargs), expected_run_id=RUN_ID)


def _headers() -> dict[str, str]:
    return {
        "Content-Type": "text/event-stream; charset=utf-8",
        "Cache-Control": "no-cache",
        "X-Phase4-Contract-Version": CORE_CONTRACT_VERSION,
        "X-Phase4-Event-Contract-Version": EVENT_CONTRACT_VERSION,
    }


class _Response:
    def __init__(self, chunks: list[bytes], *, headers: Mapping[str, str] | None = None) -> None:
        self.status_code = 200
        self.headers = dict(headers or _headers())
        self._chunks = chunks

    async def aiter_bytes(self) -> AsyncIterator[bytes]:
        for chunk in self._chunks:
            yield chunk


def _observation(
    events: list[Any],
    *,
    cursor: str | None,
    exhausted: bool = True,
) -> LiveStreamObservation:
    return LiveStreamObservation(
        requested_run_id=RUN_ID,
        requested_cursor=cursor,
        status_code=200,
        headers=_headers(),
        frames=(),
        events=tuple(events),
        dispositions=(),
        stream_exhausted=exhausted,
    )


def test_frozen_event_inventory_and_effect_partition_are_total() -> None:
    assert len(RAW_EVENT_TYPES) == 55
    assert len(SUPPORTED_V1_EVENTS) == 47
    assert len(UNSUPPORTED_V1_EVENTS) == 8
    assert set(EVENT_EFFECT) == set(SUPPORTED_V1_EVENTS)
    assert set(PAYLOAD_SAMPLES) == set(SUPPORTED_V1_EVENTS)


def test_parser_preserves_exact_bytes_across_utf8_crlf_and_chunk_splits() -> None:
    raw = (
        b": heartbeat\r\nid: 1\r\nevent: task.progress\r\n"
        b'data: {"note":"\xe8\xb4\xa2",\r\ndata: "ok":true}\r\n\r\n'
    )
    chunks = [raw[:3], raw[3:39], raw[39:62], raw[62:64], raw[64:]]
    parser = IncrementalSSEParser()
    frames = []
    for chunk in chunks:
        frames.extend(parser.feed(chunk))
    parser.finish()
    assert len(frames) == 1
    frame = frames[0]
    assert isinstance(frame, SSEBusinessFrame)
    assert frame.data == '{"note":"财",\n"ok":true}'
    assert frame.raw_bytes == raw
    assert frame.sha256 == hashlib.sha256(raw).hexdigest()


def test_parser_emits_heartbeat_comment_without_business_event() -> None:
    frames = parse_sse_bytes([b": heartbeat\n\n"])
    assert len(frames) == 1
    assert isinstance(frames[0], SSECommentFrame)
    assert frames[0].comments == (" heartbeat",)


def test_parser_rejects_truncated_frame_and_invalid_utf8() -> None:
    parser = IncrementalSSEParser()
    parser.feed(b"data: {}\n")
    with pytest.raises(SSEAcceptanceError, match="incomplete SSE frame"):
        parser.finish()
    with pytest.raises(SSEAcceptanceError, match="valid UTF-8"):
        parse_sse_bytes([b"data: \xff\n\n"])


@pytest.mark.parametrize("event_type", sorted(SUPPORTED_V1_EVENTS))
def test_every_supported_event_has_an_exact_admitted_payload(event_type: str) -> None:
    event = validate_runtime_event(_frame(event_type, 1), expected_run_id=RUN_ID)
    assert event.type == event_type
    assert event.effect == EVENT_EFFECT[event_type]


@pytest.mark.parametrize("event_type", sorted(UNSUPPORTED_V1_EVENTS))
def test_declared_but_unsupported_event_is_quarantined(event_type: str) -> None:
    event = _event_dict("task.ready", 1)
    event.update(type=event_type, task_id=None, effect="OBSERVATION_ONLY")
    data = json.dumps(event, separators=(",", ":"), sort_keys=True)
    raw = f"id: 1\nevent: {event_type}\ndata: {data}\n\n".encode()
    frame = parse_sse_bytes([raw])[0]
    assert isinstance(frame, SSEBusinessFrame)
    with pytest.raises(SSEAcceptanceError) as failure:
        validate_runtime_event(frame, expected_run_id=RUN_ID)
    assert failure.value.code == "UNSUPPORTED_EVENT"


def test_envelope_rejects_wrong_run_wire_fields_version_effect_and_unsafe_payload() -> None:
    cases = [
        _frame("task.ready", 1, run_id="RUN-B"),
        _frame("task.ready", 1),
        _frame("task.ready", 1),
        _frame("task.ready", 1),
    ]
    with pytest.raises(SSEAcceptanceError) as wrong_run:
        validate_runtime_event(cases[0], expected_run_id=RUN_ID)
    assert wrong_run.value.code == "IDENTITY_MISMATCH"

    def mutate(frame: SSEBusinessFrame, **updates: Any) -> SSEBusinessFrame:
        body = json.loads(frame.data)
        body.update(updates)
        data = json.dumps(body, separators=(",", ":"), sort_keys=True)
        raw = f"id: 1\nevent: task.ready\ndata: {data}\n\n".encode()
        result = parse_sse_bytes([raw])[0]
        assert isinstance(result, SSEBusinessFrame)
        return result

    with pytest.raises(SSEAcceptanceError):
        validate_runtime_event(
            mutate(cases[1], event_contract_version="v2"), expected_run_id=RUN_ID
        )
    with pytest.raises(SSEAcceptanceError):
        validate_runtime_event(mutate(cases[2], effect="OBSERVATION_ONLY"), expected_run_id=RUN_ID)
    unsafe = mutate(cases[3], payload={"authorization": "Bearer value"})
    with pytest.raises(SSEAcceptanceError):
        validate_runtime_event(unsafe, expected_run_id=RUN_ID)


def test_task_progress_variants_are_exact_and_non_guessing() -> None:
    _validated(
        "task.progress",
        1,
        payload={"progress": 0.5, "progress_scale": "RATIO_0_1", "message_code": "HALF"},
    )
    _validated("task.progress", 2, payload={"attempt": 1, "error_code": "TRANSIENT"})
    with pytest.raises(SSEAcceptanceError):
        _validated("task.progress", 3, payload={"progress": 50, "progress_scale": "PERCENT"})


def test_terminal_failure_requires_frozen_stage_vocabulary() -> None:
    _validated(
        "run.failed",
        1,
        payload={
            "status": "FAILED",
            "failure_stage": "PLANNING",
            "failure_code": "PLANNING_FAILED",
            "safe_message": None,
        },
    )
    for payload in (
        {"status": "FAILED", "failure_code": "PLANNING_FAILED"},
        {
            "status": "FAILED",
            "failure_stage": "UNKNOWN",
            "failure_code": "PLANNING_FAILED",
        },
        {
            "status": "CANCELLED",
            "failure_stage": "TASK_EXECUTION",
            "failure_code": "RUN_CANCELLED",
        },
    ):
        with pytest.raises(SSEAcceptanceError) as failure:
            _validated("run.failed", 1, payload=payload)
        assert failure.value.code == "UNSUPPORTED_EVENT"


def test_cursor_protocol_is_strict_for_numeric_opaque_cross_run_and_ahead() -> None:
    event_ids = {"EVT-A": 3}
    assert resolve_cursor(None, tail_sequence=4, same_run_event_ids=event_ids).sequence == 0
    assert resolve_cursor("3", tail_sequence=4, same_run_event_ids=event_ids).sequence == 3
    assert resolve_cursor("EVT-A", tail_sequence=4, same_run_event_ids=event_ids).sequence == 3
    for cursor in ("-1", "+1", "01", " 1", "UNKNOWN", "9223372036854775808"):
        assert (
            resolve_cursor(cursor, tail_sequence=4, same_run_event_ids=event_ids).disposition
            is CursorDisposition.INVALID_CURSOR
        )
    assert (
        resolve_cursor("5", tail_sequence=4, same_run_event_ids=event_ids).disposition
        is CursorDisposition.CURSOR_AHEAD
    )


def test_error_envelope_and_pre_header_cursor_errors_use_exact_vocabulary() -> None:
    for code, (status, retryable, recovery) in ERROR_HTTP_MAP.items():
        body = {
            "schema_version": "phase4-error/v1",
            "error": {
                "code": code,
                "message": "safe",
                "retryable": retryable,
                "recovery": recovery,
                "request_id": None,
                "resource": None,
                "details": {},
            },
        }
        assert validate_error_envelope(status, body)["code"] == code
    invalid = {
        "schema_version": "phase4-error/v1",
        "error": {
            "code": "INVALID_CURSOR",
            "message": "safe",
            "retryable": False,
            "recovery": "SNAPSHOT_RELOAD",
            "request_id": None,
            "resource": {"type": "research_run", "id": RUN_ID},
            "details": {},
        },
    }
    assert_cursor_error_response(
        400,
        {"Content-Type": "application/json"},
        invalid,
        expected_code="INVALID_CURSOR",
    )
    with pytest.raises(SSEAcceptanceError, match="committed SSE headers"):
        assert_cursor_error_response(400, _headers(), invalid, expected_code="INVALID_CURSOR")


def test_projection_closes_exact_identity_tasks_dependencies_and_terminal_state() -> None:
    view = validate_run_projection(
        _snapshot(), expected_run_id=RUN_ID, expected_object_id=OBJECT_ID
    )
    assert view.task_ids == {"TASK-A"}
    bad = _snapshot(tasks=[_task("TASK-A", ["TASK-B"])])
    with pytest.raises(SSEAcceptanceError) as failure:
        validate_run_projection(bad)
    assert failure.value.code == "INTEGRITY_FAILURE"
    terminal = _snapshot(sequence=4, status="RELEASED", terminal_event_id="EVT-4")
    assert validate_run_projection(terminal).terminal["outcome"] == "SUCCESS"


def test_sequence_duplicate_gap_conflict_and_snapshot_recovery_are_fail_closed() -> None:
    oracle = SSEProjectionOracle(_snapshot())
    first = _frame("task.progress", 1)
    applied = oracle.admit(first)
    assert applied.disposition is EventDisposition.APPLIED
    assert oracle.committed_sequence == 1
    assert oracle.admit(first).disposition is EventDisposition.DUPLICATE_IGNORED
    conflicting = _frame("task.progress", 1, event_id="EVT-CONFLICT")
    assert oracle.admit(conflicting).disposition is EventDisposition.QUARANTINED
    assert oracle.committed_sequence == 1
    oracle.reconcile(_snapshot(sequence=2, revision=2))
    assert oracle.connection_state == "OPEN"
    assert oracle.admit(_frame("task.progress", 4)).reason == "SEQUENCE_GAP"


def test_wrong_run_and_sparse_graph_events_cannot_fabricate_research_tasks() -> None:
    oracle = SSEProjectionOracle(_snapshot())
    before_ids = oracle.task_ids
    assert (
        oracle.admit(_frame("task.progress", 1, run_id="RUN-B")).disposition
        is EventDisposition.QUARANTINED
    )
    oracle.reconcile(_snapshot(sequence=0, revision=1))
    graph = _frame("graph.task_added", 1, task_id="TASK-B", graph_version=2)
    assert oracle.admit(graph).disposition is EventDisposition.REFRESH_REQUIRED
    assert oracle.task_ids == before_ids
    after = _snapshot(
        sequence=1,
        revision=2,
        graph_version=2,
        tasks=[_task("TASK-A"), {**_task("TASK-B"), "origin": "REPLAN"}],
    )
    oracle.reconcile(after)
    assert oracle.task_ids == {"TASK-A", "TASK-B"}


def test_research_path_is_exact_task_status_and_dependency_projection() -> None:
    snapshot = _snapshot(tasks=[_task("TASK-A"), _task("TASK-B", ["TASK-A"], status="WAITING")])
    rendered = [
        {"taskId": "TASK-A", "backendStatus": "RUNNING", "dependencyIds": []},
        {"taskId": "TASK-B", "backendStatus": "WAITING", "dependencyIds": ["TASK-A"]},
    ]
    assert_research_path_projection(snapshot, rendered)
    rendered.append({"taskId": "FAKE", "backendStatus": "READY", "dependencyIds": []})
    with pytest.raises(SSEAcceptanceError, match="not an exact authoritative Task projection"):
        assert_research_path_projection(snapshot, rendered)


def test_self_correction_is_same_task_same_graph_and_one_durable_path_change() -> None:
    before = _snapshot(sequence=10)
    events = [
        _validated("task.self_correcting", 11),
        _validated("task.correction_resolved", 12),
    ]
    correction = _path_change(
        "CORRECTION-A",
        source_kind="CORRECTION",
        change_kind="SELF_CORRECTION",
        decision=None,
        task_refs=["TASK-A"],
    )
    after = _snapshot(sequence=12, revision=2, path_changes=[correction])
    assert_self_correction_same_task_same_graph(before, events, after)
    bad = _snapshot(sequence=12, revision=2, graph_version=2, path_changes=[correction])
    with pytest.raises(SSEAcceptanceError, match="changed graph identity/version"):
        assert_self_correction_same_task_same_graph(before, events, bad)


@pytest.mark.parametrize("decision", ["PENDING", "REJECTED"])
def test_pending_or_rejected_replan_has_no_graph_mutation(decision: str) -> None:
    before = _snapshot(sequence=20)
    change = _path_change(
        "REPLAN-A",
        source_kind="REPLAN",
        change_kind="ADD_TASK",
        decision=decision,
        task_refs=["TASK-A"],
    )
    after = _snapshot(sequence=21, revision=2, path_changes=[change])
    events = [_validated("replan.requested", 21)]
    assert_controlled_replan(before, events, after, expected_decision=decision)


def test_approved_replan_follows_lead_approval_and_applies_exactly_once() -> None:
    before = _snapshot(sequence=30)
    operations = [
        {"operation": "add_node", "task_id": "TASK-B"},
        {"operation": "add_edge", "source_task_id": "TASK-A", "target_task_id": "TASK-B"},
    ]
    change = _path_change(
        "REPLAN-A",
        source_kind="REPLAN",
        change_kind="ADD_TASK",
        decision="APPROVED",
        task_refs=["TASK-A", "TASK-B"],
        operations=operations,
        before=1,
        after=2,
    )
    after = _snapshot(
        sequence=35,
        revision=2,
        graph_version=2,
        tasks=[_task("TASK-A"), {**_task("TASK-B", ["TASK-A"]), "origin": "REPLAN"}],
        path_changes=[change],
    )
    events = [
        _validated("replan.requested", 31),
        _validated("replan.approved", 32),
        _validated("graph.task_added", 33, task_id="TASK-B", graph_version=2),
        _validated("graph.edge_added", 34, task_id="TASK-B", graph_version=2),
        _validated("graph.version_changed", 35, task_id=None, graph_version=2),
    ]
    assert_controlled_replan(before, events, after, expected_decision="APPROVED")
    wrong_order = [events[0], events[2], events[1], events[3], events[4]]
    with pytest.raises(SSEAcceptanceError):
        assert_controlled_replan(before, wrong_order, after, expected_decision="APPROVED")


def test_disconnect_is_transport_state_and_does_not_change_business_snapshot() -> None:
    snapshot = _snapshot(sequence=5)
    assert_disconnect_retains_business_snapshot(
        snapshot, deepcopy(snapshot), connection_state="BACKOFF"
    )
    changed = deepcopy(snapshot)
    changed["run"]["status"] = "FAILED"
    with pytest.raises(SSEAcceptanceError):
        assert_disconnect_retains_business_snapshot(snapshot, changed, connection_state="BACKOFF")


def test_exact_run_url_and_success_headers_reject_latest_or_wrong_streams() -> None:
    assert_exact_run_event_url(f"http://127.0.0.1/api/research-runs/{RUN_ID}/events", RUN_ID)
    assert_sse_success_headers(200, _headers())
    with pytest.raises(SSEAcceptanceError):
        assert_exact_run_event_url("http://127.0.0.1/api/research-runs/latest/events", RUN_ID)
    with pytest.raises(SSEAcceptanceError):
        assert_sse_success_headers(200, {"Content-Type": "application/json"})


@pytest.mark.asyncio
async def test_live_collector_validates_chunked_real_wire_shape_and_recovery() -> None:
    raw = _frame("task.progress", 1).raw_bytes
    response = _Response([raw[:7], raw[7:41], raw[41:]])
    oracle = SSEProjectionOracle(_snapshot())
    observation = await collect_live_sse(
        response,
        expected_run_id=RUN_ID,
        requested_cursor="0",
        oracle=oracle,
    )
    assert observation.stream_exhausted
    assert observation.business_sequences == (1,)
    assert observation.dispositions[0].disposition is EventDisposition.APPLIED


@pytest.mark.asyncio
async def test_live_collector_business_limit_ignores_heartbeat_comments() -> None:
    raw = b": heartbeat\n\n" + _frame("task.progress", 1).raw_bytes
    observation = await collect_live_sse(
        _Response([raw]),
        expected_run_id=RUN_ID,
        requested_cursor="0",
        max_business_events=1,
    )
    assert observation.stream_exhausted is False
    assert observation.business_sequences == (1,)
    assert len(observation.frames) == 2


def test_numeric_and_opaque_resume_oracles_require_same_exact_suffix() -> None:
    before = _observation([_validated("task.progress", 1)], cursor="0")
    suffix = [_validated("task.progress", 2), _validated("task.progress", 3)]
    numeric = _observation(suffix, cursor="1")
    opaque = _observation(suffix, cursor="EVT-1")
    baseline = _observation(
        [*before.events, *suffix],
        cursor="0",
    )
    assert_numeric_resume(
        before,
        numeric,
        committed_sequence=1,
        durable_tail=3,
        full_baseline=baseline,
    )
    assert_replay_suffix_matches_baseline(
        baseline,
        opaque,
        committed_sequence=1,
    )
    assert_numeric_opaque_suffix_equal(numeric, opaque)
    wrong = _observation([_validated("task.progress", 3)], cursor="1")
    with pytest.raises(SSEAcceptanceError, match=r"N\+1"):
        assert_numeric_resume(before, wrong, committed_sequence=1, durable_tail=3)


def test_replay_oracles_reject_same_sequences_with_changed_event_identity() -> None:
    baseline_events = [
        _validated("task.progress", 1),
        _validated("task.progress", 2),
        _validated("task.progress", 3),
    ]
    baseline = _observation(baseline_events, cursor="0")
    expected_suffix = baseline_events[1:]
    changed_identity = [
        replace(expected_suffix[0], event_id="EVT-DIFFERENT"),
        expected_suffix[1],
    ]
    forged = _observation(changed_identity, cursor="1")

    with pytest.raises(SSEAcceptanceError, match="identity/content differs"):
        assert_replay_suffix_matches_baseline(
            baseline,
            forged,
            committed_sequence=1,
        )
    with pytest.raises(SSEAcceptanceError, match="different suffixes"):
        assert_numeric_opaque_suffix_equal(
            _observation(expected_suffix, cursor="1"),
            _observation(changed_identity, cursor="EVT-1"),
        )


def test_replay_oracles_reject_same_sequences_and_ids_with_changed_content() -> None:
    baseline_events = [
        _validated("task.progress", 1),
        _validated("task.progress", 2),
        _validated("task.progress", 3),
    ]
    baseline = _observation(baseline_events, cursor="0")
    expected_suffix = baseline_events[1:]
    changed_content = [
        _validated(
            "task.progress",
            2,
            event_id="EVT-2",
            payload={"progress": 0.75, "progress_scale": "RATIO_0_1"},
        ),
        expected_suffix[1],
    ]
    forged = _observation(changed_content, cursor="1")

    with pytest.raises(SSEAcceptanceError, match="identity/content differs"):
        assert_numeric_resume(
            _observation([baseline_events[0]], cursor="0"),
            forged,
            committed_sequence=1,
            durable_tail=3,
            full_baseline=baseline,
        )
    with pytest.raises(SSEAcceptanceError, match="different suffixes"):
        assert_numeric_opaque_suffix_equal(
            _observation(expected_suffix, cursor="1"),
            _observation(changed_content, cursor="EVT-1"),
        )


def test_terminal_success_failure_and_equal_cursor_close() -> None:
    success_events = [
        _validated("release.completed", 1),
        _validated("run.completed", 2),
    ]
    assert_terminal_stream(_observation(success_events, cursor="0"), outcome="SUCCESS")
    failure = _validated("run.failed", 1)
    assert_terminal_stream(_observation([failure], cursor="0"), outcome="FAILURE")
    terminal_cursor = LiveStreamObservation(
        requested_run_id=RUN_ID,
        requested_cursor="2",
        status_code=200,
        headers={**_headers(), "X-Run-Terminal": "true", "X-Terminal-Sequence": "2"},
        frames=(),
        events=(),
        dispositions=(),
        stream_exhausted=True,
    )
    assert_terminal_cursor_response(terminal_cursor, expected_sequence=2)
