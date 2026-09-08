from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from apps.api.main import create_app
from apps.api.routes import router


def test_parent_registers_one_frozen_product_route_inventory() -> None:
    observed = {
        (method, route.path)
        for route in router.routes
        if isinstance(route, APIRoute)
        for method in route.methods
    }
    assert observed == {
        ("POST", "/api/objects"),
        ("GET", "/api/objects"),
        ("GET", "/api/objects/{object_id}"),
        ("GET", "/api/objects/{object_id}/memory"),
        ("POST", "/api/objects/{object_id}/memory/materialize"),
        ("GET", "/api/objects/{object_id}/runs"),
        ("GET", "/api/objects/{object_id}/released-state"),
        ("GET", "/api/research-runs"),
        ("GET", "/api/research-drafts/{draft_id}"),
        ("POST", "/api/research-drafts/{draft_id}/lease-renewals"),
        ("POST", "/api/research-runs/prepare"),
        ("POST", "/api/research-runs"),
        ("POST", "/api/research-runs/{run_id}/reexecution-authorizations"),
        ("POST", "/api/research-runs/{run_id}/reexecute"),
        *(
            ("GET", "/api/research-runs/{run_id}" + suffix)
            for suffix in (
                "",
                "/projection",
                "/results",
                "/results-semantics",
                "/result",
                "/report-view",
                "/claims/{claim_id}",
                "/review-view",
                "/execution-view",
                "/trace/{claim_id}",
                "/artifacts",
                "/artifacts/{artifact_id}/content",
                "/recovery",
                "/events",
            )
        ),
    }
    assert ("GET", "/api/research-runs/{run_id}/events") in observed
    assert ("POST", "/api/research-runs") in observed
    assert ("POST", "/api/research-runs/{run_id}/execute") not in observed


def test_missing_product_backend_fails_closed_with_frozen_error() -> None:
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        response = client.get("/api/objects")

    assert response.status_code == 503
    assert response.headers["X-Phase4-Contract-Version"] == "phase4-core/v1"
    assert response.json()["schema_version"] == "phase4-error/v1"
    assert response.json()["error"]["code"] == "TRANSIENT_BACKEND_ERROR"
    assert response.json()["error"]["request_id"].startswith("REQ-")
