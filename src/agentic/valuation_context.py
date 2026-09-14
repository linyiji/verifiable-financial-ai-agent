"""Bounded interaction inside the existing valuation Agent/Executor; no recovery owner."""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import replace
from time import monotonic
from typing import Literal

from pydantic import Field, model_validator

from src.adapters.llm.mimo import MimoClient
from src.adapters.llm.teamorouter import TeamoRouterClient, context_call_observer
from src.application.research_context import POLICY, ResearchContextPackage, encoded
from src.domain.agent_output import StandardResearchAgentStructuredOutput
from src.domain.node_binding import BindingDenied, BindingValue, canonical_value, digest
from src.domain.owner_policy import TASK_CANDIDATES, TASK_POLICIES
from src.domain.recovery import Candidate


class RetrievalRequest(BindingValue):
    request_id: str
    context_id: str
    context_revision: Literal[1]
    consumer_role: Literal["valuation_analyst"]
    need_type: Literal["EVIDENCE", "CALCULATION", "MEMORY_ITEM"]
    subject_refs: tuple[str, ...] = Field(min_length=1, max_length=8)
    reason: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def exact(self):
        if len(set(self.subject_refs)) != len(self.subject_refs):
            raise ValueError("duplicate retrieval subjects")
        expected = digest(self.model_dump(exclude={"request_id"}), "retrieval-request/v1")
        if not self.request_id:
            object.__setattr__(self, "request_id", expected)
        if self.request_id != expected:
            raise ValueError("retrieval request identity")
        if len(encoded(self)) > 2048:
            raise ValueError("retrieval request bytes")
        return self


class ValuationTurn(BindingValue):
    kind: Literal["FINAL", "RETRIEVE"]
    answer: StandardResearchAgentStructuredOutput | None
    request: RetrievalRequest | None

    @model_validator(mode="after")
    def union(self):
        if (self.kind == "FINAL" and (self.answer is None or self.request is not None)) or (
            self.kind == "RETRIEVE" and (self.request is None or self.answer is not None)
        ):
            raise ValueError("exact FINAL/RETRIEVE branch required")
        return self


class CallReceipt(BindingValue):
    schema_version: Literal["vefin-context-model-call/v1"] = "vefin-context-model-call/v1"
    interaction_id: str
    turn_number: Literal[1, 2]
    call_id: str
    pre_call_B_ref: str | None = None
    context_id: str
    context_revision: Literal[1, 2]
    request_manifest_digest: str | None = None
    requested_model: str
    requested_reasoning_profile: str | None = None
    route_ref: str
    requested_route: str = "UNKNOWN"
    resolved_route: str = "UNKNOWN"
    configuration_snapshot: dict | None = None
    resolved_model: str = "UNKNOWN"
    resolved_provider: str = "UNKNOWN"
    observed_provider: str = "UNKNOWN"
    observed_model: str = "UNKNOWN"
    provider_identity_source: str = "UNKNOWN"
    model_identity_source: str = "UNKNOWN"
    observed_reasoning: str = "UNKNOWN"
    response_request_id: str | None = None
    fallback_used: bool | Literal["UNKNOWN"] = "UNKNOWN"
    fallback_from: None = None
    fallback_to: None = None
    fallback_reason: str = "NO_DISPATCH_EVIDENCE"
    fallback_policy_ref: str = POLICY
    phase: Literal["RESERVED", "DISPATCHED", "RESPONSE", "FAILED", "RESULT_UNKNOWN"] = "RESERVED"
    input_tokens: int | None = None
    output_tokens: int | None = None
    usage_coverage: str = "UNKNOWN"
    cost: Literal["UNKNOWN"] = "UNKNOWN"
    elapsed_ms: int = 0
    outcome_digest: str | None = None
    diagnostic_code: str | None = None
    client_physical_dispatch_count: int = 0
    provider_internal_fanout: Literal["UNKNOWN"] = "UNKNOWN"


