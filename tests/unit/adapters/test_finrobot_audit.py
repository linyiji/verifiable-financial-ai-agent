from typing import Any

import pytest

from src.adapters.finrobot import (
    AUDIT_MATRIX,
    FINROBOT_PINNED_COMMIT,
    AuditCategory,
    FinRobotOperationNotApprovedError,
    FinRobotRevisionMismatchError,
    FinRobotSensitiveInputError,
    PinnedFinRobotAdapter,
    ReuseDecision,
)
from src.adapters.finrobot.audit import FinRobotAuditEntry
from src.domain.base import JsonObject


class StubBackend:
    def __init__(self, result: Any = "artifacts/report.pdf") -> None:
        self.result = result
        self.calls: list[tuple[FinRobotAuditEntry, JsonObject]] = []

    async def invoke(self, entry: FinRobotAuditEntry, inputs: JsonObject) -> Any:
        self.calls.append((entry, inputs))
        return self.result


def test_audit_matrix_covers_every_required_category() -> None:
    assert {entry.category for entry in AUDIT_MATRIX} == set(AuditCategory)
    assert {entry.decision for entry in AUDIT_MATRIX}.issubset(set(ReuseDecision))
    assert all(entry.python_311 for entry in AUDIT_MATRIX)
    assert all(entry.inputs and entry.outputs and entry.dependencies for entry in AUDIT_MATRIX)


def test_only_explicit_adapter_reuse_rows_have_executable_operation_ids() -> None:
    executable = [entry for entry in AUDIT_MATRIX if entry.operation_id is not None]

    assert {entry.operation_id for entry in executable} == {
        "charts.render",
        "report.render_pdf",
    }
    assert all(entry.decision is ReuseDecision.ADAPTER_REUSE for entry in executable)


def test_adapter_rejects_source_revision_other_than_exact_audit_pin() -> None:
    with pytest.raises(FinRobotRevisionMismatchError, match="audit pin"):
        PinnedFinRobotAdapter(backend=StubBackend(), source_revision="unreviewed-main")


@pytest.mark.asyncio
async def test_adapter_delegates_allowlisted_operation_with_detached_inputs() -> None:
    backend = StubBackend(result="data:image/png;base64,AAAA")
    adapter = PinnedFinRobotAdapter(
        backend=backend,
        source_revision=FINROBOT_PINNED_COMMIT,
    )
    inputs = {"ticker": "NVDA", "series": {"revenue": [1, 2]}}

    result = await adapter.execute("charts.render", inputs)
    inputs["series"]["revenue"].append(3)

    assert result == "data:image/png;base64,AAAA"
    assert backend.calls[0][0].source_module.endswith("chart_generator.py")
    assert backend.calls[0][1] == {"ticker": "NVDA", "series": {"revenue": [1, 2]}}


@pytest.mark.asyncio
async def test_adapter_rejects_unaudited_or_non_reusable_calculation() -> None:
    adapter = PinnedFinRobotAdapter(
        backend=StubBackend(),
        source_revision=FINROBOT_PINNED_COMMIT,
    )

    with pytest.raises(FinRobotOperationNotApprovedError, match="approved for MVP"):
        await adapter.calculate("valuation.calculate_dcf", {"free_cash_flow": 1})

    with pytest.raises(FinRobotOperationNotApprovedError, match="approved for MVP"):
        await adapter.calculate("charts.render", {"series": [1, 2]})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "inputs",
    [
        {"api_key": "redacted-placeholder"},
        {"nested": {"access_token": "redacted-placeholder"}},
        {"items": [{"password": "redacted-placeholder"}]},
    ],
)
async def test_render_boundary_rejects_credential_bearing_inputs(inputs: JsonObject) -> None:
    backend = StubBackend()
    adapter = PinnedFinRobotAdapter(
        backend=backend,
        source_revision=FINROBOT_PINNED_COMMIT,
    )

    with pytest.raises(FinRobotSensitiveInputError, match="credential-bearing"):
        await adapter.execute("charts.render", inputs)

    assert backend.calls == []


@pytest.mark.asyncio
async def test_report_renderer_requires_asset_path_string() -> None:
    adapter = PinnedFinRobotAdapter(
        backend=StubBackend(result={"path": "report.pdf"}),
        source_revision=FINROBOT_PINNED_COMMIT,
    )

    with pytest.raises(TypeError, match="asset path string"):
        await adapter.render_report({"research_object": "NVDA"})
