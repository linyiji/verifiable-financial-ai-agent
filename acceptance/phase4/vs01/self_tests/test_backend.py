from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from typing import Any

import pytest

from acceptance.phase4.vs01.harness.backend import (
    BackendHarnessConfig,
    ContractViolation,
    HttpObservation,
    RestartEvidence,
    run_backend_vs01,
    validate_atomic_run_projection,
    validate_error_envelope,
    verify_restart_checkpoint,
)

NOW = "2026-09-05T06:00:00Z"
LATER = "2026-09-05T06:30:00Z"
OBJECT_ID = "OBJ-VS01"
GOAL_ID = "GOAL-VS01"
SCHEME_ID = "SCHEME-VS01"
DRAFT_ID = "DRAFT-VS01"
RUN_ID = "RUN-VS01"
GRAPH_ID = "GRAPH-VS01"
ACTUAL_GRAPH_ID = "GRAPH-VS01-ACTUAL"
ADMISSION_ID = "ADMISSION-VS01"


def _response(
    body: Mapping[str, Any],
    *,
    status: int = 200,
    etag: str | None = None,
) -> HttpObservation:
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "X-Phase4-Contract-Version": "phase4-core/v1",
    }
    if etag is not None:
        headers["ETag"] = etag
    return HttpObservation(
        status_code=status,
        headers=headers,
        body=json.dumps(dict(body), separators=(",", ":")).encode(),
    )


def _error(
    code: str,
    *,
    status: int,
    recovery: str,
    retryable: bool = False,
    resource: Mapping[str, str] | None = None,
    reason_code: str | None = None,
) -> HttpObservation:
    details = {} if reason_code is None else {"reason_code": reason_code}
    return _response(
        {
            "schema_version": "phase4-error/v1",
            "error": {
                "code": code,
                "message": "safe contract error",
                "retryable": retryable,
                "recovery": recovery,
                "request_id": "REQ-VS01",
                "resource": dict(resource) if resource is not None else None,
                "details": details,
            },
        },
        status=status,
    )


def _object_body() -> dict[str, Any]:
    return {
        "object_id": OBJECT_ID,
        "object_type": "public_company",
        "symbol": "VS01",
        "company_name": "VS01 Acceptance Corp",
        "exchange": "TEST",
        "sector": "Technology",
        "currency": "USD",
        "identity_version": 1,
        "created_at": NOW,
        "updated_at": NOW,
    }


def _draft_body() -> dict[str, Any]:
    return {
        "schema_version": "phase4-run-draft/v1",
        "draft_id": DRAFT_ID,
        "draft_version": 1,
        "status": "AWAITING_CONFIRMATION",
        "preview_kind": "SCHEME_ONLY",
        "planned_graph_availability": {
            "status": "NOT_GENERATED",
            "reason_code": "PLAN_CREATED_ON_CONFIRM",
            "retryable": False,
        },
        "object_id": OBJECT_ID,
        "goal": {
            "goal_id": GOAL_ID,
            "research_object_id": OBJECT_ID,
            "goal_type": "comprehensive_equity_research",
            "goal_text": "Produce a verifiable full-company research report",
            "as_of": "2026-09-05",
            "preferences": {"language": "en"},
            "created_at": NOW,
        },
        "scheme_snapshot": {
            "scheme_id": SCHEME_ID,
            "research_object_id": OBJECT_ID,
            "goal_id": GOAL_ID,
            "research_scope": ["fundamentals"],
            "data_requirements": ["filings"],
            "agent_requirements": ["fundamental_analyst"],
            "skill_requirements": [],
            "calculation_requirements": ["revenue_growth_v1"],
            "assurance_requirements": {"independent_review": True},
            "report_requirements": ["HTML"],
            "limitations": [],
            "generated_by": "research_lead_agent",
            "generated_model": None,
            "created_at": NOW,
            "confirmed_at": None,
        },
        "prepare_request_hash": f"sha256:{'1' * 64}",
        "draft_hash": f"sha256:{'2' * 64}",
        "created_at": NOW,
        "expires_at": LATER,
    }


