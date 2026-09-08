"""Container entry points. The accepted evaluator transport and product own authorization."""

import asyncio
import json
import os
import socket
import sys
import time
from pathlib import Path

from pydantic import SecretStr

from src.evaluator.client import GatewaySession, activate
from src.infrastructure.config.settings import Settings

SOCKET = "/run/vfa/credential.sock"


def settings():
    password = Path("/run/secrets/db_password").read_text().strip()
    return Settings(
        _env_file=None,
        database_url=f"postgresql+asyncpg://vfa:{password}@postgres:5432/vfa",
        vfa_credential_mode="evaluator",
        artifact_root="/data/artifacts",
        workspace_root="/data/workspaces",
    )


def main():
    mode = sys.argv[1]
    try:
        if mode == "migrate":
            from src.infrastructure.database.migrations import upgrade_postgresql_database

            upgrade_postgresql_database(settings().database)
            return
        if mode == "handoff":
            payload = sys.stdin.buffer.read(8193)
            if len(payload) > 8192:
                raise ValueError()
            for _attempt in range(60):
                try:
                    with socket.socket(socket.AF_UNIX) as connection:
                        connection.connect(SOCKET)
                        connection.sendall(payload)
                        connection.shutdown(socket.SHUT_WR)
                        if connection.recv(16) != b"READY":
                            raise ValueError()
                    return
                except FileNotFoundError:
                    time.sleep(0.5)
            raise ValueError()
        if mode != "api":
            raise ValueError()
        os.makedirs("/run/vfa", exist_ok=True)
        with socket.socket(socket.AF_UNIX) as listener:
            listener.bind(SOCKET)
            os.chmod(SOCKET, 0o600)
            listener.listen(1)
            listener.settimeout(180)
            with listener.accept()[0] as connection:
                connection.settimeout(30)
                chunks = bytearray()
                while chunk := connection.recv(4096):
                    chunks.extend(chunk)
                    if len(chunks) > 8192:
                        raise ValueError()
                authority = json.loads(chunks)
                session = GatewaySession(authority["url"], SecretStr(authority["token"]))
                asyncio.run(session.readiness())
                activate(session)
                del authority, chunks
                connection.sendall(b"READY")
        os.unlink(SOCKET)
        import uvicorn

        import apps.api.main as product

        config = settings()
        product.get_settings = lambda: config
        uvicorn.run(
            product.create_app(), host="0.0.0.0", port=8010, access_log=False, log_level="critical"
        )
    except Exception:
        # No exception text, URL/password, token or request body enters container logs.
        print("VFA service could not start. Run vfa doctor.", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
