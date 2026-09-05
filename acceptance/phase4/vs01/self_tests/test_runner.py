from __future__ import annotations

import base64
import hashlib
import json
from copy import deepcopy
from types import SimpleNamespace
from typing import Any

import pytest

from acceptance.phase4.vs01 import run_vs01
from acceptance.phase4.vs01.harness.backend import HttpObservation, TransportUnavailable
from acceptance.phase4.vs01.harness.gate import GateError, sha256_json
from acceptance.phase4.vs01.harness.sse import (
    CORE_CONTRACT_VERSION,
    EVENT_CONTRACT_VERSION,
    SUPPORTED_V1_EVENTS,
    LiveStreamObservation,
    validate_runtime_event,
)
from acceptance.phase4.vs01.self_tests.test_backend import (
    OBJECT_ID,
    ScriptedContractTransport,
)
from acceptance.phase4.vs01.self_tests.test_backend import (
    _config as backend_config,
)
from acceptance.phase4.vs01.self_tests.test_sse import (
    NOW,
    RUN_ID,
    _frame,
    _headers,
    _path_change,
    _snapshot,
    _task,
)

EVIDENCE_BACKEND_URL = "http://127.0.0.1:8010"


def _evidence_binding() -> dict[str, str]:
    return {
        "capture_session_nonce_sha256": "a" * 64,
        "database_name_sha256": "b" * 64,
        "backend_process_boundary_id": "PROC-VS01-CAPTURE",
        "backend_base_url": EVIDENCE_BACKEND_URL,
        "capture_driver_sha256": "c" * 64,
    }


def _projection(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "capture_kind": "REAL_PUBLIC_PROJECTION",
        "request_url": f"{EVIDENCE_BACKEND_URL}/api/research-runs/{RUN_ID}/projection",
        "sha256": sha256_json(value),
        "value": value,
    }


def _stream(
    frames: list[Any] | None = None,
    *,
    raw: bytes | None = None,
    cursor: str | None = "0",
    exhausted: bool = True,
) -> dict[str, Any]:
    content = raw if raw is not None else b"".join(frame.raw_bytes for frame in frames or [])
    return {
        "capture_kind": "REAL_PUBLIC_SSE_BYTES",
        "request_url": f"{EVIDENCE_BACKEND_URL}/api/research-runs/{RUN_ID}/events",
        "run_id": RUN_ID,
        "requested_cursor": cursor,
        "status_code": 200,
        "headers": _headers(),
        "raw_sse_base64": base64.b64encode(content).decode(),
        "sha256": hashlib.sha256(content).hexdigest(),
        "stream_exhausted": exhausted,
    }


def _dynamic_scenarios() -> dict[str, Any]:
    correction = _path_change(
        "CORRECTION-A",
        source_kind="CORRECTION",
        change_kind="SELF_CORRECTION",
        decision=None,
        task_refs=["TASK-A"],
    )
    pending = _path_change(
        "REPLAN-A",
        source_kind="REPLAN",
        change_kind="ADD_TASK",
        decision="PENDING",
        task_refs=["TASK-A"],
    )
    operations = [
        {"operation": "add_node", "task_id": "TASK-B"},
    ]
    approved = _path_change(
        "REPLAN-A",
        source_kind="REPLAN",
        change_kind="ADD_TASK",
        decision="APPROVED",
        task_refs=["TASK-A", "TASK-B"],
        operations=operations,
        before=1,
        after=2,
    )
    return {
        "self_correction": {
            "before_projection": _projection(_snapshot(sequence=10)),
            "stream": _stream(
                [_frame("task.self_correcting", 11), _frame("task.correction_resolved", 12)],
                cursor="10",
            ),
            "after_projection": _projection(
                _snapshot(sequence=12, revision=2, path_changes=[correction])
            ),
        },
        "replan_pending": {
            "before_projection": _projection(_snapshot(sequence=20)),
            "stream": _stream([_frame("replan.requested", 21)], cursor="20"),
            "after_projection": _projection(
                _snapshot(sequence=21, revision=2, path_changes=[pending])
            ),
        },
        "replan_approved": {
            "before_projection": _projection(_snapshot(sequence=30)),
            "stream": _stream(
                [
                    _frame("replan.requested", 31),
                    _frame("replan.approved", 32),
                    _frame("graph.task_added", 33, task_id="TASK-B", graph_version=2),
                    _frame("graph.version_changed", 34, task_id=None, graph_version=2),
                ],
                cursor="30",
            ),
            "after_projection": _projection(
                _snapshot(
                    sequence=34,
                    revision=2,
                    graph_version=2,
                    tasks=[_task("TASK-A"), {**_task("TASK-B"), "origin": "REPLAN"}],
                    path_changes=[approved],
                )
            ),
        },
    }


