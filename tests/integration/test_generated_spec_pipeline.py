from __future__ import annotations

import subprocess

import pytest

from src.application.phase3_financial import FreeCashFlowMarginValidationPlanProvider
from src.capabilities.generated.artifacts import generated_text_sha256
from src.capabilities.generated.contract import GeneratedCapabilityRequestV1
from src.capabilities.generated.models import GeneratedCapabilityCandidate
from src.capabilities.generated.spec import GeneratedCapabilityCompilerV1, expected_spec
from src.capabilities.generated.validation import GeneratedCapabilityValidator
from src.tooling.generated_sandbox import DEFAULT_SANDBOX_IMAGE, DockerSandboxBackend
from tests.unit.generated.test_contract import build_request
from tests.unit.generated.test_validation import ProgressSpy


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
async def test_spec_compiler_output_passes_real_sandbox_and_financial_oracle() -> None:
    request = GeneratedCapabilityRequestV1.from_build_request(build_request())
    compiled = GeneratedCapabilityCompilerV1().compile(request, expected_spec(request))
    candidate = GeneratedCapabilityCandidate(
        build_id=build_request().build_id,
        output=compiled.output,
        implementation_hash=generated_text_sha256(compiled.output.source_code),
        provider="mimo",
        requested_model="mimo-v2.5",
        actual_model="mimo-v2.5",
        attempted_models=("mimo-v2.5",),
        input_tokens=1,
        output_tokens=1,
        latency_ms=1.0,
        spec_bytes=compiled.spec_bytes,
        spec_sha256=compiled.spec_sha256,
        compiler_id=compiled.compiler_id,
        compiler_version=compiled.compiler_version,
        compiler_runtime_policy=compiled.runtime_policy,
    )
    validator = GeneratedCapabilityValidator(
        sandbox=DockerSandboxBackend(image=DEFAULT_SANDBOX_IMAGE),
        plans=FreeCashFlowMarginValidationPlanProvider(),
    )

    handoff = await validator.validate(candidate, progress=ProgressSpy())

    assert handoff.validation.validation_result == "PASS"
    assert handoff.validation.financial_validation_passed is True
    assert handoff.sandbox_execution.passed is True
    assert handoff.sandbox_execution.runtime_version.startswith("Python 3.11.")
