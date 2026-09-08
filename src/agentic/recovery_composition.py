"""Governed single-route clients and passive historical capability evidence."""

import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import select

from src.adapters.llm.execution import ProviderExecutionPolicyV1
from src.adapters.llm.mimo import MimoClient
from src.adapters.llm.routes import load_mimo_authority
from src.adapters.llm.teamorouter import TeamoRouterClient
from src.agentic.recovery import AdaptiveRecovery
from src.agentic.research_output_artifacts import (
    ResearchAgentOutputArtifactError,
    ResearchAgentOutputArtifactStore,
)
from src.application.persistence import ResearchRunAggregateRow
from src.domain.agent_output import (
    ResearchAgentOutputRecord,
    RiskResearchAgentStructuredOutput,
    StandardResearchAgentStructuredOutput,
)
from src.domain.recovery import Candidate, Capability, Health
from src.infrastructure.database.recovery import RecoveryEvidenceStore
from src.phase4_product.hashing import canonical_json_sha256 as digest


async def build_adaptive_recovery(settings, sessions, *, forbidden_values=()):
    # Isolated route attempts own no hidden fallback. Existing planner/code-builder
    # clients and the configured initial Specialist route are unchanged.
    policy = ProviderExecutionPolicyV1(
        max_attempts=1,
        bounded_backoff_seconds=(),
        read_timeout_seconds=60,
        overall_workload_deadline_seconds=90,
    )
    clients, routes = {}, {}
    if settings.vfa_credential_mode == "evaluator":
        from src.evaluator.client import EvaluatorGatewayLLM, active_session

        session = active_session()
        # Preserve existing supervisor candidate priority, independent of wire order.
        for route in ("teamorouter-sol", "teamorouter-luna", "teamorouter-terra", "mimo-direct"):
            if route not in session.metadata["routes"]:
                continue
            config = session.metadata["routes"][route]
            clients[route] = EvaluatorGatewayLLM(session, route, policy=policy)
            routes[route] = Candidate(
                route=route,
                provider=config["provider"],
                model=config["model"],
                authority_exists=True,
            )
    else:
        for route, model in (
            ("teamorouter-sol", settings.llm.primary_model),
            ("teamorouter-luna", settings.llm.fallback_model),
            ("teamorouter-terra", "gpt-5.6-terra"),
        ):
            config = settings.llm.model_copy(
                update={"primary_model": model, "fallback_model": model}
            )
            client = TeamoRouterClient(config, execution_policy=policy)
            client.route_ids = {model: route}
            clients[route] = client
            routes[route] = Candidate(
                route=route,
                provider="teamorouter",
                model=model,
                authority_exists=bool(config.api_key and config.api_key.get_secret_value()),
            )
        try:
            config = load_mimo_authority(settings=settings)
            client = MimoClient(config, execution_policy=policy)
            client.route_ids = {config.primary_model: "mimo-direct"}
            clients["mimo-direct"] = client
            routes["mimo-direct"] = Candidate(
                route="mimo-direct",
                provider="mimo",
                model=config.primary_model,
                authority_exists=True,
            )
        except ValueError:
            routes["mimo-direct"] = Candidate(
                route="mimo-direct", provider="mimo", model="mimo-v2.5", authority_exists=False
            )
    # No historical attempt backfill. Read-only local revalidation of already
    # accepted output is passive evidence, scoped to current schema + exact model.
    capabilities = {}
    certification_refs = {}
    health = {}
    artifact_store = ResearchAgentOutputArtifactStore(
        Path(settings.artifact_root) / "phase4-agent-outputs", forbidden_values=forbidden_values
    )
    async with sessions() as session:
        rows = list(await session.scalars(select(ResearchRunAggregateRow)))
    for row in sorted(rows, key=lambda row: row.updated_at):
        tasks = {
            t["task_id"]: t
            for t in row.payload.get("runtime", {}).get("actual_graph", {}).get("tasks", [])
        }
        for output in row.payload.get("artifacts", {}).get("agent_outputs", []):
            task = tasks.get(output.get("task_id"))
            if not task or output.get("actor") != task.get("assigned_agent"):
                continue
            if output.get("run_id") != row.run_id or task.get("run_id") != row.run_id:
                continue
            matched = next(
                (
                    key
                    for key, c in routes.items()
                    if c.provider == output.get("provider")
                    and c.model == output.get("actual_model")
                ),
                None,
            )
            if matched is None:
                continue
            try:
                retained = ResearchAgentOutputRecord.model_validate(output)
                artifact = json.loads(artifact_store.read_verified(retained))
                if artifact.get("structured_output") != output.get("structured_output") or any(
                    artifact.get(key) != output.get(key)
                    for key in ("run_id", "task_id", "actor", "provider", "actual_model", "status")
                ):
                    continue
            except (ValidationError, ResearchAgentOutputArtifactError, ValueError):
                continue
            if (datetime.now(UTC) - retained.created_at).total_seconds() < 86400:
                if retained.status == "SUCCESS":
                    health[matched] = Health.HEALTHY
                elif retained.failure_code in {
                    "read_timeout",
                    "provider_unavailable",
                    "remote_protocol_error",
                }:
                    health[matched] = Health.DEGRADED
            if retained.status != "SUCCESS":
                continue
            if retained.execution_outcome == "MODEL_EXECUTION_SUBSTITUTED":
                # Restart must not turn an observed substituted success into
                # capability certification; independent exact evidence is required.
                continue
            schema = (
                RiskResearchAgentStructuredOutput
                if task["task_type"] == "risk_analysis"
                else StandardResearchAgentStructuredOutput
            )
            try:
                parsed = schema.model_validate(output.get("structured_output"))
            except ValidationError:
                continue
            if any(secret in parsed.model_dump_json() for secret in forbidden_values if secret):
                continue
            key = (
                task["task_type"],
                matched,
                output["actual_model"],
                digest(schema.model_json_schema()),
            )
            capabilities[key] = Capability.VERIFIED
            certification_refs[key] = (output["output_id"], output["artifact_sha256"])
    return AdaptiveRecovery(
        routes,
        clients,
        RecoveryEvidenceStore(sessions),
        capabilities=capabilities,
        certification_refs=certification_refs,
        initial_health=health,
        forbidden_values=forbidden_values,
    )