def _evidence_document(*, binding: dict[str, str] | None = None) -> dict[str, Any]:
    inventory = [_frame(name, index) for index, name in enumerate(sorted(SUPPORTED_V1_EVENTS), 1)]
    sparse_after = _snapshot(
        sequence=1,
        revision=2,
        graph_version=2,
        tasks=[_task("TASK-A"), {**_task("TASK-B"), "origin": "REPLAN"}],
    )
    document = {
        "schema_version": run_vs01.EVIDENCE_SCHEMA_VERSION,
        "candidate": {
            "git_sha": run_vs01._candidate_git_sha(),
            "contract_revision": run_vs01.CONTRACT_REVISION,
            "event_contract_version": EVENT_CONTRACT_VERSION,
            "final_freeze_decision_sha256": run_vs01.FINAL_FREEZE_DECISION_SHA256,
            "postgresql_major": 16,
            "capture_source": "REAL_PRODUCT_PUBLIC_API_SSE",
            "mock_business_responses": False,
            **(binding or _evidence_binding()),
        },
        "scenarios": {
            "event_inventory": {"streams": [_stream(inventory)]},
            "duplicate": {
                "before_projection": _projection(_snapshot()),
                "stream": _stream([_frame("task.progress", 1)], cursor="0"),
            },
            "ordering_recovery": {
                "before_projection": _projection(_snapshot()),
                "stream": _stream(
                    [_frame("task.progress", 1), _frame("task.progress", 2)],
                    cursor="0",
                ),
                "recovered_projection": _projection(_snapshot(sequence=2, revision=2)),
            },
            "heartbeat": {
                "before_projection": _projection(_snapshot()),
                "stream": _stream(raw=b": heartbeat\n\n", cursor="0", exhausted=False),
            },
            "terminal_failure": {"stream": _stream([_frame("run.failed", 1)], cursor="0")},
            "snapshot_race": {
                "before_projection": _projection(_snapshot()),
                "stream": _stream(
                    [_frame("task.progress", 1), _frame("task.progress", 2)],
                    cursor="0",
                ),
                "after_projection": _projection(_snapshot(sequence=2, revision=2)),
            },
            "sparse_graph_refresh": {
                "before_projection": _projection(_snapshot()),
                "stream": _stream(
                    [_frame("graph.task_added", 1, task_id="TASK-B", graph_version=2)],
                    cursor="0",
                ),
                "after_projection": _projection(sparse_after),
            },
            **_dynamic_scenarios(),
        },
    }
    return document


def _capture_index() -> dict[str, Any]:
    counter = 0

    def receipt() -> str:
        nonlocal counter
        counter += 1
        return f"CAP-{counter:048X}"

    three = {"before_projection", "stream", "after_projection"}
    return {
        "schema_version": run_vs01.CAPTURE_INDEX_SCHEMA_VERSION,
        "scenarios": {
            "event_inventory": {"streams": [receipt(), receipt()]},
            "duplicate": {"before_projection": receipt(), "stream": receipt()},
            "ordering_recovery": {
                "before_projection": receipt(),
                "stream": receipt(),
                "recovered_projection": receipt(),
            },
            "heartbeat": {"before_projection": receipt(), "stream": receipt()},
            "terminal_failure": {"stream": receipt()},
            **{
                name: {field: receipt() for field in sorted(three)}
                for name in (
                    "snapshot_race",
                    "sparse_graph_refresh",
                    "self_correction",
                    "replan_pending",
                    "replan_approved",
                )
            },
        },
    }


