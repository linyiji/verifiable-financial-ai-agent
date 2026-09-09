"""Build-input content checks; OCI revision labels are not content attestations.

This manifest is integrity metadata, not a signature. Its trust anchor is the
separately verified public archive hash / reviewed Git commit. Config IDs, platform
manifest digests and multi-platform index digests are deliberately distinct types.
"""

import hashlib
import re
from pathlib import Path

BUILD_INPUTS = "evaluator-build-inputs.sha256"
SAFE_PATH = re.compile(r"^[A-Za-z0-9_.\-/]+$")
BUILD_DIRECTORIES = frozenset(
    {"src", "apps", "installer", "scripts", "contracts", "alembic", "zk", "runtime"}
)
BUILD_FILES = frozenset({"pyproject.toml", "README.md", ".dockerignore", "evaluator-source.json"})


def safe_relative(name):
    if (
        not SAFE_PATH.fullmatch(name)
        or name.startswith("/")
        or any(p in {"", ".", ".."} for p in name.split("/"))
    ):
        raise ValueError("BUILD_INPUT_PATH_UNSAFE")
    return name


def content_manifest(files: dict[str, bytes]) -> bytes:
    if BUILD_INPUTS in files:
        raise ValueError("BUILD_INPUT_MANIFEST_ALREADY_EXISTS")
    return "".join(
        f"{hashlib.sha256(files[name]).hexdigest()}  {safe_relative(name)}\n"
        for name in sorted(files)
        if name in BUILD_FILES or name.split("/", 1)[0] in BUILD_DIRECTORIES
    ).encode("ascii")


def verify_build_inputs(root: Path):
    root = root.resolve(strict=True)
    manifest = root / BUILD_INPUTS
    if manifest.is_symlink() or not manifest.is_file():
        raise ValueError("BUILD_INPUT_MANIFEST_REQUIRED")
    seen = set()
    for line in manifest.read_text(encoding="ascii").splitlines():
        digest, separator, name = line.partition("  ")
        if not separator or not re.fullmatch("[a-f0-9]{64}", digest):
            raise ValueError("BUILD_INPUT_MANIFEST_INVALID")
        safe_relative(name)
        if name in seen:
            raise ValueError("BUILD_INPUT_DUPLICATE")
        seen.add(name)
        path = root / name
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
            raise ValueError("BUILD_INPUT_MISSING_OR_UNSAFE")
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("BUILD_INPUT_CONTENT_MISMATCH")
    if not seen:
        raise ValueError("BUILD_INPUT_MANIFEST_EMPTY")
    # Ignore runtime-generated caches/credentials, never unmanifested executable
    # inputs. This includes frontend source and build configuration.
    for directory in BUILD_DIRECTORIES:
        for path in (root / directory).rglob("*"):
            if {"__pycache__", "node_modules", "dist"}.intersection(path.parts):
                continue
            if path.is_file() and path.relative_to(root).as_posix() not in seen:
                raise ValueError("BUILD_INPUT_UNDECLARED")
    return {"files": len(seen), "content_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest()}


def typed_image_identity(*, config_id, platform_manifest=None, index_digest=None):
    if not isinstance(config_id, str) or not re.fullmatch("sha256:[a-f0-9]{64}", config_id):
        raise ValueError("IMAGE_CONFIG_ID_REQUIRED")
    result = {
        "config_id": config_id,
        "platform_manifest": platform_manifest,
        "index_digest": index_digest,
    }
    if any(v is not None and not re.fullmatch("sha256:[a-f0-9]{64}", v) for v in result.values()):
        raise ValueError("IMAGE_DIGEST_INVALID")
    return result
