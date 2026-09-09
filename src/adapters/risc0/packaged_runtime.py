"""Fail-closed identity checks for the packaged Linux RISC Zero runtime."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from src.adapters.risc0.adapter import EXPECTED_REVENUE_GROWTH_IMAGE_ID

SCHEMA = "vfas.risc0.packaged-runtime.v1"
RISC0_VERSION = "3.0.6"
R0VM_VERSION = "3.0.6"
TARGET_ARCH = "linux/amd64"
SOURCE_SET_SHA256 = "sha256:f9298b08b95126e4ed225af59463f9368724d9dc2de938a80abb06982fe033cc"
MANIFEST_NAME = "PROOF_RUNTIME_MANIFEST.json"
HOST_NAME = "revenue-growth-proof-host"
R0VM_NAME = "r0vm"
GUEST_NAME = "revenue-growth-guest"


@dataclass(frozen=True, slots=True)
class PackagedProofRuntime:
    root: Path
    host_binary: Path
    r0vm_binary: Path
    guest_elf: Path
    host_sha256: str
    r0vm_sha256: str
    guest_elf_sha256: str
    method_image_id: str
    source_commit: str


def _sha256(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _strict_json(raw: bytes):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise RuntimeError("duplicate Proof Runtime manifest field")
            result[key] = value
        return result

    return json.loads(raw, object_pairs_hook=unique)


def _regular(root: Path, name: str) -> Path:
    requested = root / name
    if requested.is_symlink() or not requested.is_file():
        raise RuntimeError("packaged Proof Runtime file is missing")
    resolved = requested.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise RuntimeError("packaged Proof Runtime path escapes its root") from exc
    return resolved


def _run(command: tuple[str, ...], *, env: dict[str, str]) -> str:
    completed = subprocess.run(
        command,
        env=env,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if completed.returncode or len(completed.stdout) > 65536 or len(completed.stderr) > 65536:
        raise RuntimeError("packaged Proof Runtime identity command failed")
    return completed.stdout.decode("utf-8", errors="strict").strip()


def load_packaged_proof_runtime(root: str | Path = "/opt/vfa-proof") -> PackagedProofRuntime:
    requested = Path(root)
    if requested.is_symlink() or not requested.is_dir():
        raise RuntimeError("packaged Proof Runtime root is missing")
    resolved_root = requested.resolve(strict=True)
    manifest_path = _regular(resolved_root, MANIFEST_NAME)
    try:
        manifest = _strict_json(manifest_path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("invalid packaged Proof Runtime manifest") from exc
    required = {
        "schema",
        "risc0_version",
        "r0vm_version",
        "target_arch",
        "host_binary",
        "host_sha256",
        "r0vm_binary",
        "r0vm_sha256",
        "guest_elf",
        "guest_elf_sha256",
        "method_image_id",
        "source_commit",
        "source_set_sha256",
        "guest_builder_digest",
        "distribution_archive_sha256",
    }
    if not isinstance(manifest, dict) or set(manifest) != required:
        raise RuntimeError("unsupported packaged Proof Runtime manifest")
    if (
        manifest["schema"] != SCHEMA
        or manifest["risc0_version"] != RISC0_VERSION
        or manifest["r0vm_version"] != R0VM_VERSION
        or manifest["target_arch"] != TARGET_ARCH
        or manifest["method_image_id"] != EXPECTED_REVENUE_GROWTH_IMAGE_ID
        or manifest["source_set_sha256"] != SOURCE_SET_SHA256
        or manifest["guest_builder_digest"]
        != "sha256:3e12f71bacd27527a61dea96fa0e53e468c99aa261d3a1019b593f6dbd943eb3"
        or manifest["distribution_archive_sha256"]
        != "sha256:615d961bfb81d318db5071d7548389c850e324ac7f421c075176daf26082a60a"
        or manifest["host_binary"] != HOST_NAME
        or manifest["r0vm_binary"] != R0VM_NAME
        or manifest["guest_elf"] != GUEST_NAME
    ):
        raise RuntimeError("packaged Proof Runtime identity mismatch")
    if sys.platform != "linux" or platform.machine() not in {"x86_64", "amd64"}:
        raise RuntimeError("packaged Proof Runtime platform mismatch")
    host = _regular(resolved_root, HOST_NAME)
    r0vm = _regular(resolved_root, R0VM_NAME)
    guest = _regular(resolved_root, GUEST_NAME)
    for path in (host, r0vm):
        if not os.access(path, os.X_OK):
            raise RuntimeError("packaged Proof Runtime executable mode is missing")
    for path, field in (
        (host, "host_sha256"),
        (r0vm, "r0vm_sha256"),
        (guest, "guest_elf_sha256"),
    ):
        if _sha256(path) != manifest[field]:
            raise RuntimeError("packaged Proof Runtime digest mismatch")
    child_env = {
        "PATH": f"{resolved_root}:/usr/local/bin:/usr/bin:/bin",
        "TMPDIR": "/tmp",
        "RUST_BACKTRACE": "0",
    }
    if _run((str(r0vm), "--version"), env=child_env) != "risc0-r0vm 3.0.6":
        raise RuntimeError("packaged r0vm version mismatch")
    try:
        host_identity = _strict_json(_run((str(host), "image-id"), env=child_env).encode())
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("invalid packaged Proof host identity") from exc
    if (
        not isinstance(host_identity, dict)
        or host_identity.get("status") != "READY"
        or host_identity.get("backend") != "risc0"
        or host_identity.get("program_id") != "revenue_growth_v1"
        or host_identity.get("image_id") != EXPECTED_REVENUE_GROWTH_IMAGE_ID
        or host_identity.get("dev_mode") is not False
    ):
        raise RuntimeError("packaged Proof host method identity mismatch")
    return PackagedProofRuntime(
        root=resolved_root,
        host_binary=host,
        r0vm_binary=r0vm,
        guest_elf=guest,
        host_sha256=manifest["host_sha256"],
        r0vm_sha256=manifest["r0vm_sha256"],
        guest_elf_sha256=manifest["guest_elf_sha256"],
        method_image_id=manifest["method_image_id"],
        source_commit=manifest["source_commit"],
    )