def _admission() -> dict[str, Any]:
    return {
        "schema_version": "phase4-run-admission/v1",
        "admission_id": ADMISSION_ID,
        "run_id": RUN_ID,
        "object_id": OBJECT_ID,
        "draft_id": DRAFT_ID,
        "draft_version": 1,
        "draft_hash": f"sha256:{'2' * 64}",
        "goal_id": GOAL_ID,
        "scheme_id": SCHEME_ID,
        "planned_graph_id": GRAPH_ID,
        "status": "PLANNING",
        "auto_start": {"required": True, "admitted": True},
        "confirmation_request_hash": f"sha256:{'3' * 64}",
        "admitted_at": NOW,
        "projection_ref": f"/api/research-runs/{RUN_ID}/projection",
        "events_ref": f"/api/research-runs/{RUN_ID}/events",
    }


def _confirm_body(*, replayed: bool) -> dict[str, Any]:
    return {
        "schema_version": "phase4-confirm-response/v1",
        "admission": _admission(),
        "response_meta": {
            "schema_version": "phase4-response-meta/v1",
            "request_id": "REQ-VS01",
            "idempotency_replayed": replayed,
        },
    }


def _run_detail() -> dict[str, Any]:
    return {
        "run_id": RUN_ID,
        "research_object_id": OBJECT_ID,
        "goal_id": GOAL_ID,
        "scheme_id": SCHEME_ID,
        "status": "RUNNING",
        "stage": "RESEARCH",
        "as_of": "2026-09-05",
        "planned_graph_id": GRAPH_ID,
        "actual_graph_id": ACTUAL_GRAPH_ID,
        "execution_target": "SERVER_SANDBOX",
        "created_at": NOW,
        "updated_at": NOW,
        "started_at": NOW,
        "completed_at": None,
    }


def _availability(status: str, reason: str | None) -> dict[str, Any]:
    return {"status": status, "reason_code": reason, "retryable": False}


def _projection() -> dict[str, Any]:
    object_identity = _object_body()
    object_identity.pop("created_at")
    object_identity.pop("updated_at")
    run = _run_detail()
    task = {
        "task_id": "TASK-VS01",
        "run_id": RUN_ID,
        "status": "RUNNING",
    }
    return {
        "projection_schema_version": "phase4-run-projection/v1",
        "projection_revision": 2,
        "projection_sequence": 5,
        "generated_at": NOW,
        "object": object_identity,
        "run": run,
        "goal": {"goal_id": GOAL_ID, "research_object_id": OBJECT_ID},
        "confirmed_scheme": {
            "scheme_id": SCHEME_ID,
            "research_object_id": OBJECT_ID,
            "goal_id": GOAL_ID,
            "confirmed_at": NOW,
        },
        "planned_graph": {
            "graph_id": GRAPH_ID,
            "run_id": RUN_ID,
            "version": 1,
            "tasks": [task],
        },
        "actual_graph": {
            "graph_id": ACTUAL_GRAPH_ID,
            "run_id": RUN_ID,
            "version": 1,
            "tasks": [task],
        },
        "graph_version": 1,
        "tasks": [task],
        "path_changes": [],
        "activity": [],
        "lifecycle": {
            "status": "RUNNING",
            "stage": "RESEARCH",
            "progress": {
                "method": "ACTUAL_TASK_MEAN_V1",
                "completed_tasks": 0,
                "total_tasks": 1,
                "fraction": 0.2,
            },
            "terminal": False,
            "terminal_outcome": None,
            "safe_failure": None,
        },
        "review": {"availability": _availability("PENDING", "RUN_NONTERMINAL")},
        "result": {"availability": _availability("PENDING", "RUN_NONTERMINAL")},
        "artifacts": {"availability": _availability("NOT_GENERATED", "RUN_NONTERMINAL")},
        "proof": {
            "availability": _availability("NOT_GENERATED", "RUN_NONTERMINAL"),
            "policy": "UNKNOWN",
            "status": None,
            "proof_refs": [],
        },
        "execution": {"availability": _availability("NOT_GENERATED", "RUN_NONTERMINAL")},
        "terminal": {
            "is_terminal": False,
            "outcome": None,
            "event_id": None,
            "sequence": None,
        },
    }


