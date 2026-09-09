import json
import os
from pathlib import Path

STAGES = (
    "SYSTEM_CHECK",
    "RUNTIME_CHECK",
            "RUNTIME_INSTALL_OR_GUIDE",
            "RUNTIME_DEPENDENCY_CHECK",
    "RELEASE_RESOLUTION",
    "DOWNLOAD",
    "INTEGRITY_VERIFY",
    "PRODUCT_INSTALL",
    "LOCAL_STORAGE_INIT",
    "DATABASE_INIT",
    "MIGRATION",
    "CREDENTIAL_DISCOVERY",
    "CREDENTIAL_UNLOCK",
    "GATEWAY_READINESS",
    "DIRECT_REGISTRY_READINESS",
    "SERVICE_START",
    "HEALTH_CHECK",
    "OPEN_BROWSER",
    "READY",
)


def private_write(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(content)
    os.replace(temporary, path)


class State:
    """Only allowlisted metadata is persisted. Stages are observations, never skipped checks."""

    def __init__(self, root):
        self.root = Path(root)
        self.path = self.root / "state.json"
        self.data = json.loads(self.path.read_text()) if self.path.exists() else {}

    def save(self, **values):
        assert set(values) <= {
            "stage",
            "version",
            "image",
            "project",
            "credential_name",
            "ready",
            "error",
            "full_proof",
        }
        self.data.update(values)
        private_write(self.path, json.dumps(self.data, indent=2))

    def stage(self, name):
        assert name in STAGES
        self.save(stage=name, ready=False)
        print(
            f"[{STAGES.index(name) + 1}/{len(STAGES)}] {name.replace('_', ' ').title()}", flush=True
        )
