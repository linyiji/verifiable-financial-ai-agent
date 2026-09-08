"""Serve with uvicorn; no public issuance/revocation route."""

import os

from src.evaluator.gateway import OwnerUpstreams, create_gateway
from src.evaluator.store import CredentialStore
from src.infrastructure.config.settings import Settings


def create_app():
    path = os.environ.get("VFA_GATEWAY_STORE")
    if not path:
        raise RuntimeError("VFA_GATEWAY_STORE must identify an Owner-private durable database")
    settings = Settings()
    return create_gateway(CredentialStore(path), OwnerUpstreams(settings))