def _capture_record(
    path: str,
    body: bytes,
    *,
    request_headers: tuple[tuple[str, str], ...],
    response_headers: tuple[tuple[str, str], ...],
    cutoff: int | None = None,
) -> Any:
    deliberate = cutoff is not None
    return run_vs01.CaptureRecord(
        session_id="SESSION-" + "A" * 48,
        capture_id="CAP-" + "B" * 48,
        order=1,
        started_at=NOW,
        started_monotonic_ns=1,
        completed_at=NOW,
        completed_monotonic_ns=2,
        method="GET",
        canonical_path_query=path,
        canonical_proxy_url=f"http://127.0.0.1:54321{path}",
        canonical_upstream_url=f"{EVIDENCE_BACKEND_URL}{path}",
        request_headers=request_headers,
        upstream_request_headers=request_headers,
        sensitive_request_header_names=(),
        request_body_length=0,
        upstream_status_code=200,
        upstream_response_headers=response_headers,
        status_code=200,
        response_headers=response_headers,
        response_body=body,
        response_sha256=hashlib.sha256(body).hexdigest(),
        requested_sse_frame_cutoff=cutoff,
        complete_sse_frames=cutoff or 0,
        upstream_complete=not deliberate,
        downstream_complete=True,
        truncated=False,
        termination="GATE_SSE_FRAME_CUTOFF" if deliberate else "UPSTREAM_EOF",
        error=None,
    )


def test_reviewed_real_sse_evidence_reaches_every_formerly_unreachable_control() -> None:
    outcomes, public = run_vs01._evaluate_external_sse_evidence(
        _evidence_document(), expected_binding=_evidence_binding()
    )
    expected = {
        "VS01-SSE-003",
        "VS01-SSE-007",
        "VS01-SSE-008",
        "VS01-SSE-009",
        "VS01-SSE-010",
        "VS01-SSE-012",
        "VS01-REC-007",
        "VS01-DYN-002",
        "VS01-DYN-003",
        "VS01-DYN-004",
        "VS01-DYN-006",
        "VS01-DYN-007",
    }
    assert set(outcomes) == expected
    assert {outcome["status"] for outcome in outcomes.values()} == {"PASS"}
    assert len(public) >= 20


def test_external_evidence_is_exact_type_and_cursor_bound() -> None:
    wrong_bool = _evidence_document()
    wrong_bool["candidate"]["mock_business_responses"] = 0
    with pytest.raises(GateError, match="invalid types"):
        run_vs01._evaluate_external_sse_evidence(wrong_bool, expected_binding=_evidence_binding())

    wrong_cursor = _evidence_document()
    wrong_cursor["scenarios"]["snapshot_race"]["stream"]["requested_cursor"] = None
    with pytest.raises(GateError, match="snapshot watermark"):
        run_vs01._evaluate_external_sse_evidence(wrong_cursor, expected_binding=_evidence_binding())


def test_failure_scenario_rejects_any_success_release() -> None:
    document = _evidence_document()
    document["scenarios"]["terminal_failure"]["stream"] = _stream(
        [_frame("release.completed", 1), _frame("run.failed", 2)], cursor="0"
    )
    with pytest.raises(GateError, match="no success release"):
        run_vs01._evaluate_external_sse_evidence(document, expected_binding=_evidence_binding())


class _FakeIsolation:
    def __init__(self, *, fail: bool = False) -> None:
        self.created = True
        self.fail = fail

    def safe_evidence(self) -> dict[str, Any]:
        return {"database_name_sha256": "a" * 64, "credentials_recorded": False}

    def drop(self) -> None:
        if self.fail:
            raise GateError("drop failed")
        self.created = False