def validate_composition(agent, task):
    from src.agentic.research_agent import LLMResearchAgent

    if (
        type(agent) is not LLMResearchAgent
        or (task.task_type, task.assigned_agent, task.skill_id)
        != ("valuation_analysis", "valuation_analyst", "valuation_analysis_v1")
        or agent.agent_id != "valuation_analyst"
        or task.task_type not in agent.supported_task_types
    ):
        raise BindingDenied("CONTEXT_IDENTITY_UNAVAILABLE", "consumer")
    if agent._recovery is not None:
        raise BindingDenied("WP03_UNSUPPORTED_RECOVERY_COMPOSITION", "recovery is configured")
    client = agent._provider
    if type(client) not in (TeamoRouterClient, MimoClient) or client._client is not None:
        raise BindingDenied("WP03_UNSUPPORTED_CLIENT_COMPOSITION", "owned direct client required")
    if (
        client._settings.fallback_model != client.model_name
        or client.execution_policy.max_attempts != 1
    ):
        raise BindingDenied("WP03_UNSUPPORTED_CLIENT_COMPOSITION", "retry/fallback")
    route = client.route_ids.get(client.model_name)
    if route not in TASK_CANDIDATES[task.task_type] or client.task_profile != task.task_type:
        raise BindingDenied("MODEL_IDENTITY_OUT_OF_POLICY", "task route")
    Candidate(
        route=route,
        provider=client.provider_name,
        model=client.model_name,
        authority_exists=client._settings.enabled,
    )
    return digest(configuration_snapshot(client, task), "wp03-route-config/v1")


def configuration_snapshot(client, task):
    return canonical_value(
        {
            "policy": POLICY,
            "candidate_authority_snapshot": TASK_POLICIES[task.task_type],
            "task_profile": task.task_type,
            "route": client.route_ids[client.model_name],
            "provider": client.provider_name,
            "model": client.model_name,
            "fallback_allowed": False,
            "retry_allowed": False,
            "recovery_enabled": False,
            "transport": "OWNED_DIRECT_NO_RETRY_NO_REDIRECT",
            "endpoint_digest": digest(client._settings.base_url, "configured-endpoint/v1"),
            "execution_policy": {
                field: getattr(client.execution_policy, field)
                for field in client.execution_policy.__dataclass_fields__
            },
        }
    )


