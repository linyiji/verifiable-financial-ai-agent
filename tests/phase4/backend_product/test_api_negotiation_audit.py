"""Audit the pre-body media-negotiation boundary on every A-owned route."""

from __future__ import annotations

import hashlib
from datetime import date

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from src.phase4_product.api import (
    CONTRACT_HEADER,
    VerifiedArtifactBytes,
    create_phase4_product_router,
    install_phase4_error_handlers,
)
from src.phase4_product.errors import product_error

HTML = b"<!doctype html><html><body>negotiated artifact</body></html>"

ROUTES = (
    ("POST", "/api/objects"),
    ("GET", "/api/objects"),
    ("GET", "/api/objects/OBJ-A"),
    ("GET", "/api/objects/OBJ-A/runs"),
    ("GET", "/api/objects/OBJ-A/released-state"),
    ("GET", "/api/research-runs"),
    ("POST", "/api/research-runs/prepare"),
    ("POST", "/api/research-runs"),
    ("GET", "/api/research-runs/RUN-A"),
    ("GET", "/api/research-runs/RUN-A/projection"),
    ("GET", "/api/research-runs/RUN-A/result"),
    ("GET", "/api/research-runs/RUN-A/claims/CLAIM-A"),
    ("GET", "/api/research-runs/RUN-A/review-view"),
    ("GET", "/api/research-runs/RUN-A/execution-view"),
    ("GET", "/api/research-runs/RUN-A/trace/CLAIM-A"),
    ("GET", "/api/research-runs/RUN-A/artifacts"),
    ("GET", "/api/research-runs/RUN-A/artifacts/ART-A/content"),
)


class CountingBackend:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def __getattr__(self, name: str):
        async def unexpected_call(*_args, **_kwargs):
            self.calls.append(name)
            raise product_error("CONFLICT", "backend sentinel reached")

        return unexpected_call

    async def get_artifact_content(
        self,
        _run_id: str,
        _artifact_id: str,
    ) -> VerifiedArtifactBytes:
        self.calls.append("get_artifact_content")
        return VerifiedArtifactBytes(
            run_id=_run_id,
            artifact_id=_artifact_id,
            content=HTML,
            content_type="text/html; charset=utf-8",
            sha256=f"sha256:{hashlib.sha256(HTML).hexdigest()}",
            filename="report.html",
            disposition="inline",
        )


def _client() -> tuple[TestClient, CountingBackend]:
    app = FastAPI()
    backend = CountingBackend()

    @app.middleware("http")
    async def assign_request_id(request: Request, call_next):
        request.state.request_id = "SERVER-NEGOTIATION"
        return await call_next(request)

    app.state.phase4_product_backend = backend
    install_phase4_error_handlers(app)
    app.include_router(create_phase4_product_router())
    return TestClient(app, raise_server_exceptions=False), backend


def _assert_media_incompatible(response) -> None:
    assert response.status_code == 409
    assert response.headers["Content-Type"] == "application/json; charset=utf-8"
    assert response.headers[CONTRACT_HEADER] == "phase4-core/v1"
    assert response.json() == {
        "schema_version": "phase4-error/v1",
        "error": {
            "code": "SCHEMA_INCOMPATIBLE",
            "message": "unsupported response media type",
            "retryable": False,
            "recovery": "NONE",
            "request_id": "SERVER-NEGOTIATION",
            "resource": None,
            "details": {},
        },
    }


@pytest.mark.parametrize(("method", "url"), ROUTES)
def test_every_a_route_rejects_unsupported_accept_before_parsing_or_backend(
    method: str,
    url: str,
) -> None:
    client, backend = _client()
    response = client.request(
        method,
        url,
        content=b"{not-json",
        headers={
            "Accept": "application/xml",
            "Content-Type": "application/json",
            "Idempotency-Key": "NEGOTIATION-K1",
        },
    )

    _assert_media_incompatible(response)
    assert backend.calls == []


