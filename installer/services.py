import hashlib
import json
import secrets
import subprocess
import time
from pathlib import Path

from installer.errors import InstallError
from installer.state import private_write


class DockerServices:
    """All Docker authority stays on the evaluator host. Never put bearer/DB secrets in argv."""

    def __init__(self, root, host_root, image, project="vfa-evaluator", run=subprocess.run):
        self.root, self.host_root = Path(root), host_root.rstrip("/")
        self.image, self.run = image, run
        self.project = project + "-" + hashlib.sha256(host_root.encode()).hexdigest()[:10]
        self.compose = self.root / "runtime/compose.json"

    def command(self, args, code="INSTALLATION_FAILED", payload=None, timeout=900):
        try:
            result = self.run(args, input=payload, capture_output=True, timeout=timeout)
            if result.returncode:
                raise InstallError(code)
            return result.stdout.decode().strip()
        except (OSError, subprocess.TimeoutExpired):
            raise InstallError(code) from None

    def dc(self, *args, code="INSTALLATION_FAILED", payload=None, timeout=900):
        return self.command(
            ["docker", "compose", "-p", self.project, "-f", str(self.compose), *args],
            code,
            payload,
            timeout,
        )

    def check(self):
        self.command(["docker", "info"], "DOCKER_NOT_RUNNING")
        self.command(["docker", "compose", "version"], "DOCKER_NOT_INSTALLED")

    def storage(self):
        password = self.root / "runtime/db.password"
        if not password.exists():
            private_write(password, secrets.token_urlsafe(32))
        for name in ("artifacts", "workspaces", "logs"):
            (self.root / "runtime" / name).mkdir(parents=True, exist_ok=True, mode=0o700)
        # No secret value appears in Compose or the Docker environment.
        mounts = [
            f"{self.host_root}/runtime/db.password:/run/secrets/db_password:ro",
            f"{self.host_root}/runtime/artifacts:/data/artifacts",
            f"{self.host_root}/runtime/workspaces:/data/workspaces",
        ]
        config = {
            "services": {
                "postgres": {
                    "image": (
                        "postgres:16@sha256:"
                        "f1c3376c26f2609ab9f29f71f824103fe2fcd8ee0346485cb6122a4f93df6f94"
                    ),
                    "environment": {
                        "POSTGRES_DB": "vfa",
                        "POSTGRES_USER": "vfa",
                        "POSTGRES_PASSWORD_FILE": "/run/secrets/db_password",
                    },
                    "volumes": ["research:/var/lib/postgresql/data", mounts[0]],
                    "healthcheck": {
                        "test": ["CMD-SHELL", "pg_isready -U vfa -d vfa"],
                        "interval": "2s",
                        "timeout": "3s",
                        "retries": 40,
                    },
                },
                "api": {
                    "image": self.image,
                    "command": ["python", "-m", "installer.runtime", "api"],
                    "volumes": mounts,
                    "tmpfs": ["/run/vfa:mode=0700"],
                    "ports": ["127.0.0.1:8010:8010"],
                    "depends_on": {"postgres": {"condition": "service_healthy"}},
                },
                "web": {
                    "image": self.image,
                    "command": ["python", "-m", "installer.web"],
                    "ports": ["127.0.0.1:4173:4173"],
                },
            },
            "volumes": {"research": {}},
        }
        private_write(self.compose, json.dumps(config))

    def database(self):
        self.dc(
            "up", "-d", "--wait", "--wait-timeout", "120", "postgres", code="DATABASE_START_FAILED"
        )

    def migrate(self):
        self.dc(
            "run",
            "--rm",
            "--no-deps",
            "-T",
            "api",
            "python",
            "-m",
            "installer.runtime",
            "migrate",
            code="MIGRATION_FAILED",
        )

    def start(self, session):
        # Stop only this install's API/web; persistent database remains intact.
        self.dc("stop", "api", "web")
        self.dc("up", "-d", "--force-recreate", "api", "web")
        payload = json.dumps(
            {"url": session.url, "token": session._token.get_secret_value()}
        ).encode()
        # Secret travels over stdin into a local private Unix socket, never a file/env/argv.
        self.dc(
            "exec", "-T", "api", "python", "-m", "installer.runtime", "handoff", payload=payload
        )

    def health(self, timeout=90):
        deadline = time.monotonic() + timeout
        probe = "import urllib.request; urllib.request.urlopen('http://127.0.0.1:{port}{path}',timeout=2).read(128)"
        while time.monotonic() < deadline:
            try:
                for service, port, path in (("api", 8010, "/health"), ("web", 4173, "/")):
                    self.dc(
                        "exec",
                        "-T",
                        service,
                        "python",
                        "-c",
                        probe.format(port=port, path=path),
                        code="HEALTH_TIMEOUT",
                        timeout=max(0.1, min(5, deadline - time.monotonic())),
                    )
                return
            except InstallError:
                time.sleep(1)
        raise InstallError("HEALTH_TIMEOUT")

    def ports(self):
        own = self.dc("ps", "-q") if self.compose.exists() else ""
        for port in (8010, 4173):
            ids = self.command(["docker", "ps", "-q", "--no-trunc", "--filter", f"publish={port}"])
            if ids and any(cid not in own for cid in ids.splitlines()):
                raise InstallError(f"PORT_{port}_IN_USE")
            # Non-Docker listeners are checked through Docker Desktop's host bridge.
            if not ids:
                import socket

                try:
                    with socket.create_connection(("host.docker.internal", port), timeout=1):
                        raise InstallError(f"PORT_{port}_IN_USE")
                except OSError:
                    pass

    def stop(self):
        if self.compose.exists():
            self.dc("stop")

    def status(self):
        if not self.compose.exists():
            return "Not installed. Run the installer."
        return self.dc("ps", "--format", "{{.Service}}: {{.State}}")

    def install(self, directory, version):
        self.command(
            [
                "docker",
                "build",
                "-f",
                str(Path(directory) / "installer/Dockerfile"),
                "-t",
                self.image,
                str(directory),
            ]
        )
