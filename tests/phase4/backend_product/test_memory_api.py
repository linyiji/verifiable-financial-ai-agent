from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.phase4_product.api import create_phase4_product_router, install_phase4_error_handlers
from src.phase4_product.memory_contracts import ResearchMemorySnapshot


def client():
    class Backend:
        calls = []

        async def get_memory(self, object_id):
            self.calls.append(("get", object_id))
            return ResearchMemorySnapshot(
                research_object_id=object_id,
                latest_released_run_id=None,
                latest_research_object_version=None,
                latest_research_view_version=None,
                object_version=None,
                current_view=None,
            )

        async def materialize_memory(self, object_id, run_id):
            self.calls.append(("materialize", object_id, run_id))
            return await self.get_memory(object_id)

    app = FastAPI()
    backend = Backend()
    app.state.phase4_product_backend = backend
    install_phase4_error_handlers(app)
    app.include_router(create_phase4_product_router())
    return TestClient(app), backend


def test_exact_object_family_route():
    c, b = client()
    h = {"X-Phase4-Contract-Version": "phase4-core/v1"}
    assert c.get("/api/objects/OBJ-A/memory", headers=h).json()["research_object_id"] == "OBJ-A"
    r = c.post("/api/objects/OBJ-A/memory/materialize", headers=h, json={"source_run_id": "RUN-A"})
    assert r.status_code == 200 and ("materialize", "OBJ-A", "RUN-A") in b.calls


def test_materialize_rejects_ticker_unknown_and_private_fields():
    c, b = client()
    h = {"X-Phase4-Contract-Version": "phase4-core/v1"}
    before = len(b.calls)
    for body in (
        {"ticker": "NVDA"},
        {"source_run_id": "RUN-A", "system_prompt": "private"},
        {"source_run_id": "/Users/secret"},
    ):
        assert (
            c.post("/api/objects/OBJ-A/memory/materialize", headers=h, json=body).status_code == 422
        )
    assert len(b.calls) == before
