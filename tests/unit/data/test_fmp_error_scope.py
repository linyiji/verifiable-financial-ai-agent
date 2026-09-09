"""C-01 regression: mock HTTP only, no subscription bypass or global 403 poisoning."""

import httpx
import pytest
from pydantic import SecretStr

from src.adapters.fmp.models import FMPAccessStatus, FMPEndpoint
from src.adapters.fmp.provider import HttpxFMPTransport
from src.infrastructure.config.settings import FMPSettings


def transport(handler):
    return HttpxFMPTransport(
        FMPSettings(
            api_keys=(SecretStr("fake-first"), SecretStr("fake-second")),
            base_url="https://example.invalid",
        ),
        http_transport=httpx.MockTransport(handler),
    )


async def request(client, endpoint):
    return await client.request(endpoint=endpoint, path=f"/stable/{endpoint.value}", params={})


@pytest.mark.parametrize(
    "status,payload",
    [
        (403, {"error": "subscription unavailable"}),
        (403, {"error": "credential rejected"}),
        (402, {}),
        (200, {"Error Message": "premium subscription required"}),
    ],
)
async def test_endpoint_denial_never_poison_same_key_quote_or_financials(status, payload):
    calls = []

    def handler(req):
        calls.append((req.url.path, req.url.params["apikey"]))
        return (
            httpx.Response(status, json=payload)
            if req.url.path.endswith("transcript")
            else httpx.Response(200, json=[{"symbol": "NVDA"}])
        )

    client = transport(handler)
    denied = await request(client, FMPEndpoint.TRANSCRIPT)
    assert denied.status is FMPAccessStatus.ENTITLEMENT_DENIED
    assert denied.error_scope == "ENDPOINT"
    assert client.invalid_key_count == 0
    assert client.safe_pool_status()["rotation_occurred"] is False
    for endpoint in (FMPEndpoint.QUOTE, FMPEndpoint.INCOME, FMPEndpoint.CASHFLOW):
        assert (await request(client, endpoint)).status is FMPAccessStatus.AVAILABLE
    assert all(key == "fake-first" for _, key in calls)
    assert len(calls) == 4
    assert client.safe_health_status()["endpoint_denials"] == [
        {"slot": 0, "endpoint": "transcript", "status": "ENTITLEMENT_DENIED"}
    ]
    assert client.safe_health_status()["provider_health"] == "NOT_INFERRED"


async def test_401_invalidates_credential_across_endpoints_and_uses_finite_authorized_pool():
    calls = []

    def handler(req):
        key = req.url.params["apikey"]
        calls.append(key)
        return httpx.Response(401 if key == "fake-first" else 200, json=[{"symbol": "NVDA"}])

    client = transport(handler)
    assert (await request(client, FMPEndpoint.TRANSCRIPT)).status is FMPAccessStatus.AVAILABLE
    assert (await request(client, FMPEndpoint.QUOTE)).status is FMPAccessStatus.AVAILABLE
    assert calls == ["fake-first", "fake-second", "fake-second"]
    assert client.invalid_key_count == 1


@pytest.mark.parametrize("status", [429, 200])
async def test_rate_limited_slots_stay_unavailable_without_reset_or_infinite_retry(status):
    calls = []

    def handler(req):
        calls.append(req.url.params["apikey"])
        return httpx.Response(status, json={"error": "rate limit"})

    client = transport(handler)
    for endpoint in (FMPEndpoint.QUOTE, FMPEndpoint.INCOME):
        result = await request(client, endpoint)
        assert result.status is FMPAccessStatus.RATE_LIMITED
    assert calls == ["fake-first", "fake-second"]
    assert client.pool_exhausted
    assert client.safe_health_status()["credential_rate_limited_slots"] == [0, 1]


async def test_payload_account_limit_precedes_credential_rotation():
    calls = []

    def handler(req):
        calls.append(req.url.path)
        return httpx.Response(200, json={"scope": "account", "error": "rate limit"})

    client = transport(handler)
    for endpoint in (FMPEndpoint.QUOTE, FMPEndpoint.INCOME):
        result = await request(client, endpoint)
        assert result.status is FMPAccessStatus.RATE_LIMITED
        assert result.error_scope == "ACCOUNT"
    assert len(calls) == 1
    assert client.safe_pool_status()["rotation_occurred"] is False


@pytest.mark.parametrize("status", [403, 429])
async def test_explicit_account_restriction_never_rotates_or_sends_another_endpoint(status):
    calls = []

    def handler(req):
        calls.append(req.url.params["apikey"])
        return httpx.Response(status, json={"error": {"scope": "account"}})

    client = transport(handler)
    first = await request(client, FMPEndpoint.TRANSCRIPT)
    second = await request(client, FMPEndpoint.QUOTE)
    assert first.error_scope == second.error_scope == "ACCOUNT"
    assert second.status is first.status
    assert second.http_status == status
    assert calls == ["fake-first"]
    assert client.safe_pool_status()["rotation_occurred"] is False


async def test_mixed_exhaustion_keeps_actual_last_rate_limit_not_fabricated_auth_failure():
    def handler(req):
        return httpx.Response(401 if req.url.params["apikey"] == "fake-first" else 429, json={})

    client = transport(handler)
    for endpoint in (FMPEndpoint.QUOTE, FMPEndpoint.INCOME):
        result = await request(client, endpoint)
        assert result.status is FMPAccessStatus.RATE_LIMITED
        assert result.http_status == 429
        assert result.error_code == "FMP_KEY_POOL_EXHAUSTED"
    assert client.safe_pool_status()["attempt_count"] == 2


async def test_endpoint_or_account_health_is_transport_scoped_not_shared_provider_outage():
    denied = transport(lambda _: httpx.Response(403, json={"scope": "account"}))
    healthy = transport(lambda _: httpx.Response(200, json=[{"symbol": "NVDA"}]))
    await request(denied, FMPEndpoint.TRANSCRIPT)
    assert (await request(healthy, FMPEndpoint.TRANSCRIPT)).status is FMPAccessStatus.AVAILABLE
    assert healthy.safe_health_status()["account_restricted"] is False
