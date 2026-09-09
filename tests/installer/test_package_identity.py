import io
import json
import zipfile

import pytest

from installer.package import SOURCE_IDENTITY, bind_source_identity

REVISION = "a" * 40


def archive_with(name="README.md"):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr(name, "public")
    return stream.getvalue()


def test_unpacked_release_contains_exact_source_identity():
    raw = bind_source_identity(archive_with(), version="evaluation-v3", commit=REVISION)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        assert archive.testzip() is None
        assert json.loads(archive.read(SOURCE_IDENTITY)) == {
            "schema": 1,
            "version": "evaluation-v3",
            "commit": REVISION,
        }


def test_source_identity_cannot_shadow_tracked_content():
    with pytest.raises(ValueError, match="already exists"):
        bind_source_identity(
            archive_with(SOURCE_IDENTITY), version="evaluation-v3", commit=REVISION
        )


def test_platform_installers_resolve_unpacked_release_identity():
    for path in ("scripts/install-evaluator.sh", "scripts/install-evaluator.ps1"):
        text = open(path, encoding="utf-8").read()
        assert "evaluator-source.json" in text
        assert "RUNTIME_IMAGE_IDENTITY_NOT_RESOLVED" in text
