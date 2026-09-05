"""Revision-qualified frozen-contract verification for the VS01 harness."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

VS01_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
AUTHORITY_PATH = VS01_ROOT / "contract_authority.json"


class AuthorityError(RuntimeError):
    """The immutable authority cannot be resolved or does not match its receipt."""


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _git_bytes(revision: str, path: str, *, repository: Path) -> bytes:
    process = subprocess.run(
        ["git", "show", f"{revision}:{path}"],
        cwd=repository,
        check=False,
        capture_output=True,
    )
    if process.returncode != 0:
        raise AuthorityError(f"missing revision-qualified authority object: {revision}:{path}")
    return process.stdout


def _require_hash(*, label: str, actual: str, expected: str) -> None:
    if actual != expected:
        raise AuthorityError(f"{label} hash mismatch: expected {expected}, received {actual}")


def verify_authority(
    authority_path: Path = AUTHORITY_PATH,
    *,
    repository: Path = REPOSITORY_ROOT,
) -> dict[str, Any]:
    """Verify every identity needed before an integrated VS01 attempt starts."""

    authority = json.loads(authority_path.read_text(encoding="utf-8"))
    revision = authority["contract_revision"]

    promotion_config = authority["promotion"]
    promotion_bytes = _git_bytes(revision, promotion_config["path"], repository=repository)
    _require_hash(
        label="freeze promotion bytes",
        actual=_sha256(promotion_bytes),
        expected=promotion_config["byte_sha256"],
    )
    promotion = json.loads(promotion_bytes)
    if promotion.get("decision") != promotion_config["decision"]:
        raise AuthorityError("final freeze promotion is not PASS")
    approved = promotion.get("approved_phase3_parent", {})
    if approved.get("sha") != authority["approved_source"]["commit"]:
        raise AuthorityError("approved source commit is not the VS01 base authority")
    if approved.get("tree") != authority["approved_source"]["tree"]:
        raise AuthorityError("approved source tree is not the VS01 base authority")

    v17_config = authority["v17_r2"]
    v17_bytes = _git_bytes(revision, v17_config["path"], repository=repository)
    _require_hash(
        label="V17 R2 bytes",
        actual=_sha256(v17_bytes),
        expected=v17_config["byte_sha256"],
    )
    _require_hash(
        label="V17 R2 canonical payload",
        actual=_sha256(_canonical_json(json.loads(v17_bytes))),
        expected=v17_config["canonical_sha256"],
    )

    contract_config = authority["phase4_contract_set"]
    contract_bytes = _git_bytes(revision, contract_config["path"], repository=repository)
    _require_hash(
        label="Phase 4 contract manifest bytes",
        actual=_sha256(contract_bytes),
        expected=contract_config["byte_sha256"],
    )
    contract_manifest = json.loads(contract_bytes)
    components = contract_manifest.get("contract_components", {})
    if len(components) != contract_config["component_count"]:
        raise AuthorityError("Phase 4 contract component count mismatch")
    component_set = sorted(
        (
            {"id": component_id, "sha256": component["sha256"]}
            for component_id, component in components.items()
        ),
        key=lambda item: item["id"],
    )
    _require_hash(
        label="Phase 4 canonical contract set",
        actual=_sha256(_canonical_json(component_set)),
        expected=contract_config["canonical_sha256"],
    )

    verified_contract_components: list[str] = []
    for component_id, component in sorted(components.items()):
        if "payload" in component:
            actual_component_hash = _sha256(_canonical_json(component["payload"]))
        elif isinstance(component.get("artifact"), str):
            actual_component_hash = _sha256(
                _git_bytes(revision, component["artifact"], repository=repository)
            )
        else:
            raise AuthorityError(
                f"{component_id} has neither a canonical payload nor an exact artifact"
            )
        _require_hash(
            label=f"{component_id} frozen component",
            actual=actual_component_hash,
            expected=component["sha256"],
        )
        verified_contract_components.append(component_id)

    verified_components: list[str] = []
    for component in authority["exact_byte_components"]:
        component_bytes = _git_bytes(revision, component["path"], repository=repository)
        _require_hash(
            label=f"{component['id']} bytes",
            actual=_sha256(component_bytes),
            expected=component["sha256"],
        )
        manifest_entry = components.get(component["id"])
        if not manifest_entry or manifest_entry.get("sha256") != component["sha256"]:
            raise AuthorityError(f"{component['id']} is not bound by the contract manifest")
        verified_components.append(component["id"])

    verified_addenda: list[str] = []
    for addendum in authority.get("revision_bound_addenda", []):
        addendum_bytes = _git_bytes(revision, addendum["path"], repository=repository)
        _require_hash(
            label=f"{addendum['id']} bytes",
            actual=_sha256(addendum_bytes),
            expected=addendum["sha256"],
        )
        verified_addenda.append(addendum["id"])

    return {
        "schema_version": authority["schema_version"],
        "status": "PASS",
        "contract_revision": revision,
        "approved_source": authority["approved_source"],
        "promotion_decision": promotion["decision"],
        "v17_r2_canonical_sha256": v17_config["canonical_sha256"],
        "phase4_contract_set_sha256": contract_config["canonical_sha256"],
        "contract_component_count": len(components),
        "contract_components_verified": verified_contract_components,
        "exact_byte_components_verified": verified_components,
        "revision_bound_addenda_verified": verified_addenda,
        "wire": authority["wire"],
    }


if __name__ == "__main__":
    print(json.dumps(verify_authority(), indent=2, sort_keys=True))