def test_cleanup_control_passes_only_after_drop_and_fails_on_drop_error() -> None:
    outcomes: dict[str, Any] = {}
    findings: list[dict[str, Any]] = []
    success = _FakeIsolation()
    run_vs01._cleanup_isolated_database(success, outcomes, findings)  # type: ignore[arg-type]
    assert outcomes["VS01-REC-013"]["status"] == "PASS"
    assert outcomes["VS01-REC-013"]["evidence"]["drop_completed"] is True
    assert not findings

    outcomes = {}
    failed = _FakeIsolation(fail=True)
    run_vs01._cleanup_isolated_database(failed, outcomes, findings)  # type: ignore[arg-type]
    assert outcomes["VS01-REC-013"]["status"] == "FAIL"
    assert findings[-1]["finding_id"] == "VS01-X4-CLEANUP-001"


def test_concurrent_confirm_probe_requires_one_create_one_replay_and_consumed_draft() -> None:
    evidence = run_vs01._check_concurrent_confirm(
        ScriptedContractTransport(),
        backend_config(),
        OBJECT_ID,
    )
    assert evidence["create_responses"] == 1
    assert evidence["replay_responses"] == 1
    assert evidence["run_cardinality_delta"] == 1
    assert evidence["new_key_consumed_reason"] == "DRAFT_CONSUMED"


@pytest.mark.asyncio
async def test_post_restart_controls_require_real_full_suffix_and_terminal_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = validate_runtime_event(_frame("release.completed", 1), expected_run_id=RUN_ID)
    completed = validate_runtime_event(_frame("run.completed", 2), expected_run_id=RUN_ID)

    def observation(cursor: str, events: tuple[Any, ...]) -> LiveStreamObservation:
        headers = _headers()
        if cursor == "2":
            headers = {**headers, "X-Run-Terminal": "true", "X-Terminal-Sequence": "2"}
        return LiveStreamObservation(
            requested_run_id=RUN_ID,
            requested_cursor=cursor,
            status_code=200,
            headers=headers,
            frames=(),
            events=events,
            dispositions=(),
            stream_exhausted=True,
        )

    baseline = observation("0", (release, completed))

    async def collect(
        base_url: str,
        run_id: str,
        cursor: str,
        *,
        timeout_seconds: float,
        max_business_events: int | None = None,
    ) -> LiveStreamObservation:
        assert base_url == "http://product.invalid"
        assert run_id == RUN_ID
        assert timeout_seconds == 5
        assert max_business_events is None
        return {
            "0": observation("0", (release, completed)),
            "1": observation("1", (completed,)),
            "2": observation("2", ()),
        }[cursor]

    monkeypatch.setattr(run_vs01, "_collect_stream", collect)
    projection = _snapshot(
        sequence=2,
        revision=2,
        status="RELEASED",
        terminal_event_id="EVT-2",
    )
    outcomes, public = await run_vs01._verify_post_restart_sse(
        "http://product.invalid",
        {"A": baseline, "B": baseline},
        {"A": projection, "B": projection},
        timeout_seconds=5,
        restart_evidence={
            "managed_process": True,
            "start_count": 2,
            "process_boundary_ids": ["before", "after"],
        },
    )
    assert outcomes["VS01-REC-011"]["status"] == "PASS"
    assert outcomes["VS01-REC-015"]["status"] == "PASS"
    assert len(public) == 8

    with pytest.raises(GateError, match="managed process boundaries"):
        await run_vs01._verify_post_restart_sse(
            "http://product.invalid",
            {"A": baseline, "B": baseline},
            {"A": projection, "B": projection},
            timeout_seconds=5,
            restart_evidence={},
        )


def test_public_surface_violation_sets_both_security_controls_to_fail() -> None:
    outcomes: dict[str, Any] = {}
    with pytest.raises(GateError, match="security controls failed"):
        run_vs01._scan_public_evidence(
            [{"authorization": "Bearer abcdefghijklmnop"}],
            outcomes,
            sentinel="SENTINEL",
        )
    assert outcomes["VS01-SEC-001"]["status"] == "FAIL"
    assert outcomes["VS01-SEC-002"]["status"] == "FAIL"


