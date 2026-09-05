from __future__ import annotations

import copy
import hashlib
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
    validate_confirm_response,
    validate_error_envelope,
    validate_research_object_detail,
    validate_research_run_draft,
    validate_run_collection,
    validate_standalone_run_detail,
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


def _object_identity() -> dict[str, Any]:
    return {
        "object_id": OBJECT_ID,
        "object_type": "public_company",
        "symbol": "VS01",
        "company_name": "VS01 Acceptance Corp",
        "exchange": "TEST",
        "sector": "Technology",
        "currency": "USD",
        "identity_version": 1,
    }


def _object_body() -> dict[str, Any]:
    return {
        "object": _object_identity(),
        "latest_released_run_id": None,
        "released_result_availability": _availability("NOT_RELEASED", "NO_RELEASED_RUN"),
        "run_count": 0,
        "last_activity": None,
        "created_at": NOW,
        "updated_at": NOW,
    }


def _draft_body() -> dict[str, Any]:
    body: dict[str, Any] = {
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
        "created_at": NOW,
        "expires_at": LATER,
    }
    canonical = json.dumps(body, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    body["draft_hash"] = f"sha256:{hashlib.sha256(canonical.encode()).hexdigest()}"
    return body


def _admission() -> dict[str, Any]:
    return {
        "schema_version": "phase4-run-admission/v1",
        "admission_id": ADMISSION_ID,
        "run_id": RUN_ID,
        "object_id": OBJECT_ID,
        "draft_id": DRAFT_ID,
        "draft_version": 1,
        "draft_hash": _draft_body()["draft_hash"],
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


def _run_detail(*, standalone: bool = False) -> dict[str, Any]:
    body: dict[str, Any] = {
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
    if standalone:
        body.update(
            {
                "terminal": False,
                "projection_revision": 2,
                "projection_sequence": 5,
            }
        )
    return body


def _availability(status: str, reason: str | None) -> dict[str, Any]:
    return {"status": status, "reason_code": reason, "retryable": False}


def _projection() -> dict[str, Any]:
    object_identity = _object_identity()
    run = _run_detail()
    task = {
        "task_id": "TASK-VS01",
        "run_id": RUN_ID,
        "parent_task_id": None,
        "task_type": "fundamental",
        "goal": "Analyze the exact public company",
        "assigned_agent": "fundamental_analyst",
        "skill_id": "fundamental-analysis-v1",
        "dependencies": [],
        "origin": "PLAN",
        "reason_code": None,
        "status": "RUNNING",
        "progress": 0.2,
        "attempt_count": 1,
        "task_input_evidence_ids": [],
        "task_output_evidence_ids": [],
        "evidence_acquisition_status": None,
        "evidence_source_coverage": {},
        "created_at": NOW,
    }
    return {
        "projection_schema_version": "phase4-run-projection/v1",
        "projection_revision": 2,
        "projection_sequence": 5,
        "generated_at": NOW,
        "object": object_identity,
        "run": run,
        "goal": {
            "goal_id": GOAL_ID,
            "research_object_id": OBJECT_ID,
            "goal_type": "comprehensive_equity_research",
            "goal_text": "Produce a verifiable full-company research report",
            "as_of": "2026-09-05",
            "preferences": {"language": "en"},
            "created_at": NOW,
        },
        "confirmed_scheme": {
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
        "review": {
            "availability": _availability("PENDING", "RUN_NONTERMINAL"),
            "review_id": None,
            "status": None,
        },
        "result": {
            "availability": _availability("PENDING", "RUN_NONTERMINAL"),
            "released_result_id": None,
            "canonical_record_id": None,
            "released_at": None,
        },
        "artifacts": {
            "availability": _availability("NOT_GENERATED", "RUN_NONTERMINAL"),
            "report_id": None,
            "representation_ids": [],
        },
        "proof": {
            "availability": _availability("NOT_GENERATED", "RUN_NONTERMINAL"),
            "policy": "UNKNOWN",
            "status": None,
            "proof_refs": [],
        },
        "execution": {
            "availability": _availability("NOT_GENERATED", "RUN_NONTERMINAL"),
            "canonical_record_id": None,
        },
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
                "activity": {
                    "event_id": "EVENT-VS01-5",
                    "type": "task.progress",
                    "sequence": 5,
                    "timestamp": NOW,
                    "task_id": "TASK-VS01",
                    "message_code": "TASK_PROGRESS",
                },
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
        self.confirm_idempotency_key: str | None = None
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
            if not (json_body or {}).get("symbol"):
                return _error(
                    code="REQUEST_VALIDATION_ERROR",
                    status=422,
                    recovery="NONE",
                )
            return _response(_object_body(), status=201)
        if method == "GET" and path == f"/api/objects/{OBJECT_ID}":
            return _response(_object_body())
        if method == "GET" and path.startswith("/api/objects/OBJ-MISSING-"):
            missing_id = path.removeprefix("/api/objects/")
            return _error(
                code="NOT_FOUND",
                status=404,
                recovery="NONE",
                resource={"type": "research_object", "id": missing_id},
            )
        if method == "GET" and path == f"/api/objects/{OBJECT_ID}/runs":
            return _response(_collection(with_run=self.run_created))
        if method == "POST" and path == "/api/research-runs/prepare":
            current = dict(json_body or {})
            object_id = current.get("research_object_id")
            if isinstance(object_id, str) and object_id.startswith("OBJ-MISSING-"):
                return _error(
                    code="NOT_FOUND",
                    status=404,
                    recovery="NONE",
                    resource={"type": "research_object", "id": object_id},
                )
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
            if current.get("draft_version") != 1:
                return _error(
                    code="CONFLICT",
                    status=409,
                    recovery="NONE",
                    reason_code="DRAFT_VERSION_MISMATCH",
                )
            request_key = request_headers.get("Idempotency-Key")
            if self.run_created and request_key != self.confirm_idempotency_key:
                return _error(
                    code="CONFLICT",
                    status=409,
                    recovery="NONE",
                    reason_code="DRAFT_CONSUMED",
                )
            if self.confirm_request is None:
                self.confirm_request = current
                self.confirm_idempotency_key = request_key
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
            return _response(_run_detail(standalone=True))
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


@pytest.mark.parametrize("route", ["/api/objects", "/api/research-runs/prepare"])
def test_harness_rejects_200_for_fixed_201_creation_routes(route: str) -> None:
    class WrongStatusTransport(ScriptedContractTransport):
        def request(self, method: str, path: str, **kwargs: Any) -> HttpObservation:
            response = super().request(method, path, **kwargs)
            if method == "POST" and path == route and response.status_code == 201:
                return HttpObservation(
                    status_code=200,
                    headers=response.headers,
                    body=response.body,
                )
            return response

    report = run_backend_vs01(_config(), transport=WrongStatusTransport())
    assert not report.passed


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


def _validate_projection_fixture(value: dict[str, Any]) -> None:
    validate_atomic_run_projection(
        value,
        expected_object_id=OBJECT_ID,
        expected_goal_id=GOAL_ID,
        expected_scheme_id=SCHEME_ID,
        expected_as_of="2026-09-05",
        expected_run_id=RUN_ID,
        expected_planned_graph_id=GRAPH_ID,
        etag=f'"p4:{RUN_ID}:2:5"',
    )


def _terminal_projection(status: str) -> dict[str, Any]:
    value = copy.deepcopy(_projection())
    task_status = {"RELEASED": "COMPLETED", "FAILED": "FAILED", "CANCELLED": "CANCELLED"}[status]
    for location in (
        value["planned_graph"]["tasks"],
        value["actual_graph"]["tasks"],
        value["tasks"],
    ):
        location[0]["status"] = task_status
        location[0]["progress"] = 1.0
    outcome = {"RELEASED": "SUCCESS", "FAILED": "FAILURE", "CANCELLED": "CANCELLED"}[status]
    value["run"].update(
        {
            "status": status,
            "stage": {"RELEASED": "COMPLETE", "FAILED": "FAILED", "CANCELLED": "CANCELLED"}[status],
            "completed_at": NOW,
        }
    )
    value["lifecycle"].update(
        {
            "status": status,
            "stage": value["run"]["stage"],
            "progress": {
                "method": "ACTUAL_TASK_MEAN_V1",
                "completed_tasks": 1 if status == "RELEASED" else 0,
                "total_tasks": 1,
                "fraction": 1.0,
            },
            "terminal": True,
            "terminal_outcome": outcome,
            "safe_failure": None
            if status == "RELEASED"
            else {
                "status": status,
                "failure_stage": "TASK_EXECUTION" if status == "FAILED" else "CANCELLATION",
                "failure_code": "TASK_EXECUTION_FAILED" if status == "FAILED" else "RUN_CANCELLED",
                "safe_message": "The run ended safely.",
            },
        }
    )
    value["activity"] = [
        {
            "event_id": "EVENT-terminal",
            "type": {
                "RELEASED": "run.completed",
                "FAILED": "run.failed",
                "CANCELLED": "run.cancelled",
            }[status],
            "sequence": 5,
            "timestamp": NOW,
            "task_id": None,
            "message_code": f"RUN_{status}",
        }
    ]
    value["terminal"] = {
        "is_terminal": True,
        "outcome": outcome,
        "event_id": "EVENT-terminal",
        "sequence": 5,
    }
    if status == "RELEASED":
        value["review"] = {
            "availability": _availability("AVAILABLE", None),
            "review_id": "review-1",
            "status": "PASS",
        }
        value["result"] = {
            "availability": _availability("AVAILABLE", None),
            "released_result_id": "result-1",
            "canonical_record_id": "canonical-1",
            "released_at": NOW,
        }
        value["artifacts"] = {
            "availability": _availability("AVAILABLE", None),
            "report_id": "report-1",
            "representation_ids": ["representation-html-1"],
        }
        value["proof"] = {
            "availability": _availability("AVAILABLE", None),
            "policy": "NOT_REQUIRED",
            "status": "NOT_REQUIRED",
            "proof_refs": [],
        }
        value["execution"] = {
            "availability": _availability("AVAILABLE", None),
            "canonical_record_id": "canonical-1",
        }
    else:
        for name in ("review", "result", "artifacts", "proof", "execution"):
            value[name]["availability"] = _availability("NOT_GENERATED", "RUN_TERMINAL")
    return value


def test_atomic_projection_decoder_fails_closed_for_nested_shape_and_identity_mutations() -> None:
    candidates: list[tuple[str, dict[str, Any]]] = []

    def mutated(label: str) -> dict[str, Any]:
        value = copy.deepcopy(_projection())
        candidates.append((label, value))
        return value

    mutated("top-level extra")["invented"] = True
    mutated("object extra")["object"]["invented"] = True
    mutated("object sector type")["object"]["sector"] = 7
    mutated("run missing field")["run"].pop("execution_target")
    mutated("run stage mismatch")["run"]["stage"] = "RESULT"
    mutated("Task status")["tasks"][0]["status"] = "INVENTED"
    mutated("Task progress scale")["tasks"][0]["progress"] = 50
    mutated("Task Run identity")["tasks"][0]["run_id"] = "RUN-FOREIGN"
    mutated("Task relationship closure")["tasks"][0]["dependencies"] = ["TASK-FOREIGN"]
    mutated("graph missing field")["planned_graph"].pop("version")
    mutated("unfrozen graph edge encoding")["planned_graph"]["edges"] = []
    mutated("lifecycle exact fields")["lifecycle"].pop("terminal_outcome")
    mutated("lifecycle non-failure payload")["lifecycle"]["safe_failure"] = {"code": "UNSAFE"}
    mutated("review exact fields")["review"].pop("status")
    mutated("review availability identity closure")["review"].update(
        {"review_id": "review-1", "status": "PASS"}
    )
    mutated("result timestamp")["result"]["released_at"] = 7
    mutated("result availability identity closure")["result"].update(
        {
            "released_result_id": "result-1",
            "canonical_record_id": "canonical-1",
            "released_at": NOW,
        }
    )
    mutated("artifact representation type")["artifacts"]["representation_ids"] = [7]
    mutated("artifact availability identity closure")["artifacts"].update(
        {"report_id": "report-1", "representation_ids": ["representation-html-1"]}
    )
    mutated("proof policy")["proof"]["policy"] = "INVENTED"
    mutated("execution availability identity closure")["execution"][
        "canonical_record_id"
    ] = "canonical-1"
    mutated("terminal exact fields")["terminal"]["invented"] = True
    mutated("activity Task closure")["activity"] = [
        {
            "event_id": "EVT-VS01",
            "type": "task.progress",
            "sequence": 5,
            "timestamp": NOW,
            "task_id": "TASK-FOREIGN",
            "message_code": None,
        }
    ]
    mutated("path-change exact fields")["path_changes"] = [
        {
            "path_change_id": "CORRECTION-VS01",
            "source_kind": "CORRECTION",
            "source_id": "CORRECTION-VS01",
            "change_kind": "SELF_CORRECTION",
            "status": "APPLIED",
            "decision": None,
            "reason_code": None,
            "task_refs": ["TASK-VS01"],
            "operations": [],
            "graph_version_before": None,
            "graph_version_after": None,
            "created_at": NOW,
            "resolved_at": NOW,
            "invented": True,
        }
    ]

    for label, candidate in candidates:
        with pytest.raises(ContractViolation) as rejection:
            _validate_projection_fixture(candidate)
        assert str(rejection.value), label


def test_object_and_draft_decoders_reject_unsafe_nested_schema_drift() -> None:
    object_body = _object_body()
    object_body["object"]["sector"] = 7
    with pytest.raises(ContractViolation, match="object.*sector"):
        validate_research_object_detail(object_body)

    expected = {
        "expected_object_id": OBJECT_ID,
        "expected_goal_text": "Produce a verifiable full-company research report",
        "expected_as_of": "2026-09-05",
        "expected_preferences": {"language": "en"},
    }
    goal_drift = _draft_body()
    goal_drift["goal"]["invented"] = True
    with pytest.raises(ContractViolation, match="draft.goal fields differ"):
        validate_research_run_draft(goal_drift, **expected)

    scheme_drift = _draft_body()
    scheme_drift["scheme_snapshot"].pop("generated_model")
    with pytest.raises(ContractViolation, match="draft.scheme_snapshot fields differ"):
        validate_research_run_draft(scheme_drift, **expected)


def test_object_detail_requires_exact_envelope_identity_and_release_closure() -> None:
    assert validate_research_object_detail(
        _object_body(), expected_object_id=OBJECT_ID
    ) == OBJECT_ID
    flat = {**_object_identity(), "created_at": NOW, "updated_at": NOW}
    released_state = {
        "schema_version": "phase4-released-object-core/v1",
        "object": _object_identity(),
    }
    candidates = []
    wrong_nested = _object_body()
    wrong_nested["object"]["object_id"] = "OBJ-FOREIGN"
    candidates.append(wrong_nested)
    inconsistent_release = _object_body()
    inconsistent_release["latest_released_run_id"] = "RUN-RELEASED"
    candidates.append(inconsistent_release)
    unknown = _object_body()
    unknown["invented"] = True
    candidates.extend([flat, released_state, unknown])
    for candidate in candidates:
        with pytest.raises(ContractViolation):
            validate_research_object_detail(candidate, expected_object_id=OBJECT_ID)


def test_exact_draft_confirm_collection_and_standalone_shapes_reject_drift() -> None:
    expected = {
        "expected_object_id": OBJECT_ID,
        "expected_goal_text": "Produce a verifiable full-company research report",
        "expected_as_of": "2026-09-05",
        "expected_preferences": {"language": "en"},
    }
    draft = validate_research_run_draft(_draft_body(), **expected)
    for candidate in (
        {**_draft_body(), "invented": True},
        {name: value for name, value in _draft_body().items() if name != "draft_hash"},
    ):
        with pytest.raises(ContractViolation, match="draft fields differ"):
            validate_research_run_draft(candidate, **expected)

    valid_confirm = _confirm_body(replayed=False)
    validate_confirm_response(
        valid_confirm,
        expected_draft=draft,
        expected_object_id=OBJECT_ID,
        expected_replayed=False,
    )
    for mutate in (
        lambda body: body.update({"invented": True}),
        lambda body: body["admission"].update({"invented": True}),
        lambda body: body["response_meta"].pop("request_id"),
        lambda body: body["admission"]["auto_start"].update({"invented": True}),
    ):
        candidate = copy.deepcopy(valid_confirm)
        mutate(candidate)
        with pytest.raises(ContractViolation, match="fields differ"):
            validate_confirm_response(
                candidate,
                expected_draft=draft,
                expected_object_id=OBJECT_ID,
                expected_replayed=False,
            )

    validate_run_collection(_collection(with_run=True), expected_object_id=OBJECT_ID)
    collection_extra = _collection(with_run=True)
    collection_extra["items"][0]["invented"] = True
    with pytest.raises(ContractViolation, match=r"collection.items\[0\] fields differ"):
        validate_run_collection(collection_extra, expected_object_id=OBJECT_ID)
    for mutate in (
        lambda item: item.update({"activity": None}),
        lambda item: item["activity"].update({"sequence": 4}),
        lambda item: item.update({"result_availability": _availability("AVAILABLE", None)}),
        lambda item: item["progress"].update({"fraction": 1.0}),
    ):
        candidate = _collection(with_run=True)
        mutate(candidate["items"][0])
        with pytest.raises(ContractViolation):
            validate_run_collection(candidate, expected_object_id=OBJECT_ID)

    validate_standalone_run_detail(
        _run_detail(standalone=True),
        object_id=OBJECT_ID,
        goal_id=GOAL_ID,
        scheme_id=SCHEME_ID,
        expected_as_of="2026-09-05",
        run_id=RUN_ID,
        planned_graph_id=GRAPH_ID,
    )
    missing_watermark = _run_detail(standalone=True)
    missing_watermark.pop("projection_sequence")
    with pytest.raises(ContractViolation, match="standalone run fields differ"):
        validate_standalone_run_detail(
            missing_watermark,
            object_id=OBJECT_ID,
            goal_id=GOAL_ID,
            scheme_id=SCHEME_ID,
            expected_as_of="2026-09-05",
            run_id=RUN_ID,
            planned_graph_id=GRAPH_ID,
        )


def test_projection_task_schema_relationships_cycles_and_nonfinite_numbers_fail_closed() -> None:
    required = {
        "task_id",
        "run_id",
        "parent_task_id",
        "task_type",
        "goal",
        "assigned_agent",
        "skill_id",
        "dependencies",
        "origin",
        "reason_code",
        "status",
        "progress",
        "attempt_count",
        "task_input_evidence_ids",
        "task_output_evidence_ids",
        "evidence_acquisition_status",
        "evidence_source_coverage",
        "created_at",
    }
    for field in required:
        candidate = copy.deepcopy(_projection())
        for container in (
            candidate["planned_graph"]["tasks"],
            candidate["actual_graph"]["tasks"],
            candidate["tasks"],
        ):
            container[0].pop(field, None)
        with pytest.raises(ContractViolation):
            _validate_projection_fixture(candidate)

    for bad_progress in (float("nan"), float("inf"), float("-inf")):
        candidate = copy.deepcopy(_projection())
        candidate["planned_graph"]["tasks"][0]["progress"] = bad_progress
        with pytest.raises(ContractViolation, match="progress"):
            _validate_projection_fixture(candidate)

    extra = copy.deepcopy(_projection())
    extra["planned_graph"]["tasks"][0]["result_ref"] = "internal://forbidden"
    with pytest.raises(ContractViolation, match="extra"):
        _validate_projection_fixture(extra)

    cycle = copy.deepcopy(_projection())
    second = copy.deepcopy(cycle["tasks"][0])
    second["task_id"] = "task-2"
    second["dependencies"] = ["TASK-VS01"]
    first = copy.deepcopy(cycle["tasks"][0])
    first["dependencies"] = ["task-2"]
    cycle["planned_graph"]["tasks"] = [copy.deepcopy(first), copy.deepcopy(second)]
    cycle["actual_graph"]["tasks"] = [copy.deepcopy(first), copy.deepcopy(second)]
    cycle["tasks"] = [first, second]
    with pytest.raises(ContractViolation, match="dependency cycle"):
        _validate_projection_fixture(cycle)


def test_projection_progress_activity_and_graph_nullability_are_causally_closed() -> None:
    wrong_mean = copy.deepcopy(_projection())
    wrong_mean["lifecycle"]["progress"]["fraction"] = 0.3
    with pytest.raises(ContractViolation, match="unweighted actual Task mean"):
        _validate_projection_fixture(wrong_mean)

    graph_tuple = copy.deepcopy(_projection())
    graph_tuple["actual_graph"] = None
    graph_tuple["graph_version"] = None
    with pytest.raises(ContractViolation, match="jointly null"):
        _validate_projection_fixture(graph_tuple)

    out_of_order = copy.deepcopy(_projection())
    out_of_order["activity"] = [
        {
            "event_id": "event-4",
            "type": "task.progress",
            "sequence": 4,
            "timestamp": NOW,
            "task_id": "TASK-VS01",
            "message_code": "TASK_PROGRESS",
        },
        {
            "event_id": "event-3",
            "type": "task.started",
            "sequence": 3,
            "timestamp": NOW,
            "task_id": "TASK-VS01",
            "message_code": "TASK_STARTED",
        },
    ]
    with pytest.raises(ContractViolation, match="unique and ascending"):
        _validate_projection_fixture(out_of_order)

    beyond = copy.deepcopy(_projection())
    beyond["activity"] = [
        {
            "event_id": "event-6",
            "type": "task.progress",
            "sequence": 6,
            "timestamp": NOW,
            "task_id": "TASK-VS01",
            "message_code": "TASK_PROGRESS",
        }
    ]
    with pytest.raises(ContractViolation, match="exceeds projection watermark"):
        _validate_projection_fixture(beyond)


def test_projection_accepts_source_native_correction_replan_and_all_terminal_outcomes() -> None:
    correction = copy.deepcopy(_projection())
    correction["path_changes"] = [
        {
            "path_change_id": "correction-1",
            "source_kind": "CORRECTION",
            "source_id": "correction-1",
            "change_kind": "SELF_CORRECTION",
            "status": "RESOLVED",
            "decision": None,
            "reason_code": "PERIOD_MISMATCH",
            "task_refs": ["TASK-VS01"],
            "operations": [],
            "graph_version_before": None,
            "graph_version_after": None,
            "created_at": NOW,
            "resolved_at": NOW,
        }
    ]
    _validate_projection_fixture(correction)

    approved = copy.deepcopy(_projection())
    second = copy.deepcopy(approved["tasks"][0])
    second.update(
        {
            "task_id": "task-2",
            "origin": "REPLAN",
            "reason_code": "CAPABILITY_GAP",
            "progress": 0.0,
        }
    )
    approved["actual_graph"]["version"] = 2
    approved["actual_graph"]["tasks"].append(copy.deepcopy(second))
    approved["graph_version"] = 2
    approved["tasks"].append(copy.deepcopy(second))
    approved["lifecycle"]["progress"].update(
        {"completed_tasks": 0, "total_tasks": 2, "fraction": 0.1}
    )
    approved["path_changes"] = [
        {
            "path_change_id": "replan-1",
            "source_kind": "REPLAN",
            "source_id": "replan-1",
            "change_kind": "ADD_TASK",
            "status": "APPROVED",
            "decision": "APPROVED",
            "reason_code": "CAPABILITY_GAP",
            "task_refs": ["task-2"],
            "operations": [{"operation": "add_node", "task_id": "task-2"}],
            "graph_version_before": 1,
            "graph_version_after": 2,
            "created_at": NOW,
            "resolved_at": NOW,
        }
    ]
    _validate_projection_fixture(approved)

    for status in ("RELEASED", "FAILED", "CANCELLED"):
        _validate_projection_fixture(_terminal_projection(status))


def test_projection_rejects_invalid_path_change_and_release_summary_combinations() -> None:
    for decision, resolved_at, after in (
        ("PENDING", NOW, None),
        ("REJECTED", NOW, 2),
        ("APPROVED", NOW, None),
    ):
        candidate = copy.deepcopy(_projection())
        candidate["path_changes"] = [
            {
                "path_change_id": "replan-invalid",
                "source_kind": "REPLAN",
                "source_id": "replan-invalid",
                "change_kind": "ADD_TASK",
                "status": decision,
                "decision": decision,
                "reason_code": "TEST",
                "task_refs": ["TASK-VS01"],
                "operations": []
                if decision != "APPROVED"
                else [{"operation": "add_node", "task_id": "TASK-VS01"}],
                "graph_version_before": 1 if decision == "APPROVED" else None,
                "graph_version_after": after,
                "created_at": NOW,
                "resolved_at": resolved_at,
            }
        ]
        with pytest.raises(ContractViolation):
            _validate_projection_fixture(candidate)

    unfrozen_edge = copy.deepcopy(_projection())
    unfrozen_edge["path_changes"] = [
        {
            "path_change_id": "replan-edge",
            "source_kind": "REPLAN",
            "source_id": "replan-edge",
            "change_kind": "CHANGE_DEPENDENCY",
            "status": "APPROVED",
            "decision": "APPROVED",
            "reason_code": "TEST",
            "task_refs": ["TASK-VS01"],
            "operations": [
                {
                    "operation": "add_edge",
                    "source_task_id": "TASK-VS01",
                    "target_task_id": "TASK-VS01",
                }
            ],
            "graph_version_before": 1,
            "graph_version_after": 2,
            "created_at": NOW,
            "resolved_at": NOW,
        }
    ]
    with pytest.raises(ContractViolation, match="fields differ"):
        _validate_projection_fixture(unfrozen_edge)

    promoted_edge = copy.deepcopy(unfrozen_edge)
    promoted_edge["path_changes"][0]["operations"] = [
        {
            "operation": "add_edge",
            "task_id": "TASK-VS01",
            "dependency_task_id": "TASK-VS01",
        }
    ]
    promoted_edge["graph_version"] = 2
    promoted_edge["actual_graph"]["version"] = 2
    _validate_projection_fixture(promoted_edge)

    released = _terminal_projection("RELEASED")
    released["review"]["status"] = "BLOCK"
    with pytest.raises(ContractViolation, match="PASS Review"):
        _validate_projection_fixture(released)

    failed = _terminal_projection("FAILED")
    failed["result"] = copy.deepcopy(_terminal_projection("RELEASED")["result"])
    with pytest.raises(ContractViolation, match="non-RELEASED"):
        _validate_projection_fixture(failed)


def test_strict_json_rejects_duplicate_members_and_nonstandard_constants() -> None:
    duplicate = HttpObservation(
        status_code=200,
        headers={"content-type": "application/json"},
        body=b'{"schema_version":"phase4-error/v1","schema_version":"other","error":{}}',
    )
    with pytest.raises(ContractViolation, match="valid UTF-8 JSON"):
        duplicate.json_object()

    nonstandard = HttpObservation(
        status_code=200,
        headers={"content-type": "application/json"},
        body=b'{"value":NaN}',
    )
    with pytest.raises(ContractViolation, match="valid UTF-8 JSON"):
        nonstandard.json_object()


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
