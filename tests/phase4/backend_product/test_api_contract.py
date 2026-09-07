from __future__ import annotations

import base64
import hashlib
from datetime import UTC, date, datetime, timedelta

from fastapi import FastAPI, Request
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from src.phase4_product.admission import build_prepare_draft
from src.phase4_product.api import (
    CONTRACT_HEADER,
    VerifiedArtifactBytes,
    create_phase4_product_router,
    install_phase4_error_handlers,
)
from src.phase4_product.contracts import (
    ArtifactSummaryV1,
    AtomicRunProjectionV1,
    AvailabilityStatus,
    AvailabilityV1,
    ConfirmResearchRunRequestV1,
    ConfirmRunResponseV1,
    ErrorCodeV1,
    ExecutionSummaryV1,
    GoalProjectionV1,
    GraphProjectionV1,
    ObjectIdentityV1,
    PrepareResearchRunRequestV1,
    ProofSummaryV1,
    ResearchObjectDetailV1,
    ResearchRunDetailV1,
    ResponseMetaV1,
    ResultSummaryV1,
    ReviewSummaryV1,
    RunAdmissionV1,
    RunLifecycleV1,
    RunProgressV1,
    SchemeProjectionV1,
    TerminalStateV1,
)
from src.phase4_product.errors import product_error

NOW = datetime(2026, 9, 5, 11, tzinfo=UTC)
HTML = b"<!doctype html><html><body>API artifact</body></html>"
HASH_A = "sha256:" + "a" * 64

EXPECTED_A_ROUTES = {
    ("POST", "/api/objects"),
    ("GET", "/api/objects"),
    ("GET", "/api/objects/{object_id}"),
    ("GET", "/api/objects/{object_id}/runs"),
    ("GET", "/api/objects/{object_id}/released-state"),
    ("GET", "/api/research-runs"),
    ("POST", "/api/research-runs/prepare"),
    ("POST", "/api/research-runs"),
    ("GET", "/api/research-runs/{run_id}"),
    ("GET", "/api/research-runs/{run_id}/projection"),
    ("GET", "/api/research-runs/{run_id}/results"),
    ("GET", "/api/research-runs/{run_id}/result"),
    ("GET", "/api/research-runs/{run_id}/report-view"),
    ("GET", "/api/research-runs/{run_id}/claims/{claim_id}"),
    ("GET", "/api/research-runs/{run_id}/review-view"),
    ("GET", "/api/research-runs/{run_id}/execution-view"),
    ("GET", "/api/research-runs/{run_id}/trace/{claim_id}"),
    ("GET", "/api/research-runs/{run_id}/artifacts"),
    ("GET", "/api/research-runs/{run_id}/artifacts/{artifact_id}/content"),
}


def _goal() -> GoalProjectionV1:
    return GoalProjectionV1(
        goal_id="GOAL-A",
        research_object_id="OBJ-A",
        goal_text="Exercise the Phase 4 API adapter",
        as_of=date(2026, 9, 5),
        created_at=NOW,
    )


def _scheme(*, confirmed: bool) -> SchemeProjectionV1:
    return SchemeProjectionV1(
        scheme_id="SCHEME-A",
        research_object_id="OBJ-A",
        goal_id="GOAL-A",
        generated_by="planner-v1",
        created_at=NOW,
        confirmed_at=NOW if confirmed else None,
    )


def _draft():
    request = PrepareResearchRunRequestV1(
        research_object_id="OBJ-A",
        research_goal=_goal().goal_text,
        as_of=date(2026, 9, 5),
    )
    return build_prepare_draft(
        request,
        draft_id="DRAFT-A",
        goal=_goal(),
        scheme_snapshot=_scheme(confirmed=False),
        created_at=NOW,
    )


def _admission() -> RunAdmissionV1:
    draft = _draft()
    return RunAdmissionV1(
        admission_id="ADMISSION-A",
        run_id="RUN-A",
        object_id="OBJ-A",
        draft_id=draft.draft_id,
        draft_version=draft.draft_version,
        draft_hash=draft.draft_hash,
        goal_id="GOAL-A",
        scheme_id="SCHEME-A",
        planned_graph_id="GRAPH-A",
        confirmation_request_hash=HASH_A,
        admitted_at=NOW + timedelta(minutes=1),
        projection_ref="/api/research-runs/RUN-A/projection",
        events_ref="/api/research-runs/RUN-A/events",
    )