def test_candidate_clean_check_includes_untracked_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def dirty(command: Any, **kwargs: Any) -> Any:
        calls.append(list(command))
        return SimpleNamespace(returncode=0, stdout="?? product-untracked.py\n")

    monkeypatch.setattr(run_vs01.subprocess, "run", dirty)
    assert run_vs01._tracked_candidate_clean() is False
    assert calls == [["git", "status", "--porcelain", "--untracked-files=all"]]


def test_harness_check_counts_are_machine_readable() -> None:
    assert run_vs01._check_counts("VS01-HARNESS-PYTHON", "95 passed, 2 skipped in 0.4s") == {
        "passed": 95,
        "executed": 97,
    }
    browser = "ℹ tests 11\nℹ pass 11\nℹ tests 1\nℹ pass 1\nTotal: 4 tests in 1 file\n"
    assert run_vs01._check_counts("VS01-HARNESS-BROWSER", browser) == {
        "passed": 12,
        "executed": 12,
        "real_tests_collected": 4,
    }


def test_gate_reconstructs_projection_and_sse_artifacts_from_captured_bytes() -> None:
    projection = _snapshot()
    projection_body = json.dumps(projection, separators=(",", ":")).encode()
    projection_record = _capture_record(
        f"/api/research-runs/{RUN_ID}/projection",
        projection_body,
        request_headers=(("X-Phase4-Contract-Version", CORE_CONTRACT_VERSION),),
        response_headers=(
            ("Content-Type", "application/json"),
            ("X-Phase4-Contract-Version", CORE_CONTRACT_VERSION),
        ),
    )
    artifact = run_vs01._projection_artifact_from_record(
        projection_record,
        label="projection",
    )
    assert artifact["value"] == projection
    assert artifact["sha256"] == sha256_json(projection)

    frame = _frame("task.progress", 1)
    stream_record = _capture_record(
        f"/api/research-runs/{RUN_ID}/events",
        frame.raw_bytes,
        request_headers=(
            ("Accept", "text/event-stream"),
            ("Last-Event-ID", "0"),
            ("X-Phase4-Contract-Version", CORE_CONTRACT_VERSION),
            ("X-Phase4-Event-Contract-Version", EVENT_CONTRACT_VERSION),
        ),
        response_headers=tuple(_headers().items()),
        cutoff=1,
    )
    stream = run_vs01._stream_artifact_from_record(stream_record, label="stream")
    assert base64.b64decode(stream["raw_sse_base64"], validate=True) == frame.raw_bytes
    assert stream["requested_cursor"] == "0"
    assert stream["stream_exhausted"] is False

    ambiguous = deepcopy(stream_record)
    object.__setattr__(
        ambiguous,
        "upstream_response_headers",
        (*stream_record.upstream_response_headers, ("Content-Type", "text/event-stream")),
    )
    with pytest.raises(GateError, match="duplicate response headers"):
        run_vs01._stream_artifact_from_record(ambiguous, label="stream")


