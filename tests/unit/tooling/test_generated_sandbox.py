import json
import subprocess

import pytest

from src.tooling.generated_sandbox import (
    ALLOWED_IMPORTS,
    DockerSandboxBackend,
    GeneratedCodeASTPreflight,
    GeneratedCodeRejected,
    SandboxLimits,
    SandboxRequest,
    SandboxResult,
)

SAFE_SOURCE = """
from decimal import Decimal

def execute(inputs):
    revenue = Decimal(inputs["revenue"])
    cost = Decimal(inputs["cost"])
    return {"gross_margin": (revenue - cost) / revenue}
"""

SAFE_TESTS = """
from decimal import Decimal

def run_tests(execute, fixture):
    assert execute({"revenue": "100", "cost": "40"})["gross_margin"] == Decimal("0.6")
    assert execute(fixture)["gross_margin"] >= Decimal("0")
    return {"passed": 2}
"""


@pytest.mark.parametrize("module", sorted(ALLOWED_IMPORTS))
def test_ast_preflight_accepts_explicit_allowlist(module: str) -> None:
    result = GeneratedCodeASTPreflight().validate(f"import {module}\n")
    assert result.accepted
    assert result.violations == ()


@pytest.mark.parametrize(
    "source",
    [
        "import os",
        "import sys",
        "import subprocess",
        "import socket",
        "import requests",
        "import httpx",
        "import urllib.request",
        "from pathlib import Path",
        "import shutil",
        "import importlib",
        "import ctypes",
        "import multiprocessing",
        "import json",
    ],
)
def test_ast_preflight_rejects_forbidden_and_non_allowlisted_imports(source: str) -> None:
    result = GeneratedCodeASTPreflight().validate(source)
    assert not result.accepted
    assert "IMPORT_FORBIDDEN" in {item.code for item in result.violations}


@pytest.mark.parametrize(
    "source",
    [
        "eval('1 + 1')",
        "exec('value = 1')",
        "compile('1', '<x>', 'eval')",
        "__import__('math')",
        "open('/tmp/data')",
        "getattr(value, '__class__')",
        "value.__class__",
        "dangerous = open",
        "os.getenv('TOKEN')",
        "client.connect(('example.com', 443))",
    ],
)
def test_ast_preflight_rejects_dynamic_and_side_effect_operations(source: str) -> None:
    result = GeneratedCodeASTPreflight().validate(source)
    assert not result.accepted


def test_ast_preflight_reports_syntax_location() -> None:
    result = GeneratedCodeASTPreflight().validate("def broken(:\n")
    assert not result.accepted
    assert result.violations[0].code == "SYNTAX_ERROR"
    assert result.violations[0].line == 1


def test_ast_preflight_rejects_forbidden_name_reexported_by_allowed_module() -> None:
    result = GeneratedCodeASTPreflight().validate("from typing import sys as indirect\n")
    assert not result.accepted
    assert result.violations[0].code == "IMPORT_NAME_FORBIDDEN"


def test_docker_command_has_required_security_controls_and_no_mounts() -> None:
    backend = DockerSandboxBackend(
        image="python:3.11-slim",
        limits=SandboxLimits(memory="96m", cpus=0.25, pids=17, wall_timeout_seconds=3),
    )
    command = backend.build_command("vfas-generated-test")
    rendered = " ".join(command)

    assert "--network none" in rendered
    assert "--read-only" in command
    assert "--user 65534:65534" in rendered
    assert "--cap-drop ALL" in rendered
    assert "--security-opt no-new-privileges:true" in rendered
    assert "--memory 96m" in rendered
    assert "--memory-swap 96m" in rendered
    assert "--cpus 0.25" in rendered
    assert "--pids-limit 17" in rendered
    assert "PYTHONDONTWRITEBYTECODE=1" in command
    assert "--mount" not in command
    assert "--volume" not in command
    assert "-v" not in command
    assert SAFE_SOURCE not in rendered


def test_backend_sends_only_json_payload_over_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: dict[str, object] = {}

    def fake_run(command: tuple[str, ...], **kwargs: object) -> subprocess.CompletedProcess[str]:
        observed["command"] = command
        observed.update(kwargs)
        output = {
            "ok": True,
            "result": {"gross_margin": "0.6"},
            "tests": {"passed": 2},
        }
        return subprocess.CompletedProcess(command, 0, json.dumps(output), "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    backend = DockerSandboxBackend()
    request = SandboxRequest(
        source=SAFE_SOURCE,
        test_source=SAFE_TESTS,
        fixture={"cost": "40", "revenue": "100"},
    )
    result = backend.execute(request)

    assert isinstance(result, SandboxResult)
    assert result.passed
    payload = json.loads(str(observed["input"]))
    assert payload["source"] == SAFE_SOURCE
    assert payload["tests"] == SAFE_TESTS
    assert payload["fixture"] == {"cost": "40", "revenue": "100"}
    assert observed["text"] is True
    assert "shell" not in observed


def test_backend_rejects_code_before_starting_docker(monkeypatch: pytest.MonkeyPatch) -> None:
    def should_not_run(*args: object, **kwargs: object) -> None:
        raise AssertionError("Docker must not start after preflight rejection")

    monkeypatch.setattr(subprocess, "run", should_not_run)
    backend = DockerSandboxBackend()
    with pytest.raises(GeneratedCodeRejected):
        backend.execute(
            SandboxRequest(
                source="import os\ndef execute(inputs): return os.environ",
                test_source=SAFE_TESTS,
                fixture={"revenue": "100", "cost": "40"},
            )
        )


@pytest.mark.parametrize(
    "fixture",
    [
        {"api_key": "value"},
        {"apiKey": "value"},
        {"nested": {"access-token": "value"}},
        {"items": [{"private_key": "value"}]},
    ],
)
def test_backend_rejects_secret_like_fixture_fields(fixture: dict[str, object]) -> None:
    backend = DockerSandboxBackend()
    with pytest.raises(ValueError, match="secret-like"):
        backend.execute(SandboxRequest(source=SAFE_SOURCE, test_source=SAFE_TESTS, fixture=fixture))


def test_in_process_execution_is_not_a_production_backend() -> None:
    import src.tooling.generated_sandbox as sandbox_module

    assert not hasattr(sandbox_module, "InProcessSandboxBackend")
