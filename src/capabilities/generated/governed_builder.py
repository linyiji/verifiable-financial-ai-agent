"""Generated specs share Specialist route authority, policy and durable budgets."""

from pydantic import BaseModel

from src.adapters.llm.execution import ProviderExecutionPolicyV1
from src.adapters.llm.provider import LLMFailureClassification, StructuredOutputError
from src.capabilities.generated.artifacts import generated_text_sha256
from src.capabilities.generated.builder import PlannerProviderCodeBuilder, _initial_messages
from src.capabilities.generated.contract import GeneratedCapabilityRequestV1
from src.capabilities.generated.spec import (
    GENERATED_CAPABILITY_COMPILER_VERSION,
    GeneratedCapabilityCompilerV1,
    GeneratedCapabilitySpecV1,
    GeneratedCapabilitySpecValidationError,
)
from src.domain.recovery import Scope
from src.phase4_product.hashing import canonical_json_sha256 as digest


class GenerationContext(BaseModel):
    object_id: str
    scheme_id: str
    task_id: str
    request: dict


class AcceptedResponseProvider:
    """One already validated response; never performs a network request."""

    def __init__(self, response):
        self.response = response
        self.provider_name = response.provider
        self.model_name = response.actual_model
        self.execution_policy = ProviderExecutionPolicyV1(
            max_attempts=1,
            bounded_backoff_seconds=(),
            overall_workload_deadline_seconds=90,
        )
        self.used = False

    def lock_to_model(self, model):
        if model != self.model_name:
            raise ValueError("Accepted generation identity drift")
        return self

    async def complete_structured(self, **kwargs):
        if self.used:
            raise ValueError("Accepted generation response already consumed")
        self.used = True
        return self.response


class GovernedCodeBuilder:
    """One recovery entry per exact task/requirement, across all outer attempts."""

    builder_id = "governed-spec-compiler-builder-v1"
    max_build_attempts = 1

    def __init__(self, recovery, repository, *, initial_route="teamorouter-sol"):
        self.recovery = recovery
        self.repository = repository
        self.initial_route = initial_route
        candidate = recovery.detector.routes.get(initial_route)
        if candidate is None:
            raise ValueError("Generated capability initial route is not authorized")
        self.provider_name = candidate.provider
        self.model_name = candidate.model
        self.execution_policy = ProviderExecutionPolicyV1(
            max_attempts=1,
            bounded_backoff_seconds=(),
            per_attempt_deadline_seconds=180,
            overall_workload_deadline_seconds=min(180, recovery.budget.max_total_recovery_time),
        )

    async def generate(self, request):
        aggregate = await self.repository.get_run(request.gap.run_id)
        if aggregate is None or aggregate.run.run_id != request.gap.run_id:
            raise ValueError("Generated capability Run authority missing")
        task = aggregate.runtime.task(request.gap.task_id)
        if task.assigned_agent != request.gap.requested_by:
            raise ValueError("Generated capability Task authority mismatch")
        owned = GeneratedCapabilityRequestV1.from_build_request(request)
        context = GenerationContext(
            object_id=aggregate.run.research_object_id,
            scheme_id=aggregate.scheme.scheme_id,
            task_id=task.task_id,
            request=owned.model_dump(mode="json"),
        )
        scope = Scope(
            run_id=task.run_id,
            task_id=task.task_id,
            object_id=context.object_id,
            scheme_id=context.scheme_id,
            task_profile="GENERATED_CAPABILITY:" + owned.capability_id,
            agent_id=task.assigned_agent,
            operation_id="generated-capability:" + request.gap.requirement.requirement_id,
            context_hash=digest(context.model_dump(mode="json")),
            contract_hash=digest(
                {
                    "schema": GeneratedCapabilitySpecV1.model_json_schema(),
                    "compiler": GENERATED_CAPABILITY_COMPILER_VERSION,
                    "requirement": request.gap.requirement.model_dump(mode="json"),
                }
            ),
        )
        compiler = GeneratedCapabilityCompilerV1()

        def validate_output(output):
            try:
                compiled = compiler.compile(owned, output)
            except GeneratedCapabilitySpecValidationError as error:
                raise StructuredOutputError(
                    "Generated spec rejected by owned compiler",
                    failure_classification=LLMFailureClassification.SEMANTIC_SCHEMA_FAILURE,
                ) from error
            return generated_text_sha256(compiled.output.source_code)

        response = await self.recovery.execute_scope(
            context,
            scope,
            self.recovery.clients[self.initial_route],
            messages=_initial_messages(owned),
            response_model=GeneratedCapabilitySpecV1,
            schema_name=PlannerProviderCodeBuilder.schema_name,
            workload_type="GENERATED_CAPABILITY",
            output_validator=validate_output,
        )
        return await PlannerProviderCodeBuilder(
            AcceptedResponseProvider(response),
            compiler=compiler,
            exact_model=response.actual_model,
        ).generate(request)