def test_driver_capture_index_accepts_only_unique_gate_receipts(tmp_path: Any) -> None:
    index = _capture_index()
    raw = (run_vs01.json.dumps(index) + "\n").encode()
    path = tmp_path / "capture-index.json"
    path.write_bytes(raw)
    loaded, digest, references = run_vs01._load_driver_capture_index(path)
    assert loaded["schema_version"] == run_vs01.CAPTURE_INDEX_SCHEMA_VERSION
    assert digest == hashlib.sha256(raw).hexdigest()
    assert len(references) == 25
    assert set(references) == {
        "event_inventory.streams[0]",
        "event_inventory.streams[1]",
        "duplicate.before_projection",
        "duplicate.stream",
        "ordering_recovery.before_projection",
        "ordering_recovery.stream",
        "ordering_recovery.recovered_projection",
        "heartbeat.before_projection",
        "heartbeat.stream",
        "terminal_failure.stream",
        *{
            f"{name}.{field}"
            for name in (
                "snapshot_race",
                "sparse_graph_refresh",
                "self_correction",
                "replan_pending",
                "replan_approved",
            )
            for field in ("before_projection", "stream", "after_projection")
        },
    }

    authored = deepcopy(index)
    authored["candidate"] = _evidence_document()["candidate"]
    path.write_text(run_vs01.json.dumps(authored), encoding="utf-8")
    with pytest.raises(GateError, match="exactly"):
        run_vs01._load_driver_capture_index(path)

    duplicated = _capture_index()
    duplicated["scenarios"]["duplicate"]["stream"] = duplicated["scenarios"]["duplicate"][
        "before_projection"
    ]
    path.write_text(run_vs01.json.dumps(duplicated), encoding="utf-8")
    with pytest.raises(GateError, match="reuses"):
        run_vs01._load_driver_capture_index(path)


def test_capture_driver_receives_only_proxy_origin_and_output_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    seen_env: dict[str, str] = {}
    capture_index = _capture_index()

    class FakeVerifier:
        def verify_driver_capture_ids(self, references: Any, **kwargs: Any) -> Any:
            assert kwargs == {"seed_run_ids": ("RUN-A", "RUN-B")}
            return {label: SimpleNamespace() for label in references}

    class FakeProxy:
        def __init__(self, upstream: str, **kwargs: Any) -> None:
            assert upstream == EVIDENCE_BACKEND_URL
            assert kwargs["upstream_timeout_seconds"] == 30.0
            self.origin = "http://127.0.0.1:54321"
            self.session_id = "SESSION-" + "A" * 48
            self.session = SimpleNamespace(records=tuple(range(25)))

        def __enter__(self) -> Any:
            return self

        def __exit__(self, *args: Any) -> bool:
            return False

        def verifier(self) -> FakeVerifier:
            return FakeVerifier()

    def command(command: Any, **kwargs: Any) -> Any:
        nonlocal seen_env
        seen_env = dict(kwargs["env"])
        assert kwargs["inherit_environment"] is False
        output = run_vs01.Path(seen_env["VS01_EVIDENCE_OUTPUT_PATH"])
        output.write_text(run_vs01.json.dumps(capture_index))
        return SimpleNamespace(returncode=0, duration_seconds=0.25)

    def reconstruct(index: Any, records: Any, *, binding: Any) -> Any:
        assert index == capture_index
        assert len(records) == 25
        return _evidence_document(binding=dict(binding))

    monkeypatch.setattr(run_vs01, "run_command", command)
    monkeypatch.setattr(run_vs01, "AuditedCaptureProxy", FakeProxy)
    monkeypatch.setattr(run_vs01, "_reconstruct_sse_evidence", reconstruct)
    monkeypatch.setattr(run_vs01, "_tracked_candidate_clean", lambda: True)
    document, receipt = run_vs01._capture_external_sse_evidence(
        {
            "sse_scenario_capture": {
                "driver_path": "scripts/run_acceptance.py",
                "command": ("python3.11", "scripts/run_acceptance.py"),
                "cwd": run_vs01.REPOSITORY_ROOT,
                "timeout_seconds": 30.0,
            }
        },
        database_name_sha256="b" * 64,
        backend_url=EVIDENCE_BACKEND_URL,
        backend_process_boundary_id="PROC-LIVE-1",
        run_ids={"A": "RUN-A", "B": "RUN-B"},
        output_root=tmp_path,
    )
    assert document["candidate"]["backend_process_boundary_id"] == "PROC-LIVE-1"
    assert receipt["evidence_sha256"]
    assert receipt["raw_database_url_recorded"] is False
    assert receipt["driver_received_database_url"] is False
    assert receipt["driver_received_direct_backend_url"] is False
    assert seen_env == {
        "VS01_BACKEND_URL": "http://127.0.0.1:54321",
        "VS01_EVIDENCE_OUTPUT_PATH": str((tmp_path / "runtime-sse-capture-index.json").resolve()),
    }