@pytest.mark.parametrize(
    "url",
    (
        "/api/objects",
        "/api/research-runs/prepare",
        "/api/research-runs",
    ),
)
def test_body_routes_reject_non_json_content_type_before_body_parse(url: str) -> None:
    client, backend = _client()
    response = client.post(
        url,
        content=b"{not-json",
        headers={
            "Accept": "application/json",
            "Content-Type": "text/plain",
            "Idempotency-Key": "NEGOTIATION-K1",
        },
    )

    assert response.status_code == 409
    assert response.json()["error"] == {
        "code": "SCHEMA_INCOMPATIBLE",
        "message": "unsupported request media type",
        "retryable": False,
        "recovery": "NONE",
        "request_id": "SERVER-NEGOTIATION",
        "resource": None,
        "details": {},
    }
    assert backend.calls == []


def test_contract_version_rejection_precedes_both_media_gates() -> None:
    client, backend = _client()
    response = client.post(
        "/api/research-runs/prepare",
        content=b"{not-json",
        headers={
            CONTRACT_HEADER: "phase4-core/v999",
            "Accept": "application/xml",
            "Content-Type": "text/plain",
            "Idempotency-Key": "NEGOTIATION-K1",
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["message"] == "unsupported Phase 4 contract version"
    assert response.json()["error"]["details"] == {"supported_version": "phase4-core/v1"}
    assert backend.calls == []


def test_supported_json_negotiation_and_get_without_body_reach_backend() -> None:
    client, backend = _client()
    get_response = client.get(
        "/api/objects/OBJ-A",
        headers={
            "Accept": "application/xml;q=0.8, application/json; charset=UTF-8; q=0.2",
            # A no-body route does not acquire a request-media requirement.
            "Content-Type": "text/plain",
        },
    )

    assert get_response.status_code == 409
    assert get_response.json()["error"]["code"] == "CONFLICT"
    assert backend.calls == ["get_object"]

    backend.calls.clear()
    prepare_response = client.post(
        "/api/research-runs/prepare",
        json={
            "research_object_id": "OBJ-A",
            "research_goal": "Audit supported JSON negotiation",
            "as_of": date(2026, 9, 5).isoformat(),
            "preferences": {},
        },
        headers={
            "Accept": "application/*",
            "Content-Type": "application/json; charset=UTF-8",
            "Idempotency-Key": "NEGOTIATION-K1",
        },
    )

    assert prepare_response.status_code == 409
    assert prepare_response.json()["error"]["code"] == "CONFLICT"
    assert backend.calls == ["prepare_run"]


@pytest.mark.parametrize(
    "accept",
    [
        "application/json;q=0, */*;q=1",
        "*/*;q=1, application/json;q=0",
        "application/*;q=0, */*;q=1",
    ],
)
def test_specific_json_q_zero_overrides_positive_wildcard(accept: str) -> None:
    client, backend = _client()

    response = client.get("/api/objects/OBJ-A", headers={"Accept": accept})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SCHEMA_INCOMPATIBLE"
    assert backend.calls == []


def test_artifact_route_negotiates_recorded_representation() -> None:
    client, backend = _client()
    html_response = client.get(
        "/api/research-runs/RUN-A/artifacts/ART-A/content",
        headers={"Accept": "text/html; charset=utf-8"},
    )

    assert html_response.status_code == 200
    assert html_response.content == HTML
    assert backend.calls == ["get_artifact_content"]

    backend.calls.clear()
    pdf_only_response = client.get(
        "/api/research-runs/RUN-A/artifacts/ART-A/content",
        headers={"Accept": "application/pdf"},
    )

    assert pdf_only_response.status_code == 409
    assert pdf_only_response.json()["error"]["code"] == "SCHEMA_INCOMPATIBLE"
    assert backend.calls == ["get_artifact_content"]


@pytest.mark.parametrize(
    "accept",
    [
        "text/*;q=0, */*;q=1",
        "*/*;q=1, text/html;q=0",
    ],
)
def test_specific_artifact_q_zero_overrides_positive_wildcard(accept: str) -> None:
    client, backend = _client()

    response = client.get(
        "/api/research-runs/RUN-A/artifacts/ART-A/content",
        headers={"Accept": accept},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SCHEMA_INCOMPATIBLE"
    assert backend.calls == ["get_artifact_content"]
