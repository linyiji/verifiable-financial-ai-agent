"""Prepare immutable distribution assets locally; never publishes them."""

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

from installer.state import private_write


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
    raw = subprocess.check_output(["git", "archive", "--format=zip", "HEAD"])
    archive.write_bytes(raw)
    private_write(
        output / "evaluator-manifest.json",
        json.dumps(
            {
                "schema": 1,
                "version": args.version,
                "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
                "archive_url": f"https://github.com/linyiji/verifiable-financial-ai-agent/releases/download/{args.version}/evaluator-package.zip",
                "sha256": hashlib.sha256(raw).hexdigest(),
                "full_proof_runtime": "NOT_PACKAGED",
            },
            indent=2,
        ),
    )
    print("Local package prepared. PUBLICATION_REQUIRED; no release was created.")


if __name__ == "__main__":
    main()
