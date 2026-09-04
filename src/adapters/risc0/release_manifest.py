from __future__ import annotations

import hashlib
import json
import struct
import subprocess
from collections.abc import Iterable
from pathlib import Path
from typing import Any

RELEASE_MANIFEST_SCHEMA = "vfas.risc0.release-manifest.v1"
SOURCE_SET_ALGORITHM = "vfas-risc0-source-set-sha256-v1"
SOURCE_SET_DOMAIN = b"VFAS_RISC0_RELEASE_SOURCE_SET_V1\0"
RELEASE_MANIFEST_RELATIVE_PATH = Path("zk/revenue_growth/RISC_ZERO_RELEASE_MANIFEST.json")


def _sha256(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def discover_release_sources(repository_root: Path) -> tuple[Path, ...]:
    """Return the complete, deterministic RISC Zero release source closure."""

    root = repository_root.resolve(strict=True)
    fixed = (
        "zk/revenue_growth/Cargo.toml",
        "zk/revenue_growth/Cargo.lock",
        "zk/revenue_growth/rust-toolchain.toml",
        "zk/revenue_growth/build-host.sh",
        "zk/revenue_growth/normalize_macos_host.py",
        "zk/revenue_growth/host/Cargo.toml",
        "zk/revenue_growth/methods/Cargo.toml",
        "zk/revenue_growth/methods/build.rs",
        "zk/revenue_growth/methods/guest/Cargo.toml",
        "zk/revenue_growth/methods/guest/Cargo.lock",
        "zk/revenue_growth/shared/Cargo.toml",
    )
    discovered = {Path(value) for value in fixed}
    for pattern in (
        "zk/revenue_growth/host/src/**/*.rs",
        "zk/revenue_growth/methods/src/**/*.rs",
        "zk/revenue_growth/methods/guest/src/**/*.rs",
        "zk/revenue_growth/shared/src/**/*.rs",
    ):
        discovered.update(path.relative_to(root) for path in root.glob(pattern))

    sources: list[Path] = []
    for relative in sorted(discovered, key=lambda value: value.as_posix().encode("utf-8")):
        if relative.is_absolute() or ".." in relative.parts:
            raise RuntimeError("release source path escapes repository root")
        requested = root / relative
        if requested.is_symlink() or not requested.is_file():
            raise RuntimeError(f"release source must be a regular non-symlink file: {relative}")
        resolved = requested.resolve(strict=True)
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise RuntimeError("release source path escapes repository root") from exc
        sources.append(relative)
    return tuple(sources)


def source_set_sha256(repository_root: Path, sources: Iterable[Path]) -> str:
    """Hash path and raw bytes with unambiguous length framing."""

    root = repository_root.resolve(strict=True)
    digest = hashlib.sha256(SOURCE_SET_DOMAIN)
    normalized = sorted(
        (Path(source) for source in sources), key=lambda value: value.as_posix().encode("utf-8")
    )
    for relative in normalized:
        if relative.is_absolute() or ".." in relative.parts:
            raise RuntimeError("release source path escapes repository root")
        requested = root / relative
        if requested.is_symlink() or not requested.is_file():
            raise RuntimeError(f"release source must be a regular non-symlink file: {relative}")
        resolved = requested.resolve(strict=True)
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise RuntimeError("release source path escapes repository root") from exc
        path_bytes = relative.as_posix().encode("utf-8")
        content = resolved.read_bytes()
        digest.update(struct.pack(">I", len(path_bytes)))
        digest.update(path_bytes)
        digest.update(struct.pack(">Q", len(content)))
        digest.update(content)
    return f"sha256:{digest.hexdigest()}"


def _tracked_paths(repository_root: Path) -> set[str]:
    completed = subprocess.run(
        ("git", "ls-files", "-z"),
        cwd=repository_root,
        check=False,
        capture_output=True,
        timeout=30,
    )
    if completed.returncode != 0:
        raise RuntimeError("unable to inspect tracked release sources")
    return {value.decode("utf-8") for value in completed.stdout.split(b"\0") if value}


def load_and_verify_release_manifest(
    repository_root: Path,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    """Load and fail closed unless the manifest matches the tracked source closure."""

    root = repository_root.resolve(strict=True)
    manifest = (
        root / RELEASE_MANIFEST_RELATIVE_PATH
        if manifest_path is None
        else manifest_path.resolve(strict=True)
    )
    if manifest.is_symlink() or not manifest.is_file():
        raise RuntimeError("RISC Zero release manifest must be a regular non-symlink file")
    try:
        manifest.relative_to(root)
    except ValueError as exc:
        raise RuntimeError("RISC Zero release manifest escapes repository root") from exc
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("invalid RISC Zero release manifest") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != RELEASE_MANIFEST_SCHEMA:
        raise RuntimeError("unsupported RISC Zero release manifest schema")
    source_closure = payload.get("source_closure")
    if not isinstance(source_closure, dict):
        raise RuntimeError("RISC Zero release source closure is missing")
    if source_closure.get("algorithm") != SOURCE_SET_ALGORITHM:
        raise RuntimeError("unsupported RISC Zero release source-set algorithm")

    sources = discover_release_sources(root)
    entries = source_closure.get("files")
    if not isinstance(entries, list):
        raise RuntimeError("RISC Zero release source entries are missing")
    expected_paths = [source.as_posix() for source in sources]
    manifest_paths = [entry.get("path") for entry in entries if isinstance(entry, dict)]
    if manifest_paths != expected_paths or len(manifest_paths) != len(entries):
        raise RuntimeError("RISC Zero release manifest source closure differs from discovery")
    tracked = _tracked_paths(root)
    if any(path not in tracked for path in expected_paths):
        raise RuntimeError("RISC Zero release source closure contains an untracked file")
    for entry, relative in zip(entries, sources, strict=True):
        content = (root / relative).read_bytes()
        if entry.get("size_bytes") != len(content) or entry.get("sha256") != _sha256(content):
            raise RuntimeError(f"RISC Zero release source identity mismatch: {relative}")
    if source_closure.get("source_set_sha256") != source_set_sha256(root, sources):
        raise RuntimeError("RISC Zero release source-set identity mismatch")
    return payload


def release_manifest_sha256(manifest_path: Path) -> str:
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise RuntimeError("RISC Zero release manifest must be a regular non-symlink file")
    return _sha256(manifest_path.read_bytes())