def test_recording_transport_retains_response_headers_and_structured_body() -> None:
    class Delegate:
        def request(self, *args: Any, **kwargs: Any) -> Any:
            from acceptance.phase4.vs01.harness.backend import HttpObservation

            return HttpObservation(
                200,
                {"X-Phase4-Contract-Version": CORE_CONTRACT_VERSION},
                b'{"run_id":"RUN-A"}',
            )

    public: list[Any] = []
    transport = run_vs01.RecordingJsonTransport(Delegate(), public)  # type: ignore[arg-type]
    transport.request("GET", "/api/research-runs/RUN-A")
    assert public == [
        {
            "surface": "product_api_response",
            "status_code": 200,
            "headers": {"x-phase4-contract-version": CORE_CONTRACT_VERSION},
            "body": {"run_id": "RUN-A"},
            "body_utf8": '{"run_id":"RUN-A"}',
        }
    ]


def test_postgresql_causal_probe_requires_success_then_database_induced_failure() -> None:
    checkpoint = SimpleNamespace(
        run_id="RUN-CAUSAL",
        object_id="OBJ-CAUSAL",
        goal_id="GOAL-CAUSAL",
        scheme_id="SCHEME-CAUSAL",
        planned_graph_id="GRAPH-CAUSAL",
        as_of="2026-09-05",
    )
    run_body = {
        "run_id": checkpoint.run_id,
        "research_object_id": checkpoint.object_id,
        "goal_id": checkpoint.goal_id,
        "scheme_id": checkpoint.scheme_id,
        "planned_graph_id": checkpoint.planned_graph_id,
        "status": "RUNNING",
        "stage": "RESEARCH",
        "as_of": checkpoint.as_of,
        "actual_graph_id": "GRAPH-CAUSAL-ACTUAL",
        "execution_target": "SERVER_SANDBOX",
        "created_at": NOW,
        "updated_at": NOW,
        "started_at": NOW,
        "completed_at": None,
        "terminal": False,
        "projection_revision": 1,
        "projection_sequence": 0,
    }

    class Isolation:
        connections_blocked = False

        def block_connections(self) -> dict[str, Any]:
            self.connections_blocked = True
            return {
                "database_name_sha256": "a" * 64,
                "allow_connections": False,
                "terminated_sessions": 1,
                "remaining_sessions": 0,
            }

        def restore_connections(self) -> dict[str, Any]:
            self.connections_blocked = False
            return {"allow_connections": True}

    class Transport:
        calls = 0

        def request(self, *args: Any, **kwargs: Any) -> HttpObservation:
            self.calls += 1
            if self.calls == 1:
                return HttpObservation(200, {}, json.dumps(run_body).encode())
            raise TransportUnavailable("database is blocked")

    isolation = Isolation()
    evidence = run_vs01._prove_postgresql_causal_binding(  # type: ignore[arg-type]
        isolation,
        Transport(),  # type: ignore[arg-type]
        checkpoint,
    )
    assert evidence["blocked_read_outcome"] == "TRANSPORT_UNAVAILABLE"
    assert evidence["connections_restored"] is True
    assert isolation.connections_blocked is False

    class FalsePassTransport(Transport):
        def request(self, *args: Any, **kwargs: Any) -> HttpObservation:
            return HttpObservation(200, {}, json.dumps(run_body).encode())

    with pytest.raises(GateError, match="still succeeded"):
        run_vs01._prove_postgresql_causal_binding(  # type: ignore[arg-type]
            isolation,
            FalsePassTransport(),  # type: ignore[arg-type]
            checkpoint,
        )
    assert isolation.connections_blocked is False


def test_candidate_metadata_is_exactly_bound() -> None:
    document = _evidence_document()
    document["candidate"]["contract_revision"] = "0" * 40
    with pytest.raises(GateError, match="not runtime-bound real-product evidence"):
        run_vs01._evaluate_external_sse_evidence(document, expected_binding=_evidence_binding())
    document = _evidence_document()
    document["candidate"]["mock_business_responses"] = 0
    with pytest.raises(GateError, match="invalid types"):
        run_vs01._evaluate_external_sse_evidence(document, expected_binding=_evidence_binding())