def _projection() -> AtomicRunProjectionV1:
    pending = AvailabilityV1.unavailable(
        AvailabilityStatus.PENDING,
        "RUN_NONTERMINAL",
    )
    progress = RunProgressV1(completed_tasks=0, total_tasks=0, fraction=0.0)
    return AtomicRunProjectionV1(
        projection_revision=4,
        projection_sequence=7,
        generated_at=NOW,
        object=ObjectIdentityV1(
            object_id="OBJ-A",
            symbol="NVDA",
            company_name="NVIDIA Corporation",
            exchange="NASDAQ",
        ),
        run=ResearchRunDetailV1(
            run_id="RUN-A",
            research_object_id="OBJ-A",
            goal_id="GOAL-A",
            scheme_id="SCHEME-A",
            status="PLANNING",
            stage="PLANNING",
            as_of=date(2026, 9, 5),
            planned_graph_id="GRAPH-A",
            actual_graph_id=None,
            execution_target="SERVER_SANDBOX",
            created_at=NOW,
            updated_at=NOW,
            started_at=None,
            completed_at=None,
            terminal=False,
            projection_revision=4,
            projection_sequence=7,
        ),
        goal=_goal(),
        confirmed_scheme=_scheme(confirmed=True),
        planned_graph=GraphProjectionV1(
            graph_id="GRAPH-A",
            run_id="RUN-A",
            version=1,
            tasks=(),
        ),
        actual_graph=None,
        graph_version=None,
        tasks=(),
        path_changes=(),
        activity=(),
        lifecycle=RunLifecycleV1(
            status="PLANNING",
            stage="PLANNING",
            progress=progress,
            terminal=False,
            terminal_outcome=None,
            safe_failure=None,
        ),
        review=ReviewSummaryV1(availability=pending),
        result=ResultSummaryV1(availability=pending),
        artifacts=ArtifactSummaryV1(availability=pending),
        proof=ProofSummaryV1(
            availability=AvailabilityV1.unavailable(
                AvailabilityStatus.PENDING,
                "PROOF_PENDING",
            ),
            policy="UNKNOWN",
            status=None,
        ),
        execution=ExecutionSummaryV1(availability=pending),
        terminal=TerminalStateV1(
            is_terminal=False,
            outcome=None,
            event_id=None,
            sequence=None,
        ),
    )


class StubBackend:
    def __init__(self) -> None:
        self.replayed = False
        self.calls: list[str] = []
        self.object_error: Exception | None = None

    async def get_object(self, object_id: str) -> ResearchObjectDetailV1:
        self.calls.append("get_object")
        if self.object_error is not None:
            raise self.object_error
        return ResearchObjectDetailV1(
            object=ObjectIdentityV1(
                object_id=object_id,
                symbol="NVDA",
                company_name="NVIDIA Corporation",
                exchange="NASDAQ",
            ),
            latest_released_run_id=None,
            released_result_availability=AvailabilityV1.unavailable(
                AvailabilityStatus.NOT_RELEASED,
                "NO_RELEASED_RUN",
            ),
            run_count=0,
            created_at=NOW,
            updated_at=NOW,
        )

    async def prepare_run(self, payload, *, idempotency_key, request_id):
        del payload, idempotency_key, request_id
        self.calls.append("prepare_run")
        return _draft()

    async def confirm_run(self, payload, *, idempotency_key, request_id) -> ConfirmRunResponseV1:
        del payload, idempotency_key
        self.calls.append("confirm_run")
        return ConfirmRunResponseV1(
            admission=_admission(),
            response_meta=ResponseMetaV1(
                request_id=request_id,
                idempotency_replayed=self.replayed,
            ),
        )

    async def get_projection(self, run_id: str) -> AtomicRunProjectionV1:
        assert run_id == "RUN-A"
        self.calls.append("get_projection")
        return _projection()

    async def get_artifact_content(self, run_id: str, artifact_id: str) -> VerifiedArtifactBytes:
        assert (run_id, artifact_id) == ("RUN-A", "ART-A")
        self.calls.append("get_artifact_content")
        return VerifiedArtifactBytes(
            run_id=run_id,
            artifact_id=artifact_id,
            content=HTML,
            content_type="text/html; charset=utf-8",
            sha256=f"sha256:{hashlib.sha256(HTML).hexdigest()}",
            filename="report.html",
            disposition="inline",
        )


def _client() -> tuple[TestClient, StubBackend]:
    backend = StubBackend()
    app = FastAPI()
    request_sequence = 0

    @app.middleware("http")
    async def assign_server_request_id(request: Request, call_next):
        nonlocal request_sequence
        request_sequence += 1
        request.state.request_id = f"SERVER-REQUEST-{request_sequence}"
        return await call_next(request)

    app.state.phase4_product_backend = backend
    install_phase4_error_handlers(app)
    app.include_router(create_phase4_product_router())
    return TestClient(app, raise_server_exceptions=False), backend


