import io
import subprocess
import zipfile
from pathlib import Path

import pytest

from installer.image_identity import BUILD_INPUTS, typed_image_identity, verify_build_inputs
from installer.package import bind_source_identity
from src.application.execution import _compact_json_value

VERIFY = Path(__file__).resolve().parents[2] / "scripts/verify-build-inputs.sh"


def git(root, *args):
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
    )


def test_semantic_sentinels_survive_dictionary_list_and_depth_boundaries():
    identity = {
        "period": "2025-FY",
        "currency": "USD",
        "unit": "millions",
        "symbol": "NVDA",
        "support": {"E:31": "CALC:31"},
    }
    value = {**{f"a{i:02d}": i for i in range(35)}, **identity}
    compact = _compact_json_value(value)
    assert {key: compact[key] for key in identity} == identity
    assert "a34" not in compact  # unrelated overflow still follows original bound
    rows = [{"narrative": "ordinary"}] * 31 + [identity]
    compact_rows = _compact_json_value(rows)
    assert compact_rows[-1] == identity
    assert len(compact_rows) == 31
    nested = {"a": {"b": {"c": {"d": {"e": identity}}}}}
    assert _compact_json_value(nested) == nested


def test_oversized_semantics_fail_explicitly_instead_of_fabricating_complete_context():
    with pytest.raises(ValueError, match="CONTEXT_SEMANTICS_EXCEED_BOUND"):
        _compact_json_value({"symbol": "NVDA", "support": "X" * 40000})
    assert _compact_json_value("X" * 1001).endswith("...")


def test_semantic_descendant_does_not_retain_unrelated_outer_narrative():
    identity = {
        "period": "2025-FY",
        "currency": "USD",
        "unit": "millions",
        "symbol": "NVDA",
        "support": {"E:31": "CALC:31"},
    }
    value = {"available_calculations": [identity], "narrative": "X" * 40000}
    compact = _compact_json_value(value)
    assert compact["available_calculations"] == [identity]
    assert len(compact["narrative"]) == 1000
    assert len(str(compact)) < 32768


def test_semantic_record_compacts_unrelated_narrative_but_not_reference_values():
    value = {
        "symbol": "NVDA",
        "period": "2025-FY",
        "currency": "USD",
        "unit": "millions",
        "value": "-42.125",
        "narrative": "X" * 40000,
        "supporting_evidence_ids": [f"E:{i}" for i in range(40)],
    }
    compact = _compact_json_value(value)
    assert compact["value"] == "-42.125"
    assert compact["supporting_evidence_ids"] == value["supporting_evidence_ids"]
    assert len(compact["narrative"]) == 1000


def package(tmp_path):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("README.md", "public")
        archive.writestr("src/example.py", "value = 1\n")
        archive.writestr("apps/web/src/main.tsx", "export const revision = 1;")
    raw = bind_source_identity(stream.getvalue(), version="offline", commit="a" * 40)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        archive.extractall(tmp_path)
    return tmp_path


def test_original_archive_without_git_and_explicit_directory_validates(tmp_path):
    root = package(tmp_path)
    assert not (root / ".git").exists()
    assert verify_build_inputs(root)["files"] == 4


@pytest.mark.parametrize("target", ["src/example.py", "apps/web/src/main.tsx"])
def test_tampered_backend_or_frontend_is_not_label_only_identity(tmp_path, target):
    root = package(tmp_path)
    (root / target).write_text("changed")
    with pytest.raises(ValueError, match="CONTENT_MISMATCH"):
        verify_build_inputs(root)


def test_undeclared_executable_input_rejected(tmp_path):
    root = package(tmp_path)
    (root / "src/injected.py").write_text("changed")
    with pytest.raises(ValueError, match="UNDECLARED"):
        verify_build_inputs(root)


def test_manifest_cannot_select_another_directory(tmp_path):
    root = package(tmp_path)
    (root / BUILD_INPUTS).write_text("a" * 64 + "  ../outside.py\n")
    with pytest.raises(ValueError, match="PATH_UNSAFE"):
        verify_build_inputs(root)


def test_digest_types_are_not_conflated():
    identities = typed_image_identity(
        config_id="sha256:" + "1" * 64,
        platform_manifest="sha256:" + "2" * 64,
        index_digest="sha256:" + "3" * 64,
    )
    assert len(set(identities.values())) == 3


def test_native_prebuild_gate_accepts_clean_git_and_docs_only_change(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src/a.py").write_text("value = 1")
    (tmp_path / "notes.md").write_text("docs")
    git(tmp_path, "init")
    git(tmp_path, "add", "src/a.py", "notes.md")
    git(
        tmp_path,
        "-c",
        "user.name=Offline",
        "-c",
        "user.email=offline@example.invalid",
        "commit",
        "-m",
        "fixture",
    )
    (tmp_path / "notes.md").write_text("docs-only update")
    command = ["bash", str(VERIFY), str(tmp_path)]
    assert subprocess.run(command, capture_output=True).returncode == 0
    (tmp_path / "src/a.py").write_text("runtime changed")
    result = subprocess.run(command, capture_output=True)
    assert result.returncode != 0
    assert b"BUILD_INPUT_DIRTY" in result.stdout


def test_native_prebuild_gate_checks_original_and_modified_unpacked_zip(tmp_path):
    root = package(tmp_path)
    command = ["bash", str(VERIFY), str(root)]
    assert subprocess.run(command, capture_output=True).returncode == 0
    (root / "apps/web/src/main.tsx").write_text("different frontend")
    result = subprocess.run(command, capture_output=True)
    assert result.returncode != 0
    assert b"CONTENT_MISMATCH" in result.stdout


def test_unidentified_no_git_directory_fails_closed(tmp_path):
    result = subprocess.run(["bash", str(VERIFY), str(tmp_path)], capture_output=True)
    assert result.returncode != 0
    assert b"MANIFEST_REQUIRED" in result.stdout