def _collection(*, with_run: bool) -> dict[str, Any]:
    items = []
    if with_run:
        items.append(
            {
                "run_id": RUN_ID,
                "object": {
                    "object_id": OBJECT_ID,
                    "symbol": "VS01",
                    "company_name": "VS01 Acceptance Corp",
                },
                "status": "RUNNING",
                "stage": "RESEARCH",
                "progress": {
                    "method": "ACTUAL_TASK_MEAN_V1",
                    "completed_tasks": 0,
                    "total_tasks": 1,
                    "fraction": 0.2,
                },
                "activity": None,
                "graph_version": 1,
                "projection_revision": 2,
                "projection_sequence": 5,
                "as_of": "2026-09-05",
                "created_at": NOW,
                "updated_at": NOW,
                "started_at": NOW,
                "completed_at": None,
                "terminal": False,
                "result_availability": _availability("PENDING", "RUN_NONTERMINAL"),
            }
        )
    return {
        "schema_version": "phase4-run-collection/v1",
        "items": items,
        "next_cursor": None,
    }


class ScriptedContractTransport:
    """A pure contract server used only to self-test harness decisions."""

    def __init__(self) -> None:
        self.run_created = False
        self.prepare_request: dict[str, Any] | None = None
        self.confirm_request: dict[str, Any] | None = None
        self.confirm_successes = 0

    def request(
        self,
        method: str,
        path: str,
        *,
        headers: Mapping[str, str] | None = None,
        json_body: Mapping[str, Any] | None = None,
    ) -> HttpObservation:
        request_headers = dict(headers or {})
        if request_headers.get("X-Phase4-Contract-Version") == "phase4-core/v999":
            return _error(code="SCHEMA_INCOMPATIBLE", status=409, recovery="NONE")
        if method == "POST" and path == "/api/objects":
            return _response(_object_body(), status=201)
        if method == "GET" and path == f"/api/objects/{OBJECT_ID}":
            return _response(_object_body())
        if method == "GET" and path == f"/api/objects/{OBJECT_ID}/runs":
            return _response(_collection(with_run=self.run_created))
        if method == "POST" and path == "/api/research-runs/prepare":
            current = dict(json_body or {})
            if self.prepare_request is None:
                self.prepare_request = current
            elif current != self.prepare_request:
                return _error(
                    code="CONFLICT",
                    status=409,
                    recovery="NONE",
                    reason_code="IDEMPOTENCY_REQUEST_MISMATCH",
                )
            return _response(_draft_body(), status=201)
        if method == "POST" and path == "/api/research-runs":
            current = dict(json_body or {})
            if self.confirm_request is None:
                self.confirm_request = current
            elif current != self.confirm_request:
                return _error(
                    code="CONFLICT",
                    status=409,
                    recovery="NONE",
                    reason_code="IDEMPOTENCY_REQUEST_MISMATCH",
                )
            self.run_created = True
            replayed = self.confirm_successes > 0
            self.confirm_successes += 1
            return _response(_confirm_body(replayed=replayed), status=200 if replayed else 201)
        if method == "GET" and path == f"/api/research-runs/{RUN_ID}":
            return _response(_run_detail())
        if method == "GET" and path == f"/api/research-runs/{RUN_ID}/projection":
            return _response(_projection(), etag=f'"p4:{RUN_ID}:2:5"')
        if method == "GET" and path.startswith("/api/research-runs/RUN-MISSING-"):
            missing_id = path.removeprefix("/api/research-runs/")
            return _error(
                code="NOT_FOUND",
                status=404,
                recovery="NONE",
                resource={"type": "research_run", "id": missing_id},
            )
        raise AssertionError(f"unexpected scripted request: {method} {path}")


