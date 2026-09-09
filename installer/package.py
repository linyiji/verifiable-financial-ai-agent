"""Prepare immutable distribution assets locally; never publishes them."""

import argparse
import hashlib
import io
import json
import re
import subprocess
import zipfile
from pathlib import Path

from installer.state import private_write

SOURCE_IDENTITY = "evaluator-source.json"


def bind_source_identity(raw: bytes, *, version: str, commit: str) -> bytes:
    """Embed non-secret immutable identity for installs launched from an unpacked ZIP."""
    source = io.BytesIO(raw)
    with zipfile.ZipFile(source, "r") as archive:
        if SOURCE_IDENTITY in archive.namelist():
            raise ValueError("Source identity path already exists")
    metadata = json.dumps(
        {"schema": 1, "version": version, "commit": commit},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    target = io.BytesIO(raw)
    with zipfile.ZipFile(target, "a", compression=zipfile.ZIP_DEFLATED) as archive:
        info = zipfile.ZipInfo(SOURCE_IDENTITY, date_time=(1980, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o100644 << 16
        archive.writestr(info, metadata)
    return target.getvalue()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", args.version):
        raise SystemExit("Invalid version")
    if subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"]).strip():
        raise SystemExit("Commit the reviewed installer before packaging.")
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    archive = output / "evaluator-package.zip"
    if archive.exists():
        raise SystemExit("Package already exists; choose a new output directory.")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    raw = bind_source_identity(
        subprocess.check_output(["git", "archive", "--format=zip", "HEAD"]),
        version=args.version,
        commit=commit,
    )
    archive.write_bytes(raw)
    private_write(
        output / "evaluator-manifest.json",
        json.dumps(
            {
                "schema": 1,
                "version": args.version,
                "commit": commit,
                "archive_url": f"https://github.com/linyiji/verifiable-financial-ai-agent/releases/download/{args.version}/evaluator-package.zip",
                "sha256": hashlib.sha256(raw).hexdigest(),
                "full_proof_runtime": "PACKAGED_VERIFIED_RISC0_3_0_6",
                "generated_sandbox_runtime": "GOVERNED_BROKER",
            },
            indent=2,
        ),
    )
    print("Local package prepared. PUBLICATION_REQUIRED; no release was created.")


if __name__ == "__main__":
    main()
