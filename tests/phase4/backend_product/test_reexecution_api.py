"""Public re-execution routes cannot smuggle new research intent into admission."""

import pytest

from tests.phase4.backend_product.test_api_negotiation_audit import _client


@pytest.mark.parametrize(
    "suffix,body",
    [
        (
            "reexecution-authorizations",
            {"research_object_id": "OBJ-A", "authorize_reexecution": True},
        ),
        ("reexecute", {"research_object_id": "OBJ-A", "authorization_id": "AUTH-A"}),
    ],
)
def test_closed_reexecution_request_and_required_key(suffix, body):
    client, backend = _client()
    path = "/api/research-runs/RUN-A/" + suffix
    headers = {"X-Phase4-Contract-Version": "phase4-core/v1", "Idempotency-Key": "test"}
    for injected in (
        "scheme_id",
        "goal",
        "base_run_id",
        "base_research_view_version",
        "reexecution_of_run_id",
    ):
        assert (
            client.post(path, headers=headers, json={**body, injected: "changed"}).status_code
            == 422
        )
    assert backend.calls == []
    response = client.post(path, headers={"X-Phase4-Contract-Version": "phase4-core/v1"}, json=body)
    assert response.status_code == 422
    assert backend.calls == []
    response = client.post(path, headers=headers, json=body)
    assert response.status_code == 409 and len(backend.calls) == 1
    assert "traceback" not in response.text.lower()