def _config() -> BackendHarnessConfig:
    return BackendHarnessConfig(
        base_url="http://127.0.0.1:8000",
        object_request={
            "symbol": "vs01",
            "company_name": "VS01 Acceptance Corp",
            "exchange": "TEST",
            "sector": "Technology",
            "currency": "USD",
        },
        research_goal="Produce a verifiable full-company research report",
        as_of="2026-09-05",
        preferences={"language": "en"},
        object_idempotency_key="object-key",
        prepare_idempotency_key="prepare-key",
        confirm_idempotency_key="confirm-key",
        auto_start_timeout_seconds=0,
    )


def test_pre_restart_harness_accepts_only_the_frozen_journey() -> None:
    report = run_backend_vs01(_config(), transport=ScriptedContractTransport())

    assert report.passed
    assert report.checkpoint is not None
    assert report.checkpoint.run_id == RUN_ID
    assert len(report.controls) == 11
    serialized = json.dumps(report.to_dict(), sort_keys=True)
    assert "confirm-key" not in serialized
    assert "prepare-key" not in serialized
    assert "object-key" not in serialized


def test_post_restart_harness_requires_and_accepts_postgresql_boundary_evidence() -> None:
    transport = ScriptedContractTransport()
    pre = run_backend_vs01(_config(), transport=transport)
    assert pre.checkpoint is not None

    post = verify_restart_checkpoint(
        _config(),
        pre.checkpoint,
        RestartEvidence(
            process_boundary_id="PROC-BOUNDARY-1",
            api_process_restarted=True,
            persistence_backend="PostgreSQL 16",
            storage_preserved=True,
        ),
        transport=transport,
    )

    assert post.passed
    assert [control.control_id for control in post.controls] == [
        "VS01-BE-014",
        "VS01-BE-012",
        "VS01-BE-013",
    ]


def test_projection_validator_rejects_cross_object_substitution() -> None:
    projection = copy.deepcopy(_projection())
    projection["object"]["object_id"] = "OBJ-FOREIGN"

    with pytest.raises(ContractViolation, match="projection.object.object_id"):
        validate_atomic_run_projection(
            projection,
            expected_object_id=OBJECT_ID,
            expected_goal_id=GOAL_ID,
            expected_scheme_id=SCHEME_ID,
            expected_as_of="2026-09-05",
            expected_run_id=RUN_ID,
            expected_planned_graph_id=GRAPH_ID,
            etag=f'"p4:{RUN_ID}:2:5"',
        )


def test_error_validator_rejects_wrong_retry_recovery_tuple() -> None:
    wrong = _error(
        code="TRANSIENT_BACKEND_ERROR",
        status=503,
        recovery="NONE",
        retryable=False,
    )

    with pytest.raises(ContractViolation, match="retryable"):
        validate_error_envelope(wrong, expected_code="TRANSIENT_BACKEND_ERROR")


def test_restart_verifier_fails_without_real_postgresql_evidence() -> None:
    transport = ScriptedContractTransport()
    pre = run_backend_vs01(_config(), transport=transport)
    assert pre.checkpoint is not None

    post = verify_restart_checkpoint(
        _config(),
        pre.checkpoint,
        RestartEvidence(
            process_boundary_id="PROC-BOUNDARY-INVALID",
            api_process_restarted=True,
            persistence_backend="sqlite-memory",
            storage_preserved=True,
        ),
        transport=transport,
    )

    assert not post.passed
    assert post.controls[0].control_id == "VS01-BE-014"
    assert post.controls[0].status == "FAIL"
