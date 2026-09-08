"""Owner-local durable verifier store. Atomic quota reservation before dispatch."""

import hashlib
import os
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager

from src.evaluator.contracts import CredentialPolicy, EvaluationAuthorizationError


class CredentialStore:
    def __init__(self, path, *, clock=time.time):
        self.path, self.clock = str(path), clock
        with self.connection() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS credentials (
              id TEXT PRIMARY KEY, verifier TEXT UNIQUE NOT NULL, policy TEXT NOT NULL,
              revoked INTEGER NOT NULL DEFAULT 0, llm INTEGER NOT NULL DEFAULT 0,
              data INTEGER NOT NULL DEFAULT 0, window INTEGER NOT NULL DEFAULT 0,
              rate_count INTEGER NOT NULL DEFAULT 0
            );
            """)
        if os.name != "nt":
            os.chmod(self.path, 0o600)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def issue(self, policy: CredentialPolicy):
        if policy.expires_at <= self.clock():
            raise EvaluationAuthorizationError("EVALUATION_CREDENTIAL_EXPIRED")
        token = "vfa_" + secrets.token_urlsafe(32)
        cid = str(uuid.uuid4())
        with self.connection() as db:
            db.execute(
                "INSERT INTO credentials (id,verifier,policy) VALUES (?,?,?)",
                (cid, hashlib.sha256(token.encode()).hexdigest(), policy.model_dump_json()),
            )
        return cid, token

    def revoke(self, cid):
        with self.connection() as db:
            if db.execute("UPDATE credentials SET revoked=1 WHERE id=?", (cid,)).rowcount != 1:
                raise EvaluationAuthorizationError("EVALUATION_CREDENTIAL_INVALID")

    def authorize(self, token, *, kind=None, route=None):
        if not isinstance(token, str) or len(token) != 47 or not token.startswith("vfa_"):
            raise EvaluationAuthorizationError("EVALUATION_CREDENTIAL_INVALID")
        with self.connection() as db:
            # SQLite serializes reservations across threads/processes; no quota overdraw.
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM credentials WHERE verifier=?",
                (hashlib.sha256(token.encode()).hexdigest(),),
            ).fetchone()
            if row is None:
                raise EvaluationAuthorizationError("EVALUATION_CREDENTIAL_INVALID")
            if row["revoked"]:
                raise EvaluationAuthorizationError("EVALUATION_CREDENTIAL_REVOKED")
            policy = CredentialPolicy.model_validate_json(row["policy"])
            now = int(self.clock())
            if policy.expires_at <= now:
                raise EvaluationAuthorizationError("EVALUATION_CREDENTIAL_EXPIRED")
            if kind not in {None, "llm", "data"}:
                raise EvaluationAuthorizationError("EVALUATION_REQUEST_INVALID")
            if (
                kind == "llm"
                and route not in policy.routes
                or kind == "data"
                and not policy.financial_data_allowed
            ):
                raise EvaluationAuthorizationError("EVALUATION_ROUTE_NOT_ALLOWED")
            counts = {"llm": row["llm"], "data": row["data"]}
            if kind is not None:
                maximum = policy.max_llm_requests if kind == "llm" else policy.max_data_requests
                if counts[kind] >= maximum:
                    raise EvaluationAuthorizationError("EVALUATION_BUDGET_EXHAUSTED")
                window = now // 60
                rate = row["rate_count"] if row["window"] == window else 0
                if rate >= policy.requests_per_minute:
                    raise EvaluationAuthorizationError("EVALUATION_RATE_LIMITED")
                counts[kind] += 1
                db.execute(
                    "UPDATE credentials SET llm=?,data=?,window=?,rate_count=? WHERE id=?",
                    (counts["llm"], counts["data"], window, rate + 1, row["id"]),
                )
            return {
                "credential_id": row["id"],
                "expires_at": policy.expires_at,
                "allowed_routes": sorted(policy.routes),
                "financial_data_allowed": policy.financial_data_allowed,
                "llm_remaining": policy.max_llm_requests - counts["llm"],
                "data_remaining": policy.max_data_requests - counts["data"],
                "cost": "NOT_OBSERVED",
                "gateway_version": "1",
                "credential_valid": True,
            }
