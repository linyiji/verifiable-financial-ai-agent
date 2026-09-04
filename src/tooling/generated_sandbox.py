"""Preflight validation and isolated execution for generated Python capabilities.

The AST validator is deliberately conservative, but it is only a fast rejection
layer.  ``DockerSandboxBackend`` is the security boundary used for generated
code: no host paths are mounted and the complete workload arrives on stdin as a
bounded JSON document.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from src.domain.base import JsonObject

ALLOWED_IMPORTS = frozenset(
    {"dataclasses", "datetime", "decimal", "math", "statistics", "typing"}
)
FORBIDDEN_IMPORTS = frozenset(
    {
        "ctypes",
        "httpx",
        "importlib",
        "multiprocessing",
        "os",
        "pathlib",
        "requests",
        "shutil",
        "socket",
        "subprocess",
        "sys",
        "urllib",
    }
)
FORBIDDEN_CALLS = frozenset(
    {
        "__import__",
        "breakpoint",
        "compile",
        "delattr",
        "dir",
        "eval",
        "exec",
        "getattr",
        "globals",
        "help",
        "input",
        "locals",
        "open",
        "setattr",
        "vars",
    }
)
FORBIDDEN_ATTRIBUTES = frozenset(
    {
        "environ",
        "getenv",
        "putenv",
        "spawn",
        "system",
        "popen",
        "fork",
        "connect",
        "bind",
        "listen",
        "urlopen",
        "request",
        "read_text",
        "read_bytes",
        "write_text",
        "write_bytes",
        "unlink",
        "rmdir",
        "mkdir",
    }
)
_MEMORY_LIMIT = re.compile(r"^[1-9][0-9]*(?:[bkmg])?$", re.IGNORECASE)
_IMAGE_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/:@-]{0,254}$")
DEFAULT_SANDBOX_IMAGE = (
    "python:3.11-slim@sha256:9534e5a8e315485d4061ed659af0fd78a284c015f9b73661b41d6bab25604534"
)


@dataclass(frozen=True, slots=True)
class PreflightViolation:
    code: str
    message: str
    line: int | None = None
    column: int | None = None

    def as_dict(self) -> JsonObject:
        return {
            "code": self.code,
            "message": self.message,
            "line": self.line,
            "column": self.column,
        }


@dataclass(frozen=True, slots=True)
class ASTPreflightResult:
    accepted: bool
    violations: tuple[PreflightViolation, ...] = ()


class GeneratedCodeRejected(ValueError):
    def __init__(self, result: ASTPreflightResult):
        self.result = result
        detail = "; ".join(item.message for item in result.violations)
        super().__init__(detail or "generated code rejected by AST preflight")


class _GeneratedCodeVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: list[PreflightViolation] = []

    def _reject(self, node: ast.AST, code: str, message: str) -> None:
        self.violations.append(
            PreflightViolation(
                code=code,
                message=message,
                line=getattr(node, "lineno", None),
                column=getattr(node, "col_offset", None),
            )
        )

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        for alias in node.names:
            root = alias.name.split(".", maxsplit=1)[0]
            if alias.name not in ALLOWED_IMPORTS:
                detail = "explicitly forbidden" if root in FORBIDDEN_IMPORTS else "not allowed"
                self._reject(
                    node,
                    "IMPORT_FORBIDDEN",
                    f"import {alias.name!r} is {detail}",
                )
            if alias.asname and alias.asname in FORBIDDEN_IMPORTS:
                self._reject(
                    node,
                    "DANGEROUS_ALIAS",
                    f"import alias {alias.asname!r} is reserved",
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        module = node.module or ""
        root = module.split(".", maxsplit=1)[0]
        if node.level or module not in ALLOWED_IMPORTS:
            detail = "explicitly forbidden" if root in FORBIDDEN_IMPORTS else "not allowed"
            self._reject(
                node,
                "IMPORT_FORBIDDEN",
                f"import from {module or '<relative>'!r} is {detail}",
            )
        for alias in node.names:
            if alias.name == "*":
                self._reject(node, "WILDCARD_IMPORT", "wildcard imports are not allowed")
            if alias.name in FORBIDDEN_IMPORTS or alias.name.startswith("__"):
                self._reject(
                    node,
                    "IMPORT_NAME_FORBIDDEN",
                    f"imported name {alias.name!r} is not allowed",
                )
            if alias.asname and alias.asname in FORBIDDEN_IMPORTS:
                self._reject(
                    node,
                    "DANGEROUS_ALIAS",
                    f"import alias {alias.asname!r} is reserved",
                )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        name: str | None = None
        if isinstance(node.func, ast.Name):
            name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            name = node.func.attr
        if name in FORBIDDEN_CALLS:
            self._reject(node, "CALL_FORBIDDEN", f"call to {name!r} is not allowed")
        elif name in FORBIDDEN_ATTRIBUTES:
            self._reject(node, "SIDE_EFFECT_FORBIDDEN", f"operation {name!r} is not allowed")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:  # noqa: N802
        if node.attr.startswith("__"):
            self._reject(node, "DUNDER_ACCESS", "dunder attribute access is not allowed")
        elif node.attr in FORBIDDEN_ATTRIBUTES:
            self._reject(
                node,
                "SIDE_EFFECT_FORBIDDEN",
                f"attribute {node.attr!r} is not allowed",
            )
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:  # noqa: N802
        if (
            node.id in FORBIDDEN_IMPORTS
            or node.id in FORBIDDEN_CALLS
            or node.id == "__builtins__"
        ):
            self._reject(node, "NAME_FORBIDDEN", f"name {node.id!r} is not allowed")


class GeneratedCodeASTPreflight:
    """Default-deny AST policy for generated source and generated tests."""

    def validate(self, source: str, *, filename: str = "<generated>") -> ASTPreflightResult:
        try:
            tree = ast.parse(source, filename=filename, mode="exec")
        except (SyntaxError, ValueError, TypeError) as exc:
            return ASTPreflightResult(
                accepted=False,
                violations=(
                    PreflightViolation(
                        code="SYNTAX_ERROR",
                        message=str(exc),
                        line=getattr(exc, "lineno", None),
                        column=getattr(exc, "offset", None),
                    ),
                ),
            )

        visitor = _GeneratedCodeVisitor()
        visitor.visit(tree)
        violations = tuple(visitor.violations)
        return ASTPreflightResult(accepted=not violations, violations=violations)

    def validate_or_raise(self, source: str, *, filename: str = "<generated>") -> None:
        result = self.validate(source, filename=filename)
        if not result.accepted:
            raise GeneratedCodeRejected(result)


@dataclass(frozen=True, slots=True)
class SandboxLimits:
    memory: str = "128m"
    cpus: float = 0.5
    pids: int = 32
    wall_timeout_seconds: float = 10.0
    max_payload_bytes: int = 1_000_000
    max_output_bytes: int = 1_000_000

    def __post_init__(self) -> None:
        if not _MEMORY_LIMIT.fullmatch(self.memory):
            raise ValueError("memory must be a Docker byte value such as '128m'")
        if not 0 < self.cpus <= 8:
            raise ValueError("cpus must be greater than zero and at most 8")
        if not 1 <= self.pids <= 512:
            raise ValueError("pids must be between 1 and 512")
        if not 0 < self.wall_timeout_seconds <= 300:
            raise ValueError("wall timeout must be greater than zero and at most 300 seconds")
        if self.max_payload_bytes < 1 or self.max_output_bytes < 1:
            raise ValueError("payload and output limits must be positive")


@dataclass(frozen=True, slots=True)
class SandboxRequest:
    source: str
    test_source: str
    fixture: JsonObject
    entrypoint: str = "execute"

    def __post_init__(self) -> None:
        if not self.source.strip():
            raise ValueError("generated source must not be empty")
        if not self.test_source.strip():
            raise ValueError("generated tests must not be empty")
        if not self.entrypoint.isidentifier() or self.entrypoint.startswith("_"):
            raise ValueError("entrypoint must be a public Python identifier")


@dataclass(frozen=True, slots=True)
class SandboxResult:
    passed: bool
    exit_code: int
    output: JsonObject
    duration_ms: int
    timed_out: bool = False
    stderr: str = ""
    security: JsonObject = field(default_factory=dict)


@runtime_checkable
class SandboxBackend(Protocol):
    """Execution boundary for untrusted generated code."""

    def execute(self, request: SandboxRequest) -> SandboxResult: ...


class DockerSandboxBackend:
    """Run generated Python in a constrained, non-root Docker container."""

    def __init__(
        self,
        *,
        image: str = DEFAULT_SANDBOX_IMAGE,
        docker_binary: str = "docker",
        limits: SandboxLimits | None = None,
        preflight: GeneratedCodeASTPreflight | None = None,
    ) -> None:
        if not _IMAGE_REFERENCE.fullmatch(image):
            raise ValueError("invalid Docker image reference")
        self.image = image
        self.docker_binary = docker_binary
        self.limits = limits or SandboxLimits()
        self.preflight = preflight or GeneratedCodeASTPreflight()

    def build_command(self, container_name: str) -> tuple[str, ...]:
        """Return the auditable argv; payload is intentionally absent from it."""
        memory = self.limits.memory
        return (
            self.docker_binary,
            "run",
            "--rm",
            "--interactive",
            "--pull",
            "never",
            "--name",
            container_name,
            "--network",
            "none",
            "--read-only",
            "--user",
            "65534:65534",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges:true",
            "--memory",
            memory,
            "--memory-swap",
            memory,
            "--cpus",
            str(self.limits.cpus),
            "--pids-limit",
            str(self.limits.pids),
            "--ulimit",
            "nofile=64:64",
            "--ipc",
            "none",
            "--env",
            "PYTHONDONTWRITEBYTECODE=1",
            "--env",
            "PYTHONHASHSEED=0",
            "--entrypoint",
            "python",
            self.image,
            "-I",
            "-B",
            "-c",
            _CONTAINER_RUNNER,
        )

    def execute(self, request: SandboxRequest) -> SandboxResult:
        self.preflight.validate_or_raise(request.source, filename="generated_capability.py")
        self.preflight.validate_or_raise(request.test_source, filename="test_generated.py")
        sensitive_paths = _find_sensitive_fixture_paths(request.fixture)
        if sensitive_paths:
            joined = ", ".join(sensitive_paths)
            raise ValueError(f"sandbox fixture contains secret-like fields: {joined}")

        try:
            payload = json.dumps(
                {
                    "source": request.source,
                    "tests": request.test_source,
                    "fixture": request.fixture,
                    "entrypoint": request.entrypoint,
                    "allowed_imports": sorted(ALLOWED_IMPORTS),
                },
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
                allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("sandbox fixture must be canonical JSON") from exc
        payload_size = len(payload.encode("utf-8"))
        if payload_size > self.limits.max_payload_bytes:
            raise ValueError(
                f"sandbox payload is {payload_size} bytes; limit is "
                f"{self.limits.max_payload_bytes}"
            )

        container_name = f"vfas-generated-{uuid.uuid4().hex}"
        command = self.build_command(container_name)
        started = time.monotonic()
        try:
            completed = subprocess.run(  # noqa: S603 - fixed argv, shell is never used
                command,
                input=payload,
                capture_output=True,
                text=True,
                check=False,
                timeout=self.limits.wall_timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            self._force_remove(container_name)
            return SandboxResult(
                passed=False,
                exit_code=124,
                output={"ok": False, "error": {"code": "WALL_TIMEOUT"}},
                duration_ms=_elapsed_ms(started),
                timed_out=True,
                security=self.security_profile,
            )
        except FileNotFoundError:
            return SandboxResult(
                passed=False,
                exit_code=127,
                output={"ok": False, "error": {"code": "DOCKER_NOT_FOUND"}},
                duration_ms=_elapsed_ms(started),
                security=self.security_profile,
            )

        stdout = completed.stdout
        stderr = completed.stderr
        if len(stdout.encode("utf-8")) > self.limits.max_output_bytes:
            return SandboxResult(
                passed=False,
                exit_code=completed.returncode,
                output={"ok": False, "error": {"code": "OUTPUT_LIMIT_EXCEEDED"}},
                duration_ms=_elapsed_ms(started),
                stderr=_bounded(stderr, self.limits.max_output_bytes),
                security=self.security_profile,
            )
        try:
            decoded = json.loads(stdout)
            if not isinstance(decoded, dict):
                raise TypeError("sandbox output is not a JSON object")
        except (json.JSONDecodeError, TypeError) as exc:
            decoded = {
                "ok": False,
                "error": {
                    "code": "INVALID_SANDBOX_OUTPUT",
                    "detail": str(exc),
                },
            }
        passed = completed.returncode == 0 and decoded.get("ok") is True
        return SandboxResult(
            passed=passed,
            exit_code=completed.returncode,
            output=decoded,
            duration_ms=_elapsed_ms(started),
            stderr=_bounded(stderr, self.limits.max_output_bytes),
            security=self.security_profile,
        )

    @property
    def security_profile(self) -> JsonObject:
        return {
            "network": "none",
            "read_only_root": True,
            "user": "65534:65534",
            "cap_drop": "ALL",
            "no_new_privileges": True,
            "memory": self.limits.memory,
            "cpus": self.limits.cpus,
            "pids": self.limits.pids,
            "wall_timeout_seconds": self.limits.wall_timeout_seconds,
            "host_mounts": [],
            "python_dont_write_bytecode": True,
        }

    def _force_remove(self, container_name: str) -> None:
        try:
            subprocess.run(  # noqa: S603 - exact name generated by this backend
                (self.docker_binary, "rm", "--force", container_name),
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass


def _find_sensitive_fixture_paths(value: Any, path: str = "fixture") -> list[str]:
    findings: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if _looks_sensitive(str(key)):
                findings.append(child_path)
            findings.extend(_find_sensitive_fixture_paths(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(_find_sensitive_fixture_paths(child, f"{path}[{index}]"))
    return findings


def _elapsed_ms(started: float) -> int:
    return max(0, round((time.monotonic() - started) * 1000))


def _bounded(value: str, limit: int) -> str:
    encoded = value.encode("utf-8")
    if len(encoded) <= limit:
        return value
    return encoded[:limit].decode("utf-8", errors="replace")


def _looks_sensitive(key: str) -> bool:
    compact = re.sub(r"[^a-z0-9]", "", key.lower())
    return any(
        marker in compact
        for marker in (
            "accesskey",
            "apikey",
            "authorization",
            "cookie",
            "credential",
            "password",
            "privatekey",
            "secret",
            "token",
        )
    )


_CONTAINER_RUNNER = r'''
import builtins
import contextlib
import dataclasses
import datetime
import decimal
import io
import json
import os
import socket
import sys


def normalize(value):
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return normalize(dataclasses.asdict(value))
    if isinstance(value, decimal.Decimal):
        return str(value)
    if isinstance(value, (datetime.date, datetime.datetime, datetime.time)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): normalize(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        return [normalize(item) for item in value]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise TypeError("output contains unsupported type: " + type(value).__name__)


def security_probe():
    root_blocked = False
    try:
        with open("/vfas-root-write-probe", "w", encoding="utf-8") as handle:
            handle.write("probe")
    except OSError:
        root_blocked = True

    interfaces = []
    try:
        interfaces = [name for _, name in socket.if_nameindex()]
    except OSError:
        pass
    external_connect_blocked = True
    probe_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe_socket.settimeout(0.25)
    try:
        external_connect_blocked = probe_socket.connect_ex(("1.1.1.1", 53)) != 0
    except OSError:
        external_connect_blocked = True
    finally:
        probe_socket.close()

    def read_control(path):
        try:
            with open(path, encoding="utf-8") as handle:
                return handle.read().strip()
        except OSError:
            return None

    process_status = read_control("/proc/self/status") or ""
    status_fields = {}
    for line in process_status.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            status_fields[key] = value.strip()
    return {
        "uid": os.getuid(),
        "non_root": os.getuid() != 0,
        "root_write_blocked": root_blocked,
        "network_interfaces": interfaces,
        "external_connect_blocked": external_connect_blocked,
        "capabilities_effective": status_fields.get("CapEff"),
        "no_new_privileges": status_fields.get("NoNewPrivs") == "1",
        "memory_max": read_control("/sys/fs/cgroup/memory.max"),
        "cpu_max": read_control("/sys/fs/cgroup/cpu.max"),
        "pids_max": read_control("/sys/fs/cgroup/pids.max"),
        # Names, never values, let acceptance verify that selected host secrets
        # were not forwarded. Base-image metadata such as its public GPG_KEY is
        # not a host credential and therefore is not treated as an exposure.
        "environment_names": sorted(os.environ),
    }


def main():
    payload = json.load(sys.stdin)
    allowed = frozenset(payload["allowed_imports"])
    real_import = builtins.__import__

    def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
        if level or name not in allowed:
            raise ImportError("import is not allowed: " + name)
        return real_import(name, globals, locals, fromlist, level)

    safe_builtins = {
        "__build_class__": builtins.__build_class__,
        "__import__": safe_import,
        "abs": abs,
        "all": all,
        "any": any,
        "AssertionError": AssertionError,
        "bool": bool,
        "dict": dict,
        "enumerate": enumerate,
        "Exception": Exception,
        "float": float,
        "int": int,
        "isinstance": isinstance,
        "len": len,
        "list": list,
        "max": max,
        "min": min,
        "object": object,
        "range": range,
        "round": round,
        "set": set,
        "sorted": sorted,
        "str": str,
        "sum": sum,
        "tuple": tuple,
        "TypeError": TypeError,
        "ValueError": ValueError,
        "zip": zip,
    }
    namespace = {"__builtins__": safe_builtins, "__name__": "__main__"}
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
        exec(compile(payload["source"], "generated_capability.py", "exec"), namespace)
        entrypoint = namespace.get(payload["entrypoint"])
        if not callable(entrypoint):
            raise TypeError("generated capability entrypoint is missing or not callable")
        exec(compile(payload["tests"], "test_generated.py", "exec"), namespace)
        test_runner = namespace.get("run_tests")
        if not callable(test_runner):
            raise TypeError("generated tests must define run_tests(execute, fixture)")
        test_result = test_runner(entrypoint, payload["fixture"])
        if test_result is False:
            raise AssertionError("generated test runner returned false")
        result = entrypoint(payload["fixture"])
    return {
        "ok": True,
        "result": normalize(result),
        "tests": normalize(test_result),
        "captured_output": captured.getvalue()[-4096:],
        "runtime": {"implementation": "CPython", "python": sys.version.split()[0]},
        "security_probe": security_probe(),
    }


try:
    print(json.dumps(main(), sort_keys=True, separators=(",", ":"), allow_nan=False))
except BaseException as exc:
    print(json.dumps({
        "ok": False,
        "error": {
            "code": "SANDBOX_EXECUTION_FAILED",
            "type": type(exc).__name__,
            "detail": str(exc),
        },
        "runtime": {"implementation": "CPython", "python": sys.version.split()[0]},
        "security_probe": security_probe(),
    }, sort_keys=True, separators=(",", ":")))
    raise SystemExit(1)
'''
