from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from src.adapters.finrobot.technical import (
    MACD12269Capability,
    RSI14Capability,
    SMA50Capability,
    SMA200Capability,
    VolumeRatio20Capability,
)
from src.capabilities.registry import CapabilityRegistry
from src.domain.calculation import CalculationRecord
from src.domain.capability import CapabilityContext
from src.domain.enums import CapabilityBackend, EvidenceCategory, EvidenceStatus
from src.domain.evidence import EvidenceRecord
from src.tooling.native import NativeToolBackend
from src.tooling.runtime import ToolRuntime


def accepted_nvda_history() -> list[EvidenceRecord]:
    records: list[EvidenceRecord] = []
    retrieved = datetime(2026, 9, 4, tzinfo=UTC)
    for index in range(220):
        as_of = date(2026, 1, 1) + timedelta(days=index)
        common = {
            "run_id": "RUN-NVDA-P3",
            "object_id": "OBJ-NVDA",
            "provider": "fmp",
            "source_locator": "/stable/historical-price-eod/full",
            "source_endpoint": "/stable/historical-price-eod/full",
            "evidence_purpose": "historical_market_context",
            "evidence_category": EvidenceCategory.MARKET,
            "retrieved_at": retrieved,
            "period": "DAILY",
            "as_of": as_of,
            "raw_artifact_ref": "artifact://nvda-historical",
            "snapshot_hash": "sha256:nvda-historical",
            "status": EvidenceStatus.ACCEPTED,
        }
        records.append(
            EvidenceRecord(
                evidence_id=f"EVD-NVDA-CLOSE-{index:03d}",
                normalized_field="close",
                normalized_value=str(100 + index / 10),
                unit="CURRENCY",
                currency="USD",
                **common,
            )
        )
        records.append(
            EvidenceRecord(
                evidence_id=f"EVD-NVDA-VOLUME-{index:03d}",
                normalized_field="volume",
                normalized_value=str(1_000_000 + index * 1_000),
                unit="COUNT",
                **common,
            )
        )
    return records


@pytest.mark.asyncio
async def test_real_runtime_path_calls_all_owned_finrobot_indicator_capabilities() -> None:
    registry = CapabilityRegistry()
    capabilities = (
        SMA50Capability(),
        SMA200Capability(),
        RSI14Capability(),
        MACD12269Capability(),
        VolumeRatio20Capability(),
    )
    for capability in capabilities:
        registry.register(capability)
    runtime = ToolRuntime(
        registry=registry,
        backends={CapabilityBackend.NATIVE: NativeToolBackend(registry)},
    )
    evidence = accepted_nvda_history()
    capability_context = CapabilityContext(
        run_id="RUN-NVDA-P3",
        task_id="TASK-NVDA-TECHNICAL",
        accepted_evidence_ids=[record.evidence_id for record in evidence],
    )

    runtime_outputs: list[CalculationRecord] = []
    for index, capability in enumerate(capabilities):
        output = await runtime.execute(
            capability.definition.capability_id,
            {"history": evidence, "calculation_id": f"CALC-NVDA-TECH-{index}"},
            capability_context,
            version=capability.definition.version,
        )
        runtime_outputs.extend(output if isinstance(output, tuple) else (output,))

    assert len(runtime_outputs) == 7
    assert {record.capability_id for record in runtime_outputs} == {
        "technical_sma_50",
        "technical_sma_200",
        "technical_rsi_14",
        "technical_macd_12_26_9",
        "technical_volume_ratio_20",
    }
    assert all(record.run_id == capability_context.run_id for record in runtime_outputs)
    assert all(record.task_id == capability_context.task_id for record in runtime_outputs)
    assert all(record.input_evidence_ids for record in runtime_outputs)