def test_router_preserves_frozen_routes_and_adds_only_phase5a_memory() -> None:
    router = create_phase4_product_router()
    observed = {
        (method, route.path)
        for route in router.routes
        if isinstance(route, APIRoute)
        for method in route.methods
    }
    assert observed == EXPECTED_A_ROUTES | {
        ("GET", "/api/objects/{object_id}/memory"),
        ("POST", "/api/objects/{object_id}/memory/materialize"),
    }


def test_contract_version_is_admitted_before_backend_and_echoed_on_success() -> None:
    client, backend = _client()
    good = client.get(
        "/api/objects/OBJ-A",
        headers={CONTRACT_HEADER: "phase4-core/v1"},
    )
    assert good.status_code == 200
    assert good.headers["Content-Type"] == "application/json; charset=utf-8"
    assert good.headers[CONTRACT_HEADER] == "phase4-core/v1"
    assert backend.calls == ["get_object"]

    backend.calls.clear()
    bad = client.get(
        "/api/objects/OBJ-A",
        headers={CONTRACT_HEADER: "phase4-core/v2"},
    )
    assert bad.status_code == 409
    assert bad.headers["Content-Type"] == "application/json; charset=utf-8"
    assert bad.json()["error"] == {
        "code": "SCHEMA_INCOMPATIBLE",
        "message": "unsupported Phase 4 contract version",
        "retryable": False,
        "recovery": "NONE",
        "request_id": "SERVER-REQUEST-2",
        "resource": None,
        "details": {"supported_version": "phase4-core/v1"},
    }
    assert bad.json()["schema_version"] == "phase4-error/v1"
    assert backend.calls == []


def test_prepare_requires_idempotency_before_backend_mutation() -> None:
    client, backend = _client()
    payload = PrepareResearchRunRequestV1(
        research_object_id="OBJ-A",
        research_goal="Exercise the Phase 4 API adapter",
        as_of=date(2026, 9, 5),
    ).model_dump(mode="json")

    missing = client.post("/api/research-runs/prepare", json=payload)
    assert missing.status_code == 422
    assert missing.json()["error"]["code"] == "REQUEST_VALIDATION_ERROR"
    assert missing.json()["error"]["details"] == {"field": "Idempotency-Key"}
    assert backend.calls == []

    created = client.post(
        "/api/research-runs/prepare",
        json=payload,
        headers={"Idempotency-Key": "PREPARE-K1"},
    )
    assert created.status_code == 201
    assert created.headers[CONTRACT_HEADER] == "phase4-core/v1"
    assert created.json()["schema_version"] == "phase4-run-draft/v1"
    assert backend.calls == ["prepare_run"]


def test_confirm_uses_201_then_200_and_never_trusts_caller_request_id() -> None:
    client, backend = _client()
    draft = _draft()
    payload = ConfirmResearchRunRequestV1(
        draft_id=draft.draft_id,
        draft_version=draft.draft_version,
        draft_hash=draft.draft_hash,
        research_object_id=draft.object_id,
        confirm_scheme=True,
    ).model_dump(mode="json")
    headers = {"Idempotency-Key": "CONFIRM-K1", "X-Request-ID": "REQ-FIRST"}

    first = client.post("/api/research-runs", json=payload, headers=headers)
    backend.replayed = True
    replay = client.post(
        "/api/research-runs",
        json=payload,
        headers={**headers, "X-Request-ID": "REQ-REPLAY"},
    )

    assert first.status_code == 201
    assert replay.status_code == 200
    assert first.json()["admission"] == replay.json()["admission"]
    assert first.json()["response_meta"]["idempotency_replayed"] is False
    assert replay.json()["response_meta"]["idempotency_replayed"] is True
    assert first.json()["response_meta"]["request_id"] == "SERVER-REQUEST-1"
    assert replay.json()["response_meta"]["request_id"] == "SERVER-REQUEST-2"
    assert first.json()["response_meta"]["request_id"] != "REQ-FIRST"
    assert replay.json()["response_meta"]["request_id"] != "REQ-REPLAY"


