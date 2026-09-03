"""Bounded, secret-safe A/B/C probe for the TeamoRouter Scheme route."""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import date
from pathlib import Path
from typing import Any, Literal

import httpx
from pydantic import BaseModel

from src.adapters.llm import LLMMessage, TeamoRouterClient
from src.agentic.llm_integration import (
    SchemeProposal,
    _scheme_messages,
    _validate_scheme_proposal,
)
from src.domain.research_goal import ResearchGoal
from src.domain.research_object import ResearchObject
from src.infrastructure.config.settings import Settings


class _SimpleAnswer(BaseModel):
    value: Literal["ok"]


def _safe_model(value: object, allowed: set[str]) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return value if value in allowed else "provider_reported_other"


def _safe_attempts(error: Exception, allowed: set[str]) -> list[str]:
    values = getattr(error, "attempted_models", ())
    return [value for value in values if isinstance(value, str) and value in allowed]


def _safe_failure(stage: str, error: Exception, allowed: set[str]) -> dict[str, Any]:
    classification = getattr(error, "failure_classification", None)
    value = classification.value if hasattr(classification, "value") else classification
    if value is None and isinstance(error, ValueError):
        value = "semantic_validation_failed"
    return {
        "stage": stage,
        "classification": value if isinstance(value, str) and value else type(error).__name__,
        "attempted_models": _safe_attempts(error, allowed),
        "actual_model": None,
        "validation": "failed",
    }


async def _plain_probe(
    *,
    http: httpx.AsyncClient,
    settings,
) -> dict[str, Any]:
    allowed = {settings.primary_model, settings.fallback_model}
    route = list(dict.fromkeys((settings.primary_model, settings.fallback_model)))
    attempted: list[str] = []
    url = f"{settings.base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.api_key.get_secret_value()}",
        "Content-Type": "application/json",
    }
    for model in route:
        attempted.append(model)
        try:
            response = await http.post(
                url,
                headers=headers,
                json={
                    "model": model,
                    "messages": [
                        {"role": "user", "content": "Reply with the single word ok."}
                    ],
                },
            )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            if model != route[-1]:
                continue
            return {
                "stage": "A_plain_model",
                "classification": "retryable_transport_failure",
                "transport_error_type": type(exc).__name__,
                "attempted_models": attempted,
                "actual_model": None,
                "validation": "failed",
            }
        if response.status_code in {408, 429} or response.status_code >= 500:
            if model != route[-1]:
                continue
            classification = "retryable_http_failure"
        elif response.is_error:
            classification = "request_rejected"
        else:
            try:
                body = response.json()
                content = body["choices"][0]["message"]["content"]
                valid = isinstance(content, (str, dict, list))
                actual_model = _safe_model(body.get("model"), allowed) or model
            except (ValueError, TypeError, KeyError, IndexError):
                valid = False
                actual_model = None
            classification = "pass" if valid else "response_shape_invalid"
        return {
            "stage": "A_plain_model",
            "classification": classification,
            "http_status": response.status_code,
            "attempted_models": attempted,
            "actual_model": actual_model if classification == "pass" else None,
            "validation": "pass" if classification == "pass" else "failed",
        }
    raise AssertionError("model route must not be empty")


async def _run(timeout_seconds: float) -> dict[str, Any]:
    settings = Settings().llm
    if not settings.enabled:
        return {
            "preflight": "preflight_failure",
            "stages": [],
            "reason": "credential_not_configured",
        }
    allowed = {settings.primary_model, settings.fallback_model}
    results: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=timeout_seconds) as http:
        plain = await _plain_probe(http=http, settings=settings)
        results.append(plain)
        if plain["classification"] != "pass":
            return {"preflight": "pass", "stages": results}

        client = TeamoRouterClient(settings, client=http, timeout_seconds=timeout_seconds)
        try:
            simple = await client.complete_structured(
                messages=[LLMMessage(role="user", content='Return {"value":"ok"}.')],
                response_model=_SimpleAnswer,
                schema_name="simple_answer_v1",
            )
            results.append(
                {
                    "stage": "B_simple_schema",
                    "classification": "pass",
                    "attempted_models": list(simple.attempted_models),
                    "actual_model": _safe_model(simple.actual_model, allowed),
                    "validation": "pass",
                }
            )
        except Exception as exc:
            results.append(_safe_failure("B_simple_schema", exc, allowed))
            return {"preflight": "pass", "stages": results}

        research_object = ResearchObject(
            object_id="OBJ-PROBE-NVDA",
            symbol="NVDA",
            company_name="NVIDIA Corporation",
            exchange="NASDAQ",
        )
        goal = ResearchGoal(
            goal_id="GOAL-PROBE-SCHEME",
            research_object_id=research_object.object_id,
            goal_text="Evaluate fundamentals and risks using accepted evidence",
            as_of=date(2026, 9, 4),
        )
        try:
            scheme = await client.complete_structured(
                messages=_scheme_messages(research_object, goal),
                response_model=SchemeProposal,
                schema_name="research_scheme_proposal_v2",
            )
            _validate_scheme_proposal(scheme.output)
            results.append(
                {
                    "stage": "C_research_scheme_schema",
                    "classification": "pass",
                    "attempted_models": list(scheme.attempted_models),
                    "actual_model": _safe_model(scheme.actual_model, allowed),
                    "validation": "schema_and_semantic_pass",
                }
            )
        except Exception as exc:
            results.append(_safe_failure("C_research_scheme_schema", exc, allowed))
    return {"preflight": "pass", "stages": results}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/phase2_1/scheme_route/probe_result.json"),
    )
    args = parser.parse_args()
    if not 0 < args.timeout_seconds <= 30:
        raise SystemExit("timeout must be between 0 and 30 seconds")
    result = asyncio.run(_run(args.timeout_seconds))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
