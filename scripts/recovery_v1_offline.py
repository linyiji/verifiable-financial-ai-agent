"""Create a secret-free test snapshot. Never read registries, bundles or env files.

Run from the repository root; output is an isolated temporary directory.
Network isolation is provided by the caller's Docker internal network, not this copier.
"""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path


def snapshot():
    root = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
    paths = (
        subprocess.check_output(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=root
        )
        .decode()
        .split("\0")
    )
    destination = Path(tempfile.mkdtemp(prefix="vfa-recovery-v1-offline-"))
    allowed = {
        "src",
        "apps",
        "contracts",
        "installer",
        "alembic",
        "tests",
        "scripts",
        "docs",
        "examples",
        ".github",
        "runtime",
        "zk",
        "acceptance",
    }
    for name in paths:
        if not name:
            continue
        path = Path(name)
        if len(path.parts) > 1 and path.parts[0] not in allowed:
            continue
        if any(
            part in {"credentials", "node_modules", "__pycache__", ".git"}
            or part.startswith(".env")
            for part in path.parts
        ):
            continue
        if path.suffix.lower() in {".vfacred", ".db", ".sqlite", ".log", ".pem", ".key"}:
            continue
        source = root / path
        if source.is_symlink() or not source.is_file():
            continue
        target = destination / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    print(json.dumps({"snapshot": str(destination), "credentials_copied": False}))


if __name__ == "__main__":
    snapshot()
