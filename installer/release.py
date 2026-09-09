"""Resolve only published accepted release assets; never develop or mutable source HEAD."""

import hashlib
import io
import json
import re
import urllib.request
import zipfile
from pathlib import Path

from installer.errors import InstallError

REPOSITORY = "linyiji/verifiable-financial-ai-agent"
API = f"https://api.github.com/repos/{REPOSITORY}/releases"


def read_url(url, limit=100_000_000):
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            content = response.read(limit + 1)
        if len(content) > limit:
            raise ValueError()
        return content
    except Exception:
        raise InstallError("DOWNLOAD_FAILED") from None


def resolve(version=None, read=read_url):
    if version and not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", version):
        raise InstallError("PUBLICATION_REQUIRED")
    try:
        release = json.loads(read(API + ("/tags/" + version if version else "/latest")))
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", release["tag_name"]):
            raise ValueError()
        if release.get("draft") or (not version and release.get("prerelease")):
            raise ValueError()
        asset = next(a for a in release["assets"] if a["name"] == "evaluator-manifest.json")
        expected_prefix = (
            f"https://github.com/{REPOSITORY}/releases/download/{release['tag_name']}/"
        )
        if not asset["browser_download_url"].startswith(expected_prefix):
            raise ValueError()
        manifest = json.loads(read(asset["browser_download_url"]))
        if manifest["version"] != release["tag_name"] or not manifest["archive_url"].startswith(
            expected_prefix
        ):
            raise ValueError()
        if not re.fullmatch(r"[a-f0-9]{64}", manifest["sha256"]):
            raise ValueError()
        if not re.fullmatch(r"[a-f0-9]{40}", manifest.get("commit", "")):
            raise ValueError()
        if manifest.get("schema") != 1:
            raise ValueError()
        return manifest
    except Exception:
        raise InstallError("PUBLICATION_REQUIRED") from None


def unpack(manifest, destination, read=read_url):
    raw = read(manifest["archive_url"])
    if hashlib.sha256(raw).hexdigest() != manifest["sha256"]:
        raise InstallError("INTEGRITY_FAILED")
    destination = Path(destination)
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            entries = archive.infolist()
            if len({item.filename for item in entries}) != len(entries):
                raise ValueError()
            if len(entries) > 10000 or sum(i.file_size for i in entries) > 400_000_000:
                raise ValueError()
            for item in entries:
                name = item.filename
                if (
                    name.startswith(("/", "\\"))
                    or "\\" in name
                    or ":" in name
                    or ".." in Path(name).parts
                ):
                    raise ValueError()
                if (item.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError()
            # Extraction begins only after every member passes validation.
            destination.mkdir(parents=True, exist_ok=True)
            archive.extractall(destination)
    except Exception:
        raise InstallError("INTEGRITY_FAILED") from None
    return destination
