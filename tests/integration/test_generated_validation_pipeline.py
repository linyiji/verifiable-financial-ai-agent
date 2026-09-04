import subprocess
from decimal import Decimal

import pytest

from src.capabilities.generated.models import GeneratedCapabilityCandidate
from src.capabilities.generated.scoped_registry import ScopedCapabilityRegistry
from src.capabilities.generated.validation import (
    CapabilityValidationPlan,
    GeneratedCapabilityValidator,
    StaticCapabilityValidationPlanProvider,
)
from src.capabilities.registry import CapabilityRegistry
from src.domain.capability import CapabilityContext, ScopedCapabilityRegistration
from src.domain.enums import CapabilityLifecycle, CapabilityScope
from src.tooling.generated_sandbox import DEFAULT_SANDBOX_IMAGE, DockerSandboxBackend
from tests.unit.generated.test_validation import (
    ProgressSpy,
    candidate,
    financial_policy,
)


def _docker_image_available(image: str) -> bool:
    try:
        probe = subprocess.run(
            ("docker", "image", "inspect", image),
            capture_output=True,
            check=False,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return probe.returncode == 0


pytestmark = pytest.mark.skipif(
    not _docker_image_available(DEFAULT_SANDBOX_IMAGE),
    reason="real generated validation requires the pinned Python 3.11 Docker image",
)


@pytest.mark.asyncio
async def test_real_docker_validation_scoped_activation_and_calculation_lineage() -> None:
    generated: GeneratedCapabilityCandidate = candidate()
    validator = GeneratedCapabilityValidator(
        sandbox=DockerSandboxBackend(image=DEFAULT_SANDBOX_IMAGE),
        plans=StaticCapabilityValidationPlanProvider(
            CapabilityValidationPlan(
                primary_fixture={"gross_profit": "40", "revenue": "100"},
                edge_case_fixtures=(
                    {"gross_profit": "0", "revenue": "100"},
                    {"gross_profit": "125", "revenue": "100"},
                ),
                financial_policy=financial_policy(),
            )
        ),
    )
    progress = ProgressSpy()

    handoff = await validator.validate(generated, progress=progress)
    handoff.assert_ready_for_task_approval(generated)
    assert handoff.sandbox_execution.runtime_version.startswith("Python 3.11.")
    assert handoff.sandbox_execution.backend == "docker"
    assert handoff.sandbox_execution.passed

    registry = ScopedCapabilityRegistry(CapabilityRegistry())
    active = await registry.register(
        ScopedCapabilityRegistration(
            registration_id="REG-REAL-1",
            generated_capability_ref="GEN-REAL-1",
            capability_id="gross_margin",
            capability_version="1.0.0-generated",
            scope=CapabilityScope.TASK,
            run_id="RUN-REAL-1",
            task_id="TASK-REAL-1",
            approved_by="research_lead",
            lifecycle=CapabilityLifecycle.TASK_APPROVED,
        ),
        handoff.capability,
    )
    assert active.lifecycle is CapabilityLifecycle.ACTIVE_FOR_SCOPE
    resolved = await registry.lookup(
        "gross_margin",
        version="1.0.0-generated",
        run_id="RUN-REAL-1",
        task_id="TASK-REAL-1",
    )
    assert resolved is handoff.capability
    assert (
        await registry.lookup(
            "gross_margin",
            version="1.0.0-generated",
            run_id="RUN-REAL-1",
            task_id="TASK-OTHER",
        )
        is None
    )

    calculation = await resolved.execute(
        {"calculation_id": "CALC-REAL-1", "gross_profit": "40", "revenue": "100"},
        CapabilityContext(
            run_id="RUN-REAL-1",
            task_id="TASK-REAL-1",
            accepted_evidence_ids=["EVD-GROSS-REAL", "EVD-REVENUE-REAL"],
        ),
    )
    assert calculation.calculation_id == "CALC-REAL-1"
    assert calculation.output_value == Decimal("0.4")
    assert calculation.capability_id == "gross_margin"
    assert calculation.capability_version == "1.0.0-generated"
    assert calculation.formula_id == "gross_margin_v1"
    assert calculation.implementation_hash == generated.implementation_hash
    assert calculation.source_ref == "generated://BUILD-1/source.py"
    assert calculation.input_evidence_ids == ["EVD-GROSS-REAL", "EVD-REVENUE-REAL"]
    assert calculation.output_unit == "ratio"
    assert calculation.runtime_version.startswith("Python 3.11.")