def test_integrated_browser_command_requires_and_proves_node24(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    config = {
        "browser": {
            "cwd": str(tmp_path),
            "command": ("npm", "run", "test:real"),
            "node24_command": ("node24-launcher", "--call"),
            "timeout_seconds": 10,
        },
        "frontend": {"url": "http://127.0.0.1:4173"},
    }
    calls: list[list[str]] = []

    def command(command: Any, **kwargs: Any) -> Any:
        calls.append(list(command))
        if command[-1] == "node --version":
            return SimpleNamespace(returncode=0, stdout="v24.8.0\n")
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(run_vs01, "run_command", command)
    monkeypatch.setattr(
        run_vs01,
        "parse_playwright_result",
        lambda path: {"expected": 6, "unexpected": 0},
    )
    monkeypatch.setattr(
        run_vs01,
        "_playwright_control_evidence",
        lambda path: {
            control_id: {"status": "PASS"} for control_id in run_vs01.EXPECTED_BROWSER_CONTROLS
        },
    )
    artifact_root = tmp_path / "artifacts"
    result = run_vs01._run_browser(
        config,
        tmp_path / "scenario.json",
        artifact_root,
        secret_sentinel="VS01_SENTINEL_SELF_TEST",
    )
    assert result["node_version"] == "v24.8.0"
    assert calls == [
        ["node24-launcher", "--call", "node --version"],
        ["node24-launcher", "--call", "npm run test:real"],
    ]

    def wrong_version(command: Any, **kwargs: Any) -> Any:
        return SimpleNamespace(returncode=0, stdout="v25.0.0\n")

    monkeypatch.setattr(run_vs01, "run_command", wrong_version)
    with pytest.raises(GateError, match="did not prove Node 24"):
        run_vs01._run_browser(
            config,
            tmp_path / "scenario.json",
            artifact_root,
            secret_sentinel="VS01_SENTINEL_SELF_TEST",
        )


def test_playwright_controls_are_mapped_from_exact_passing_annotations(tmp_path: Any) -> None:
    test_record = {
        "expectedStatus": "passed",
        "status": "expected",
        "annotations": [
            {"type": "vs01-control", "description": control_id}
            for control_id in sorted(run_vs01.EXPECTED_BROWSER_CONTROLS)
        ],
        "results": [{"status": "passed", "errors": [], "duration": 10}],
    }
    path = tmp_path / "playwright-result.json"
    path.write_text(run_vs01.json.dumps({"suites": [{"tests": [test_record]}]}))
    controls = run_vs01._playwright_control_evidence(path)
    assert set(controls) == run_vs01.EXPECTED_BROWSER_CONTROLS
    report = {
        "summary": {"expected": 6, "unexpected": 0},
        "controls": controls,
        "node_version": "v24.8.0",
    }
    outcomes = run_vs01._browser_outcomes(report)
    assert all(outcomes[control_id]["status"] == "PASS" for control_id in controls)
    assert outcomes["VS01-ID-003"]["evidence"]["control_annotation"] == "VS01-ID-003"
    assert outcomes["VS01-DYN-001"]["evidence"]["control_annotation"] == ("VS01-DYN-001")

    failed = deepcopy(test_record)
    failed["results"] = [{"status": "failed", "errors": [{}], "duration": 10}]
    failed["status"] = "unexpected"
    path.write_text(run_vs01.json.dumps({"suites": [{"tests": [failed]}]}))
    with pytest.raises(GateError, match="annotated controls failed"):
        run_vs01._playwright_control_evidence(path)


def test_dynamic_fixture_timestamp_remains_public_contract_shape() -> None:
    assert NOW.endswith("Z")
    assert deepcopy(_evidence_document())["candidate"]["capture_session_nonce_sha256"] == "a" * 64
