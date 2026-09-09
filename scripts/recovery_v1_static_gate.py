"""Read-only candidate path/secret/link gate; never opens private credentials.

This is a bounded pattern scan, not a claim of perfect secret detection. The
original untracked audit is excluded from the candidate and preserved separately.
"""

import hashlib
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote


def main():
    root = Path(__file__).resolve().parents[1]
    names = (
        subprocess.check_output(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=root
        )
        .decode()
        .split("\0")
    )
    denied_suffixes = {".vfacred", ".vfaeval", ".pem", ".key", ".db", ".sqlite"}
    public_credential_docs = {
        "credentials/.gitkeep",
        "credentials/README.md",
        "credentials/README.zh-CN.md",
    }
    # Reviewed negative redaction fixtures, pinned to full-file bytes. A changed
    # fixture must be reviewed again; no directory-wide exception is permitted.
    negative_fixtures = {
        "tests/phase4/backend_product/test_contracts_and_errors.py": (
            "5c59b16085cecc9ac1e76687b8fd415d17d5df0a6c0bf6418998bc45e612a35f"
        ),
        "tests/phase4/backend_product/test_projection_safety.py": (
            "f9525b31faa0284ae47c78b86ed8b0a7fbde794a9c58c03ec1d03b90294268c5"
        ),
    }
    patterns = (
        re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
        re.compile(rb"\bgithub_pat_[A-Za-z0-9_]{60,}\b"),
        re.compile(rb"\bsk-[A-Za-z0-9_-]{32,}\b"),
        re.compile(rb"\bAKIA[A-Z0-9]{16}\b"),
    )
    findings, links, examined = [], [], 0
    hashes = {}
    for name in sorted(set(names)):
        if not name or name.startswith("docs/audits/"):
            continue
        path = Path(name)
        if (
            path.is_absolute()
            or ".." in path.parts
            or ("credentials" in path.parts and name not in public_credential_docs)
            or any(part.startswith(".env") and part != ".env.example" for part in path.parts)
            or path.suffix in denied_suffixes
        ):
            findings.append({"path": name, "kind": "PRIVATE_OR_UNSAFE_PATH"})
            continue  # Never read the denied path.
        source = root / path
        if source.is_symlink():
            findings.append({"path": name, "kind": "SYMLINK"})
            continue
        if not source.is_file():
            continue
        raw = source.read_bytes()
        examined += 1
        if any(pattern.search(raw) for pattern in patterns) and hashlib.sha256(
            raw
        ).hexdigest() != negative_fixtures.get(name):
            findings.append({"path": name, "kind": "SECRET_PATTERN"})
        if path.parts[0] in {"src", "apps", "installer", "alembic", "contracts", "runtime"}:
            hashes[name] = hashlib.sha256(raw).hexdigest()
        if source.suffix == ".md" and (
            "RECOVERABLE_EXECUTION_AND_POLICY_V1" in name or "OWNER_POLICY_V1" in name
        ):
            for target in re.findall(r"\]\(([^)]+)\)", raw.decode()):
                if "://" in target or target.startswith("#"):
                    continue
                local = unquote(target.split("#")[0])
                if not (source.parent / local).exists():
                    links.append({"path": name, "target": target})
    result = {
        "candidate_files_scanned": examined,
        "private_paths_and_symlinks": "PASS" if not findings else "FAIL",
        "secret_pattern_scan": "PASS" if not findings else "FAIL",
        "new_bilingual_links": "PASS" if not links else "FAIL",
        "findings": findings,
        "broken_links": links,
        "runtime_input_manifest": hashes,
        "limitations": "Pattern scan only; no real credential values accessed for comparison.",
        "reviewed_negative_fixture_hashes": negative_fixtures,
    }
    print(json.dumps(result, indent=2))
    return bool(findings or links)


if __name__ == "__main__":
    raise SystemExit(main())
