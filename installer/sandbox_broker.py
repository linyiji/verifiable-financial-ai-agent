"""Private, narrow generated-capability broker; this process alone owns Docker authority."""

from __future__ import annotations

import argparse
import json
import os
import re
import socketserver
import stat
import struct
import subprocess
import threading
from pathlib import Path

from src.tooling.generated_sandbox import (
    DEFAULT_SANDBOX_IMAGE,
    DockerSandboxBackend,
    SandboxLimits,
    SandboxRequest,
    _receive_frame,
)

SOCKET_PATH = Path("/run/vfa-sandbox/broker.sock")
MAX_REQUEST_BYTES = 1_000_000
MAX_RESPONSE_BYTES = 1_100_000
MAX_CONCURRENCY = 2
_IDENTITY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_REQUEST_KEYS = {
    "schema",
    "request_id",
    "run_id",
    "task_id",
    "capability_id",
    "generation_attempt",
    "source",
    "test_source",
    "fixture",
    "entrypoint",
}


def _strict_json(raw: bytes):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate broker field")
            result[key] = value
        return result

    return json.loads(raw, object_pairs_hook=unique)


def _request(raw: bytes) -> tuple[str, SandboxRequest]:
    value = _strict_json(raw)
    if not isinstance(value, dict) or set(value) != _REQUEST_KEYS:
        raise ValueError("invalid broker request shape")
    if value["schema"] != "vfas.sandbox-broker.request.v1":
        raise ValueError("unsupported broker schema")
    for key in ("request_id", "run_id", "task_id", "capability_id"):
        if not isinstance(value[key], str) or not _IDENTITY.fullmatch(value[key]):
            raise ValueError("invalid broker identity")
    attempt = value["generation_attempt"]
    if type(attempt) is not int or not 1 <= attempt <= 16:
        raise ValueError("invalid generation attempt")
    if not isinstance(value["fixture"], dict):
        raise ValueError("fixture must be an object")
    return value["request_id"], SandboxRequest(
        source=value["source"],
        test_source=value["test_source"],
        fixture=value["fixture"],
        entrypoint=value["entrypoint"],
        run_id=value["run_id"],
        task_id=value["task_id"],
        capability_id=value["capability_id"],
        generation_attempt=attempt,
    )


def _response(request_id: str, result) -> bytes:
    value = {
        "schema": "vfas.sandbox-broker.response.v1",
        "request_id": request_id,
        "result": {
            "passed": result.passed,
            "exit_code": result.exit_code,
            "output": result.output,
            "duration_ms": result.duration_ms,
            "timed_out": result.timed_out,
            "stderr": result.stderr,
            "security": result.security,
        },
    }
    raw = json.dumps(value, separators=(",", ":"), sort_keys=True, allow_nan=False).encode()
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("broker response exceeds limit")
    return raw


class _Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    block_on_close = True

    def __init__(self, path: str):
        self.execution_slots = threading.BoundedSemaphore(MAX_CONCURRENCY)
        self.backend = DockerSandboxBackend(
            image=DEFAULT_SANDBOX_IMAGE,
            limits=SandboxLimits(),
            platform="linux/amd64",
        )
        super().__init__(path, _Handler)


class _Handler(socketserver.BaseRequestHandler):
    def handle(self):
        request_id = "SBR-invalid"
        try:
            raw = _receive_frame(self.request, MAX_REQUEST_BYTES)
            request_id, request = _request(raw)
            with self.server.execution_slots:
                result = self.server.backend.execute(request)
            response = _response(request_id, result)
        except Exception:
            response = json.dumps(
                {
                    "schema": "vfas.sandbox-broker.response.v1",
                    "request_id": request_id,
                    "result": {
                        "passed": False,
                        "exit_code": 126,
                        "output": {"ok": False, "error": {"code": "SANDBOX_BROKER_REJECTED"}},
                        "duration_ms": 0,
                        "timed_out": False,
                        "stderr": "",
                        "security": self.server.backend.security_profile,
                    },
                },
                separators=(",", ":"),
                sort_keys=True,
            ).encode()
        try:
            self.request.sendall(struct.pack("!I", len(response)) + response)
        except OSError:
            pass


def readiness() -> bool:
    try:
        mode = SOCKET_PATH.stat().st_mode
        if not stat.S_ISSOCK(mode):
            return False
        return _sandbox_image_is_amd64(timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return False


def _sandbox_image_is_amd64(*, timeout: float) -> bool:
    # Docker Desktop may report the manifest-list's cached host architecture from
    # `image inspect` even when its explicitly selected amd64 child is present.
    # Execute that exact child without network access to validate what will run.
    completed = subprocess.run(
        (
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--platform",
            "linux/amd64",
            "--pull",
            "never",
            DEFAULT_SANDBOX_IMAGE,
            "python",
            "-c",
            "import platform; print(platform.machine())",
        ),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        timeout=timeout,
        check=False,
    )
    return completed.returncode == 0 and completed.stdout.strip() in {b"x86_64", b"amd64"}


def serve() -> None:
    SOCKET_PATH.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
    SOCKET_PATH.unlink(missing_ok=True)
    try:
        available = _sandbox_image_is_amd64(timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        available = False
    if not available:
        raise SystemExit("SANDBOX_RUNTIME_NOT_READY")
    with _Server(str(SOCKET_PATH)) as server:
        os.chmod(SOCKET_PATH, 0o660)
        try:
            server.serve_forever(poll_interval=0.25)
        finally:
            SOCKET_PATH.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("serve", "health"))
    args = parser.parse_args()
    if args.command == "health":
        raise SystemExit(0 if readiness() else 1)
    serve()


if __name__ == "__main__":
    main()
