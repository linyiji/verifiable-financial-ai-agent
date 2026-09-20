"""Production HTTP boundary with local synthetic runtime owners."""

import asyncio
from types import SimpleNamespace

import httpx
from fastapi import FastAPI

from src.phase4_product.api import create_phase4_product_router, install_phase4_error_handlers
from tests.external_failure_resume.runtime_fixture import exhaust, legal_fixture


async def test_explicit_resume_http(tmp_path):
    service, value, _ = await legal_fixture(tmp_path)
    await exhaust(service, value)
    backend = SimpleNamespace(
        service=service, get_run=service.repository.get_run_fresh, _wake=asyncio.Event()
    )
    app = FastAPI()
    app.state.phase4_product_backend = backend
    app.include_router(create_phase4_product_router())
    install_phase4_error_handlers(app)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://local"
    ) as c:
        url = f"/api/research-runs/{value.run.run_id}/external-resume"
        view = (await c.get(url)).json()
        command = dict(
            view["legal_actions"][0]["expectations"],
            authorize_resume=True,
            idempotency_key="explicit-one",
        )
        headers = {"Idempotency-Key": "explicit-one"}
        assert (await c.post(url, json={"text": "resume"}, headers=headers)).status_code == 422
        bad = dict(command, actor="spoofed")
        assert (await c.post(url, json=bad, headers=headers)).status_code == 403
        for field in (
            "expected_profile_digest",
            "expected_scenario_digest",
            "expected_resume_envelope_digest",
            "failed_node_id",
        ):
            wrong = dict(command, **{field: "wrong"})
            denial = await c.post(url, json=wrong, headers=headers)
            assert denial.status_code == 409, denial.text
        first = await c.post(url, json=command, headers=headers)
        assert first.status_code == 200, first.text
        second = await c.post(url, json=command, headers=headers)
        assert second.json()["receipt"] == first.json()["receipt"]
        assert second.json()["outcome"] == "IDEMPOTENT"
        assert second.json()["projection"]["state"] == "EXTERNAL_RESUME_PENDING"
        stale = dict(command, idempotency_key="stale")
        rejected = await c.post(url, json=stale, headers={"Idempotency-Key": "stale"})
        assert rejected.status_code == 409, rejected.text
        assert rejected.json()["outcome"] == "STALE_RESUME_REJECTED"
        current = (await c.get(url)).json()
        assert not current["legal_actions"]
        assert (
            len([a for a in current["audit"] if a["type"] == "external_failure.resume_authorized"])
            == 1
        )
