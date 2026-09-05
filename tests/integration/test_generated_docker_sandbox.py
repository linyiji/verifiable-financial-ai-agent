import os
import subprocess

import pytest

from src.tooling.generated_sandbox import (
    DEFAULT_SANDBOX_IMAGE,
    DockerSandboxBackend,
    SandboxLimits,
    SandboxRequest,
)
from tests.unit.tooling.test_generated_sandbox import SAFE_SOURCE, SAFE_TESTS

IMAGE = DEFAULT_SANDBOX_IMAGE


def _docker_image_available() -> bool:
    try:
        probe = subprocess.run(
            ("docker", "image", "inspect", IMAGE),
            capture_output=True,
            check=False,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return probe.returncode == 0


pytestmark = pytest.mark.skipif(
    not _docker_image_available(),
    reason=f"real Docker integration requires the pre-pulled {IMAGE} image",
)


def test_real_docker_executes_generated_capability_with_security_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FMP_API_KEY", "must-not-enter-sandbox")
    monkeypatch.setenv("FMP_API_KEY_1", "must-not-enter-sandbox")
    monkeypatch.setenv("TEAMOROUTER_API_KEY", "must-not-enter-sandbox")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "must-not-enter-sandbox")
    backend = DockerSandboxBackend(
        image=IMAGE,
        limits=SandboxLimits(memory="96m", cpus=0.5, pids=32, wall_timeout_seconds=10),
    )
    result = backend.execute(
        SandboxRequest(
            source=SAFE_SOURCE,
            test_source=SAFE_TESTS,
            fixture={"cost": "40", "revenue": "100"},
        )
    )

    assert result.passed, (result.output, result.stderr)
    assert result.exit_code == 0
    assert result.output["result"] == {"gross_margin": "0.6"}
    assert result.output["tests"] == {"passed": 2}
    probe = result.output["security_probe"]
    assert probe["non_root"] is True
    assert probe["root_write_blocked"] is True
    assert probe["external_connect_blocked"] is True
    assert probe["capabilities_effective"] == "0000000000000000"
    assert probe["no_new_privileges"] is True
    assert probe["memory_max"] == str(96 * 1024 * 1024)
    assert probe["cpu_max"] == "50000 100000"
    assert probe["pids_max"] == "32"
    assert "FMP_API_KEY" not in probe["environment_names"]
    assert "FMP_API_KEY_1" not in probe["environment_names"]
    assert "TEAMOROUTER_API_KEY" not in probe["environment_names"]
    assert "LANGFUSE_SECRET_KEY" not in probe["environment_names"]
    assert result.security["host_mounts"] == []


def test_real_docker_wall_timeout_is_enforced_and_container_is_removed() -> None:
    backend = DockerSandboxBackend(
        image=IMAGE,
        limits=SandboxLimits(wall_timeout_seconds=0.5),
    )
    source = """
def execute(inputs):
    while True:
        pass
"""
    result = backend.execute(
        SandboxRequest(source=source, test_source=SAFE_TESTS, fixture={"value": "1"})
    )

    assert not result.passed
    assert result.timed_out
    assert result.exit_code == 124
    assert result.output["error"]["code"] == "WALL_TIMEOUT"

    listed = subprocess.run(
        ("docker", "ps", "--all", "--filter", "name=vfas-generated-", "--format", "{{.Names}}"),
        capture_output=True,
        text=True,
        check=True,
        timeout=5,
    )
    assert listed.stdout.strip() == ""


def test_real_docker_does_not_receive_host_environment() -> None:
    secret_name = "VFAS_SANDBOX_TEST_SECRET"
    old_value = os.environ.get(secret_name)
    os.environ[secret_name] = "must-not-enter-sandbox"
    try:
        backend = DockerSandboxBackend(image=IMAGE)
        result = backend.execute(
            SandboxRequest(
                source=SAFE_SOURCE,
                test_source=SAFE_TESTS,
                fixture={"cost": "40", "revenue": "100"},
            )
        )
    finally:
        if old_value is None:
            os.environ.pop(secret_name, None)
        else:
            os.environ[secret_name] = old_value

    assert result.passed
    assert secret_name not in result.output["security_probe"]["environment_names"]
