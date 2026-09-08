"""Owner administrative console: issue encrypted bundle or revoke by public ID."""

import argparse
import os
import time
from pathlib import Path

from src.evaluator.bundle import encrypt_bundle, secure_prompt
from src.evaluator.contracts import CredentialPolicy
from src.evaluator.store import CredentialStore


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", required=True, help="Owner-private gateway SQLite path")
    sub = parser.add_subparsers(dest="command", required=True)
    issue = sub.add_parser("issue")
    issue.add_argument("--gateway-url", required=True)
    issue.add_argument("--output", required=True)
    issue.add_argument("--days", type=int, default=7)
    issue.add_argument(
        "--routes", nargs="+", default=["teamorouter-sol", "teamorouter-luna", "mimo-direct"]
    )
    issue.add_argument("--financial-data", action="store_true")
    issue.add_argument("--llm-requests", type=int, default=100)
    issue.add_argument("--data-requests", type=int, default=500)
    issue.add_argument("--requests-per-minute", type=int, default=30)
    issue.add_argument("--allow-loopback", action="store_true")
    revoke = sub.add_parser("revoke")
    revoke.add_argument("--credential-id", required=True)
    args = parser.parse_args()
    cid = None
    store = None
    try:
        store = CredentialStore(Path(args.store).expanduser())
        if args.command == "revoke":
            store.revoke(args.credential_id)
            print("Credential revoked.")
            return
        if not 1 <= args.days <= 30:
            raise ValueError()
        output = Path(args.output).expanduser()
        if output.suffix != ".vfaeval":
            raise ValueError()
        password = secure_prompt("Bundle passphrase (12+ characters, distribute out of band): ")
        if password != secure_prompt("Confirm passphrase: "):
            raise ValueError()
        policy = CredentialPolicy(
            routes=set(args.routes),
            financial_data_allowed=args.financial_data,
            expires_at=int(time.time()) + args.days * 86400,
            max_llm_requests=args.llm_requests,
            max_data_requests=args.data_requests,
            requests_per_minute=args.requests_per_minute,
        )
        cid, token = store.issue(policy)
        bundle = encrypt_bundle(
            token,
            password,
            url=args.gateway_url,
            credential_id=cid,
            allow_loopback=args.allow_loopback,
        )
        # Exclusive create; never overwrite a previous investor bundle.
        descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(bundle)
        del token, password
        print("Encrypted bundle issued. Credential ID: " + cid)
    except Exception:
        if store is not None and cid is not None:
            store.revoke(cid)
        print("Credential administration failed; no token was displayed.")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