class ValuationInteraction:
    def __init__(self, agent, projector):
        self.agent, self.projector = agent, projector
        self.client = agent._provider
        self.started = monotonic()
        self.interaction_id = digest(projector.admission, "valuation-interaction/v1")
        self.turns = self.calls = self.rounds = self.logical_calls = 0
        self.receipts = []
        self.receipt_refs = []
        self.current = None
        self.wire_digest = None

    def limit(self):
        if monotonic() - self.started >= 180:
            raise BindingDenied("CONTEXT_BUDGET_EXHAUSTED", "interaction deadline")

    async def final_checkpoint(self):
        self.limit()
        async with asyncio.timeout(max(0, 180 - (monotonic() - self.started))):
            await self.projector.checkpoint()
        self.limit()

    async def prepare(self, client, payload):
        self.limit()
        if (
            client is not self.client
            or validate_composition(self.agent, self.projector.task) != self.projector.route_ref
        ):
            raise BindingDenied("MODEL_IDENTITY_OUT_OF_POLICY", "composition changed")
        if payload.get("model") != self.current.requested_model:
            raise BindingDenied("MODEL_IDENTITY_OUT_OF_POLICY", "wire model")
        if len(encoded(payload)) > 65536:
            raise BindingDenied("CONTEXT_TOO_LARGE", "wire payload")
        package = self.projector.package
        rebuilt = ResearchContextPackage.build(
            **package.model_dump(
                exclude={"context_id", "size_bytes", "created_at", "source_manifest_digest"}
            )
        )
        if (rebuilt.context_id, rebuilt.size_bytes, rebuilt.source_manifest_digest) != (
            package.context_id,
            package.size_bytes,
            package.source_manifest_digest,
        ):
            raise BindingDenied("CONTEXT_IDENTITY_UNAVAILABLE", "mutated context")
        await self.projector.checkpoint()
        self.wire_digest = digest(payload, "model-wire-payload/v1")
        binding = await self.projector.executor._bind_step(
            self.projector.task,
            f"wp03:valuation:context:{self.turns}",
            {
                "context_package": canonical_value(self.projector.package),
                "request_manifest_digest": self.wire_digest,
                "response_schema_digest": self.schema_digest,
                "configuration_snapshot": self.current.configuration_snapshot,
            },
        )
        self.current = self.current.model_copy(
            update={
                "pre_call_B_ref": binding.resolved_input_binding_id,
                "request_manifest_digest": self.wire_digest,
                "resolved_model": payload["model"],
                "resolved_provider": client.provider_name,
                "resolved_route": client.route_ids[payload["model"]],
            }
        )
        await self.projector.checkpoint()

    def dispatch(self, client, payload):
        self.limit()
        if (
            client is not self.client
            or self.current.pre_call_B_ref is None
            or self.current.client_physical_dispatch_count
            or self.calls >= 2
            or self.wire_digest != digest(payload, "model-wire-payload/v1")
            or validate_composition(self.agent, self.projector.task) != self.projector.route_ref
        ):
            raise BindingDenied("CONTEXT_BUDGET_EXHAUSTED", "physical dispatch denied")
        self.calls += 1
        self.current = self.current.model_copy(
            update={
                "phase": "DISPATCHED",
                "client_physical_dispatch_count": 1,
                "observed_provider": client.provider_name,
                "provider_identity_source": "CLIENT_DISPATCH",
                "fallback_used": False,
                "fallback_reason": "NO_FALLBACK_IN_WP03_V1",
            }
        )

    async def response(self, response):
        try:
            body = response.json()
        except (ValueError, TypeError):
            body = {}
        body = body if isinstance(body, dict) else {}
        model = body.get("model")
        usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
        counts = {
            name: usage.get(source)
            if type(usage.get(source)) is int and usage[source] >= 0
            else None
            for name, source in (
                ("input_tokens", "prompt_tokens"),
                ("output_tokens", "completion_tokens"),
            )
        }
        evidenced = isinstance(model, str) and bool(re.fullmatch(r"[A-Za-z0-9._/-]{1,128}", model))
        request_id = response.headers.get("x-request-id")
        if not isinstance(request_id, str) or not re.fullmatch(
            r"[A-Za-z0-9._-]{1,128}", request_id
        ):
            request_id = None
        self.current = self.current.model_copy(
            update={
                "phase": "RESPONSE",
                "observed_model": model if evidenced else "UNKNOWN",
                "model_identity_source": "PROVIDER_RESPONSE" if evidenced else "UNKNOWN",
                "response_request_id": request_id,
                **counts,
                "usage_coverage": "REPORTED"
                if all(v is not None for v in counts.values())
                else "PARTIAL_OR_UNKNOWN",
            }
        )

        await self.projector.checkpoint()
        self.limit()
        if self.turns == 2:
            try:
                content = body["choices"][0]["message"]["content"]
                decoded = json.loads(content) if isinstance(content, str) else content
            except (KeyError, IndexError, ValueError, TypeError):
                decoded = None
            if isinstance(decoded, dict) and decoded.get("kind") == "RETRIEVE":
                raise BindingDenied("RETRIEVAL_ROUND_BUDGET_EXHAUSTED")

    async def retrieve(self, request):
        if self.rounds:
            raise BindingDenied("RETRIEVAL_ROUND_BUDGET_EXHAUSTED")
        package = self.projector.package
        if (request.context_id, request.context_revision) != (
            package.context_id,
            package.context_revision,
        ):
            raise BindingDenied("CONTEXT_IDENTITY_UNAVAILABLE", "retrieval context")
        kinds = {
            "EVIDENCE": "EVIDENCE",
            "CALCULATION": "CALCULATION_CORE",
            "MEMORY_ITEM": "ResearchMemoryRepository",
        }
        await self.projector.checkpoint()
        sections = list(package.sections)
        for identity in request.subject_refs:
            item = self.projector.inventory.get(identity)
            if (
                item is None
                or item[0].owner != kinds[request.need_type]
                or identity in self.projector.rendered
            ):
                raise BindingDenied(
                    "CONTEXT_IDENTITY_UNAVAILABLE", "unknown/type/no-new-info retrieval"
                )
            # Owners were re-read at checkpoint. Historical content remains separately namespaced.
            sections.append(
                {"source_id": identity, "namespace": item[0].namespace, "content": item[1]}
            )
        self.rounds += 1
        values = package.model_dump(
            exclude={"context_id", "size_bytes", "created_at", "source_manifest_digest"}
        )
        history = self.projector.ref(
            "ValuationInteraction",
            request.request_id,
            "retrieval-request/v1",
            request.model_dump(exclude={"request_id"}),
            namespace="INTERACTION",
            reason="REQUESTED",
        )
        sections.append(
            {
                "source_id": request.request_id,
                "prior_context_id": package.context_id,
                "prior_turn_receipt_ref": self.receipt_refs[-1],
                "request": canonical_value(request),
            }
        )
        for key in (
            "evidence_refs",
            "calculation_refs",
            "claim_metric_refs",
            "resolved_issue_refs",
        ):
            values[key] = tuple(
                {**r, "inclusion_reason": "REQUESTED"}
                if r["source_id"] in request.subject_refs
                else r
                for r in values[key]
            )
        values.update(
            context_revision=2, sections=tuple(sections), retrieval_history_refs=(history,)
        )
        self.projector.package = ResearchContextPackage.build(**values)

    async def run(self, context):
        async with asyncio.timeout(180):
            await self.projector.build()
            for turn in (1, 2):
                self.turns = turn
                package = self.projector.package
                self.current = CallReceipt(
                    interaction_id=self.interaction_id,
                    turn_number=turn,
                    call_id=f"{self.interaction_id}:{turn}:1",
                    context_id=package.context_id,
                    context_revision=package.context_revision,
                    requested_model=self.projector.requested_model,
                    route_ref=self.projector.route_ref,
                    requested_route=self.client.route_ids[self.projector.requested_model],
                    configuration_snapshot=configuration_snapshot(self.client, self.projector.task),
                )
                schema = ValuationTurn if turn == 1 else StandardResearchAgentStructuredOutput
                self.schema_digest = digest(schema.model_json_schema(), "model-response-schema/v1")
                token = context_call_observer.set(self)
                response = None
                failure = None
                started = monotonic()
                try:
                    self.logical_calls += 1
                    response = await self.agent.execute_valuation_turn(package, schema)
                    await self.projector.checkpoint()
                    if self.current.observed_model != self.current.requested_model:
                        raise BindingDenied("MODEL_IDENTITY_OUT_OF_POLICY", "observed model")
                    self.current = self.current.model_copy(
                        update={"outcome_digest": digest(response.output)}
                    )
                except BaseException as exc:
                    failure = exc
                    self.current = self.current.model_copy(
                        update={
                            "phase": "RESULT_UNKNOWN"
                            if self.current.phase == "DISPATCHED"
                            else "FAILED",
                            "diagnostic_code": getattr(exc, "code", type(exc).__name__),
                        }
                    )
                    raise
                finally:
                    context_call_observer.reset(token)
                    self.current = self.current.model_copy(
                        update={"elapsed_ms": round((monotonic() - started) * 1000)}
                    )
                    self.receipts.append(self.current)
                    try:
                        b = await self.projector.executor._bind_step(
                            self.projector.task,
                            f"wp03:valuation:turn:{turn}:receipt",
                            {
                                "execution_receipt": canonical_value(self.current),
                                "response": canonical_value(response.output) if response else None,
                                "interaction_counters": self.summary(),
                            },
                        )
                        self.receipt_refs.append(b.resolved_input_binding_id)
                    except BindingDenied:
                        await asyncio.to_thread(
                            self.agent.retain_uncommitted_valuation_failure,
                            self.projector.task,
                            self.current,
                        )
                        if failure is None:
                            raise
                if turn == 1 and response.output.kind == "RETRIEVE":
                    await self.retrieve(response.output.request)
                    continue
                if turn == 1:
                    response = replace(response, output=response.output.answer)
                await self.final_checkpoint()
                return self.agent.retain_valuation_final(
                    context,
                    response,
                    round((monotonic() - self.started) * 1000),
                    package.context_id,
                )
            raise BindingDenied("RETRIEVAL_ROUND_BUDGET_EXHAUSTED")

    def summary(self):
        return {
            "interaction_id": self.interaction_id,
            "logical_turn_count": self.turns,
            "provider_logical_call_count": self.logical_calls,
            "retrieval_round_count": self.rounds,
            "client_physical_dispatch_count": self.calls,
            "tool_data_read_count": self.projector.read_count,
            "read_count_scope": "PROJECTION_OWNER_READ_CALLS_ONLY",
            "nested_persistence_reads": "NOT_INSTRUMENTED",
            "physical_database_queries": "UNKNOWN",
            "fallback_count": 0,
            "retry_count": 0,
            "receipt_refs": self.receipt_refs,
            "calls": canonical_value(self.receipts),
            "provider_internal_fanout": "UNKNOWN",
        }
