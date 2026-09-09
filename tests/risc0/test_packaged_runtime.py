import json
from pathlib import Path

import pytest

from src.adapters.risc0 import packaged_runtime


def _fixture(tmp_path: Path):
    files = {
        packaged_runtime.HOST_NAME: b"host",
        packaged_runtime.R0VM_NAME: b"r0vm",
        packaged_runtime.GUEST_NAME: b"guest",
    }
    for name, value in files.items():
        path = tmp_path / name
        path.write_bytes(value)
        path.chmod(0o555 if name != packaged_runtime.GUEST_NAME else 0o444)
    sha = {name: packaged_runtime._sha256(tmp_path / name) for name in files}
    manifest = {
        "schema": packaged_runtime.SCHEMA,
        "risc0_version": packaged_runtime.RISC0_VERSION,
        "r0vm_version": packaged_runtime.R0VM_VERSION,
        "target_arch": packaged_runtime.TARGET_ARCH,
        "host_binary": packaged_runtime.HOST_NAME,
        "host_sha256": sha[packaged_runtime.HOST_NAME],
        "r0vm_binary": packaged_runtime.R0VM_NAME,
        "r0vm_sha256": sha[packaged_runtime.R0VM_NAME],
        "guest_elf": packaged_runtime.GUEST_NAME,
        "guest_elf_sha256": sha[packaged_runtime.GUEST_NAME],
        "method_image_id": packaged_runtime.EXPECTED_REVENUE_GROWTH_IMAGE_ID,
        "source_commit": "checkpoint",
        "source_set_sha256": packaged_runtime.SOURCE_SET_SHA256,
        "guest_builder_digest": (
            "sha256:3e12f71bacd27527a61dea96fa0e53e468c99aa261d3a1019b593f6dbd943eb3"
        ),
        "distribution_archive_sha256": (
            "sha256:615d961bfb81d318db5071d7548389c850e324ac7f421c075176daf26082a60a"
        ),
    }
    (tmp_path / packaged_runtime.MANIFEST_NAME).write_text(json.dumps(manifest))
    return manifest


def _identity(command, *, env):
    del env
    if command[-1] == "--version":
        return "risc0-r0vm 3.0.6"
    return json.dumps(
        {
            "status": "READY",
            "backend": "risc0",
            "program_id": "revenue_growth_v1",
            "image_id": packaged_runtime.EXPECTED_REVENUE_GROWTH_IMAGE_ID,
            "dev_mode": False,
        }
    )


def test_packaged_runtime_validates_exact_files_and_identity(tmp_path, monkeypatch):
    manifest = _fixture(tmp_path)
    monkeypatch.setattr(packaged_runtime.sys, "platform", "linux")
    monkeypatch.setattr(packaged_runtime.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(packaged_runtime, "_run", _identity)
    result = packaged_runtime.load_packaged_proof_runtime(tmp_path)
    assert result.host_sha256 == manifest["host_sha256"]
    assert result.method_image_id == packaged_runtime.EXPECTED_REVENUE_GROWTH_IMAGE_ID


@pytest.mark.parametrize("mutation", ["host", "version", "extra", "platform"])
def test_packaged_runtime_fails_closed(tmp_path, monkeypatch, mutation):
    manifest = _fixture(tmp_path)
    monkeypatch.setattr(packaged_runtime.sys, "platform", "linux")
    monkeypatch.setattr(packaged_runtime.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(packaged_runtime, "_run", _identity)
    if mutation == "host":
        host = tmp_path / packaged_runtime.HOST_NAME
        host.chmod(0o755)
        host.write_bytes(b"changed")
    elif mutation == "version":
        manifest["r0vm_version"] = "other"
    elif mutation == "extra":
        manifest["unexpected"] = True
    else:
        monkeypatch.setattr(packaged_runtime.platform, "machine", lambda: "aarch64")
    if mutation in {"version", "extra"}:
        (tmp_path / packaged_runtime.MANIFEST_NAME).write_text(json.dumps(manifest))
    with pytest.raises(RuntimeError):
        packaged_runtime.load_packaged_proof_runtime(tmp_path)
