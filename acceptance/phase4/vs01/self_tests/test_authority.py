from __future__ import annotations

import json
import sys
from pathlib import Path


VS01_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VS01_ROOT))

from harness.authority import AuthorityError, verify_authority  # noqa: E402


def test_frozen_contract_authority_is_revision_qualified() -> None:
    result = verify_authority()
    assert result["status"] == "PASS"
    assert result["contract_component_count"] == 14
    assert result["v17_r2_canonical_sha256"] == (
        "fc184034e448e85190aa4cfd92b89e90b9f258307632920daa8d8cd73c600c19"
    )
    assert result["phase4_contract_set_sha256"] == (
        "0bf6c824d553847fa129a429715aedc36a30601a97421f4447cdd3f6d6a81741"
    )


def test_authority_rejects_a_tampered_receipt(tmp_path: Path) -> None:
    authority = json.loads((VS01_ROOT / "contract_authority.json").read_text(encoding="utf-8"))
    authority["promotion"]["byte_sha256"] = "0" * 64
    tampered = tmp_path / "authority.json"
    tampered.write_text(json.dumps(authority), encoding="utf-8")

    try:
        verify_authority(tampered)
    except AuthorityError as error:
        assert "hash mismatch" in str(error)
    else:
        raise AssertionError("tampered authority must fail closed")
