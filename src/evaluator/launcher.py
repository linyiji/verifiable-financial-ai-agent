"""Session-only launch on macOS, native Windows, or inside WSL2."""

import argparse
import asyncio

from src.evaluator.bundle import decrypt_bundle, read_bundle, secure_prompt
from src.evaluator.client import GatewaySession, activate, clear_session
from src.evaluator.contracts import EvaluationAuthorizationError
from src.infrastructure.config.settings import Settings


async def prepare_session(
    bundle_path, password, *, allow_loopback=False, http=None, expected_url=None
):
    clear_session()
    url, token, cid = decrypt_bundle(
        read_bundle(bundle_path), password, allow_loopback=allow_loopback
    )
    if expected_url and expected_url.rstrip("/") != url:
        raise EvaluationAuthorizationError("EVALUATION_REQUEST_INVALID")
    session = GatewaySession(url, token, allow_loopback=allow_loopback, http=http)
    metadata = await session.readiness()
    if metadata.get("credential_id") != cid:
        raise EvaluationAuthorizationError()
    activate(session)
    return session


def print_readiness(metadata):
    print("Verifiable Financial Agent — Evaluator")
    print("Credential ........ PASS")
    print("Gateway ........... PASS (CONFIGURED, not live-provider verified)")
    print(
        "Financial Data .... " + ("ENABLED" if metadata["financial_data_allowed"] else "DISABLED")
    )
    for route in metadata["routes"]:
        print(route + " .. ALLOWED")
    print("Expires ........... " + str(metadata["expires_at"]))
    print("LLM quota ......... " + str(metadata["llm_remaining"]))
    print("Data quota ........ " + str(metadata["data_remaining"]))
    # Scope can intentionally be restricted. Do not overclaim full workflow readiness.
    complete = {"teamorouter-sol", "mimo-direct"} <= set(metadata["routes"]) and metadata[
        "financial_data_allowed"
    ]
    funded = metadata["llm_remaining"] > 0 and metadata["data_remaining"] > 0
    print(
        "READY FOR REAL RESEARCH"
        if complete and funded
        else "READY — RESTRICTED SCOPE OR EXHAUSTED QUOTA"
    )
    print("No upstream provider/data calls were made by readiness.")


def main():
    parser = argparse.ArgumentParser(
        description="Open an Owner-issued encrypted evaluator credential."
    )
    parser.add_argument("--bundle", required=True)
    parser.add_argument(
        "--allow-loopback", action="store_true", help="Local fake gateway development only"
    )
    parser.add_argument("--readiness-only", action="store_true")
    args = parser.parse_args()
    try:
        settings = Settings()
        if settings.vfa_credential_mode != "evaluator":
            raise EvaluationAuthorizationError("EVALUATION_REQUEST_INVALID")
        password = secure_prompt("Evaluation credential passphrase: ")
        session = asyncio.run(
            prepare_session(
                args.bundle,
                password,
                allow_loopback=args.allow_loopback,
                expected_url=settings.vfa_evaluator_gateway_url,
            )
        )
        del password
        print_readiness(session.metadata)
        if not args.readiness_only:
            import uvicorn

            import apps.api.main as product

            # All credentials remain in this process. No secret env/argv or reload worker.
            product.get_settings = lambda: settings
            uvicorn.run(product.create_app(), host="127.0.0.1", port=8010, access_log=False)
    except Exception:
        print(
            "Evaluation startup failed. Check mode, bundle/passphrase, gateway and authorization."
        )
        raise SystemExit(1) from None
    finally:
        clear_session()


if __name__ == "__main__":
    main()