def test_contract_rejection_precedes_body_validation_error_handler() -> None:
    client, backend = _client()
    response = client.post(
        "/api/research-runs/prepare",
        json={"unknown": "must-not-be-reflected"},
        headers={
            CONTRACT_HEADER: "phase4-core/v999",
            "Idempotency-Key": "PREPARE-K1",
            "X-Request-ID": "CALLER-CONTROLLED",
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SCHEMA_INCOMPATIBLE"
    assert response.json()["error"]["request_id"] == "SERVER-REQUEST-1"
    assert "must-not-be-reflected" not in response.text
    assert "CALLER-CONTROLLED" not in response.text
    assert backend.calls == []


def test_product_error_precedes_generic_handler_and_generic_failure_is_sanitized() -> None:
    client, backend = _client()
    backend.object_error = product_error(
        ErrorCodeV1.NOT_FOUND,
        "the exact object does not exist",
        resource_type="research_object",
        resource_id="OBJ-A",
    )
    missing = client.get("/api/objects/OBJ-A")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "NOT_FOUND"
    assert missing.json()["error"]["resource"] == {
        "type": "research_object",
        "id": "OBJ-A",
    }

    backend.object_error = RuntimeError(
        "api_key=must-not-leak at /Users/operator/private/backend.py"
    )
    failed = client.get("/api/objects/OBJ-A")
    assert failed.status_code == 500
    assert failed.json()["error"]["code"] == "INTERNAL_ERROR"
    assert failed.json()["error"]["message"] == "an internal product error occurred"
    assert "must-not-leak" not in failed.text
    assert "/Users/operator" not in failed.text


def test_projection_response_has_exact_atomic_etag() -> None:
    client, _ = _client()
    response = client.get("/api/research-runs/RUN-A/projection")
    assert response.status_code == 200
    assert response.headers["ETag"] == '"p4:RUN-A:4:7"'
    assert response.headers[CONTRACT_HEADER] == "phase4-core/v1"
    assert response.json()["projection_schema_version"] == "phase4-run-projection/v1"


def test_artifact_route_preserves_verified_bytes_and_exact_headers() -> None:
    client, backend = _client()
    response = client.get("/api/research-runs/RUN-A/artifacts/ART-A/content")

    assert response.status_code == 200
    assert response.content == HTML
    assert response.headers["Content-Type"] == "text/html; charset=utf-8"
    assert response.headers["Content-Length"] == str(len(HTML))
    assert response.headers["Digest"] == (
        "sha-256=" + base64.b64encode(hashlib.sha256(HTML).digest()).decode("ascii")
    )
    assert response.headers["ETag"] == f'"sha256-{hashlib.sha256(HTML).hexdigest()}"'
    assert response.headers["Content-Disposition"] == 'inline; filename="report.html"'
    assert response.headers["Cache-Control"] == "private, no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers[CONTRACT_HEADER] == "phase4-core/v1"
    assert backend.calls == ["get_artifact_content"]


def test_artifact_route_rejects_self_consistent_foreign_bytes() -> None:
    client, backend = _client()

    async def foreign_artifact(
        _run_id: str,
        _artifact_id: str,
    ) -> VerifiedArtifactBytes:
        backend.calls.append("get_artifact_content")
        return VerifiedArtifactBytes(
            run_id="RUN-B",
            artifact_id="ART-B",
            content=HTML,
            content_type="text/html; charset=utf-8",
            sha256=f"sha256:{hashlib.sha256(HTML).hexdigest()}",
            filename="report.html",
            disposition="inline",
        )

    backend.get_artifact_content = foreign_artifact  # type: ignore[method-assign]
    response = client.get("/api/research-runs/RUN-A/artifacts/ART-A/content")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "IDENTITY_MISMATCH"
    assert response.content != HTML
    assert backend.calls == ["get_artifact_content"]


def test_range_rejection_uses_error_envelope_before_artifact_lookup() -> None:
    client, backend = _client()
    response = client.get(
        "/api/research-runs/RUN-A/artifacts/ART-A/content",
        headers={"Range": "bytes=0-10"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "REQUEST_VALIDATION_ERROR"
    assert response.json()["error"]["details"] == {"reason_code": "RANGE_NOT_SUPPORTED"}
    assert backend.calls == []


def test_body_validation_error_is_safe_and_never_reaches_backend() -> None:
    client, backend = _client()
    response = client.post(
        "/api/research-runs/prepare",
        json={"research_object_id": "OBJ-A", "unknown": "secret"},
        headers={"Idempotency-Key": "PREPARE-K1"},
    )
    assert response.status_code == 422
    assert response.json()["schema_version"] == "phase4-error/v1"
    assert response.json()["error"]["code"] == "REQUEST_VALIDATION_ERROR"
    assert response.json()["error"]["details"]["errors"]
    assert "secret" not in response.text
    assert backend.calls == []
