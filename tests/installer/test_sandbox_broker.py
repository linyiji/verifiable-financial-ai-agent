"""Offline contract tests for the private generated-capability broker."""

import json
import os
import struct
import threading
from pathlib import Path
from uuid import uuid4

import pytest

from installer import sandbox_broker
from src.tooling.generated_sandbox import (
    BrokerSandboxBackend,
    SandboxRequest,
    SandboxResult,
)


def request_payload(**overrides):
    value = {
        "schema": "vfas.sandbox-broker.request.v1",
        "request_id": "SBR-test",
        "run_id": "RUN-test",
        "task_id": "TASK-test",
        "capability_id": "generated.fcf",
        "generation_attempt": 1,
        "source": "def execute(inputs):\n    return inputs",
        "test_source": "def run_tests(fn, inputs):\n    return {'passed': 1}",
        "fixture": {"value": "1"},
        "entrypoint": "execute",
    }
    value.update(overrides)
    return json.dumps(value, separators=(",", ":")).encode()


@pytest.mark.parametrize(
    "change",
    [
        {"schema": "other"},
        {"image": "attacker/image"},
        {"generation_attempt": True},
        {"run_id": "../escape"},
        {"fixture": ["not-object"]},
    ],
)
def test_broker_rejects_unowned_or_malformed_fields(change):
    with pytest.raises(ValueError):
        sandbox_broker._request(request_payload(**change))


def test_broker_rejects_duplicate_fields():
    raw = request_payload()[:-1] + b',"run_id":"RUN-other"}'
    with pytest.raises(ValueError):
        sandbox_broker._request(raw)


def test_client_round_trip_has_runtime_identity_and_no_docker_authority(tmp_path):
    socket_path = Path(f"/tmp/vfa-broker-{os.getpid()}-{uuid4().hex[:8]}.sock")
    server = sandbox_broker._Server(str(socket_path))

    class FakeBackend:
        security_profile = {"network": "none", "host_mounts": []}

        def execute(self, request):
            assert request.run_id == "RUN-test"
            return SandboxResult(
                passed=True,
                exit_code=0,
                output={"ok": True, "result": {"value": "1"}, "runtime": {"python": "3.11.0"}},
                duration_ms=2,
                security=self.security_profile,
            )

    server.backend = FakeBackend()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = BrokerSandboxBackend(socket_path=str(socket_path))
        result = client.execute(
            SandboxRequest(
                source="def execute(inputs):\n    return inputs",
                test_source="def run_tests(fn, inputs):\n    return {'passed': 1}",
                fixture={"value": "1"},
                run_id="RUN-test",
                task_id="TASK-test",
                capability_id="generated.fcf",
                generation_attempt=1,
            )
        )
        assert result.passed and result.output["result"] == {"value": "1"}
        assert client.backend_name == "docker-broker"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        socket_path.unlink(missing_ok=True)


def test_client_fails_closed_when_broker_is_unavailable(tmp_path):
    result = BrokerSandboxBackend(socket_path=str(tmp_path / "missing.sock")).execute(
        SandboxRequest(
            source="def execute(inputs):\n    return inputs",
            test_source="def run_tests(fn, inputs):\n    return {'passed': 1}",
            fixture={"value": "1"},
            run_id="RUN-test",
            task_id="TASK-test",
            capability_id="generated.fcf",
            generation_attempt=1,
        )
    )
    assert not result.passed
    assert result.output["error"]["code"] == "SANDBOX_RUNTIME_NOT_READY"


def test_oversized_frame_rejected_without_allocation():
    class Connection:
        calls = 0

        def recv(self, size):
            self.calls += 1
            return (
                struct.pack("!I", sandbox_broker.MAX_REQUEST_BYTES + 1)
                if self.calls == 1
                else b""
            )

    from src.tooling.generated_sandbox import _receive_frame

    with pytest.raises(ValueError):
        _receive_frame(Connection(), sandbox_broker.MAX_REQUEST_BYTES)
