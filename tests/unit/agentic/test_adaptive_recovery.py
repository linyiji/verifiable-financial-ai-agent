import asyncio

import pytest

from src.adapters.llm.provider import LLMFailureClassification as Code
from src.adapters.llm.provider import LLMProviderError, LLMStructuredResponse
from src.agentic.recovery import AdaptiveRecovery
from src.agentic.research_agent import LLMResearchAgent, ResearchAgentInvocationError
from src.agentic.research_output_artifacts import ResearchAgentOutputArtifactStore
from src.agentic.specialist import SpecialistExecutionContext
from src.domain.agent_output import StandardResearchAgentStructuredOutput as Output
from src.domain.enums import RunStatus, TaskStatus
from src.domain.recovery import Action, Candidate, Capability, RecoveryBudget, RecoveryDecision
from src.domain.task import PlannedTaskGraph, Task
from src.infrastructure.database.recovery import MemoryRecoveryEvidenceStore
from src.phase4_product.hashing import canonical_json_sha256 as digest
from src.runtime.checkpoint import InMemoryCheckpointStore
from src.runtime.events import InMemoryRuntimeEventStore
from src.runtime.scheduler import DependencyScheduler, TaskExecutionResult
from src.runtime.state import RuntimeState


def task():
    return Task(
        run_id="RUN-local",
        task_id="RUN-local:fundamentals",
        task_type="fundamental_analysis",
        goal="Bounded test",
        assigned_agent="fundamental_analyst",
        skill_id="fundamental_analysis_v1",
    )


def context(t=None):
    return SpecialistExecutionContext(
        task=t or task(),
        inputs={"research_object_id": "OBJ-local", "scheme_id": "SCHEME-local", "input_refs": []},
    )


class Client:
    def __init__(self, provider, model, failures=(), delay=0):
        self.provider_name = provider
        self.model_name = model
        self.failures = list(failures)
        self.calls = 0
        self.delay = delay

    async def complete_structured(self, **kwargs):
        self.calls += 1
        await asyncio.sleep(self.delay)
        if self.failures:
            code = self.failures.pop(0)
            if isinstance(code, Exception):
                raise code
            raise LLMProviderError("SENTINEL_SECRET", failure_classification=code)
        return LLMStructuredResponse(
            output=kwargs["response_model"].model_validate(
                dict(
                    summary="Validated local result",
                    key_findings=["Exact input"],
                    risks=[],
                    limitations=[],
                    requires_follow_up=False,
                )
            ),
            provider=self.provider_name,
            requested_model=self.model_name,
            actual_model=self.model_name,
            attempted_models=(self.model_name,),
            input_tokens=12,
            output_tokens=6,
        )


def setup(budget=None, supervisor=None, first_failure=Code.READ_TIMEOUT):
    clients = {
        "teamorouter-sol": Client("teamorouter", "gpt-5.6-sol", [first_failure]),
        "teamorouter-luna": Client("teamorouter", "gpt-5.6-luna", [Code.PROVIDER_UNAVAILABLE]),
        "mimo-direct": Client("mimo", "mimo-v2.5"),
    }
    routes = {
        key: Candidate(
            route=key, provider=c.provider_name, model=c.model_name, authority_exists=True
        )
        for key, c in clients.items()
    }
    certs = {
        (
            "fundamental_analysis",
            "teamorouter-luna",
            "gpt-5.6-luna",
            digest(Output.model_json_schema()),
        ): Capability.VERIFIED
    }
    store = MemoryRecoveryEvidenceStore()
    recovery = AdaptiveRecovery(
        routes,
        clients,
        store,
        capabilities=certs,
        budget=budget,
        supervisor=supervisor,
        forbidden_values=("SENTINEL_SECRET",),
    )
    return recovery, clients, store


def agent(tmp_path, recovery, clients):
    return LLMResearchAgent(
        agent_id="fundamental_analyst",
        supported_task_types=frozenset({"fundamental_analysis"}),
        provider=clients["teamorouter-sol"],
        artifacts=ResearchAgentOutputArtifactStore(tmp_path),
        recovery=recovery,
    )


@pytest.mark.asyncio
async def test_same_task_sol_luna_unknown_check_mimo_success(tmp_path):
    recovery, clients, store = setup()
    result = await agent(tmp_path, recovery, clients).execute(context())
    assert (
        result.agent_output.status == "SUCCESS" and result.agent_output.actual_model == "mimo-v2.5"
    )
    assert [clients[k].calls for k in clients] == [1, 1, 2]
    attempts = [r for r in store.values if r.kind == "ATTEMPT_COMPLETED" and not r.capability_check]
    assert [r.attempt_number for r in attempts] == [1, 2, 3]
    assert [r.outcome for r in attempts] == ["FAIL", "FAIL", "PASS"]
    assert len({r.scope.task_id for r in store.values}) == 1
    assert [r.action for r in store.values if r.kind == "DECISION"] == [
        Action.SWITCH_MODEL,
        Action.CAPABILITY_CHECK,
        Action.SWITCH_PROVIDER,
    ]
    assert "SENTINEL_SECRET" not in str([r.model_dump() for r in store.values])
    assert all(r.recovery_context for r in store.values if r.kind == "DECISION")


@pytest.mark.asyncio
async def test_real_scheduler_continues_same_graph_after_recovery(tmp_path):
    recovery, clients, store = setup()
    researcher = agent(tmp_path, recovery, clients)
    first = task()
    downstream = first.model_copy(
        update={"task_id": "RUN-local:downstream", "dependencies": [first.task_id]}
    )
    graph = PlannedTaskGraph(graph_id="GRAPH-local", run_id=first.run_id, tasks=[first, downstream])
    state = RuntimeState.create(run_id=first.run_id, planned_graph=graph)
    called = []

    class Executor:
        async def execute(self, t, execution_context):
            called.append(t.task_id)
            if t.task_id == first.task_id:
                await researcher.execute(context(t))
            return TaskExecutionResult(result_ref="local://validated")

    scheduler = DependencyScheduler(
        event_store=InMemoryRuntimeEventStore(), checkpoint_store=InMemoryCheckpointStore()
    )
    await scheduler.execute(state=state, executor=Executor())
    assert called == [first.task_id, downstream.task_id]
    assert state.run_status == RunStatus.REVIEW
    assert all(
        t.status == TaskStatus.COMPLETED and t.attempt_count == 1 for t in state.actual_graph.tasks
    )
    assert len(state.actual_graph.tasks) == 2 and state.actual_graph.version == 1


@pytest.mark.asyncio
async def test_budget_stops_without_fourth_attempt(tmp_path):
    recovery, clients, store = setup(RecoveryBudget(max_total_attempts_per_task=2))
    with pytest.raises(ResearchAgentInvocationError):
        await agent(tmp_path, recovery, clients).execute(context())
    assert [clients[k].calls for k in clients] == [1, 1, 0]
    assert store.values[-1].reason_code == "RECOVERY_BUDGET_EXHAUSTED"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [Code.SEMANTIC_SCHEMA_FAILURE, Code.AUTHENTICATION_FAILURE, ValueError("invalid agent")],
)
async def test_nonrecoverable_does_not_switch(tmp_path, error):
    recovery, clients, store = setup(first_failure=error)
    with pytest.raises(ResearchAgentInvocationError):
        await agent(tmp_path, recovery, clients).execute(context())
    assert [clients[k].calls for k in clients] == [1, 0, 0]


@pytest.mark.asyncio
async def test_failed_check_cannot_force_execution(tmp_path):
    recovery, clients, store = setup()
    clients["mimo-direct"].failures = [Code.SEMANTIC_SCHEMA_FAILURE]
    with pytest.raises(ResearchAgentInvocationError):
        await agent(tmp_path, recovery, clients).execute(context())
    assert clients["mimo-direct"].calls == 1
    assert not any(
        r.route == "mimo-direct" and not r.capability_check
        for r in store.values
        if r.kind == "ATTEMPT_STARTED"
    )


@pytest.mark.asyncio
async def test_time_budget_and_redelivery_are_closed(tmp_path):
    recovery, clients, store = setup(RecoveryBudget(max_total_recovery_time=0.01))
    clients["teamorouter-sol"].delay = 0.1
    researcher = agent(tmp_path, recovery, clients)
    with pytest.raises(ResearchAgentInvocationError):
        await researcher.execute(context())
    assert sum(c.calls for c in clients.values()) == 1
    with pytest.raises(ResearchAgentInvocationError):
        await researcher.execute(context())
    assert sum(c.calls for c in clients.values()) == 1


@pytest.mark.asyncio
async def test_supervisor_cannot_cross_identity(tmp_path):
    class Hostile:
        def decide(self, ctx):
            return RecoveryDecision(
                scope=ctx.scope.model_copy(update={"object_id": "OBJ-other"}),
                action=Action.SWITCH_PROVIDER,
                target_route="mimo-direct",
                reason_code="NEXT_GOVERNED_ROUTE",
            )

    recovery, clients, store = setup(supervisor=Hostile())
    with pytest.raises(ResearchAgentInvocationError):
        await agent(tmp_path, recovery, clients).execute(context())
    assert sum(c.calls for c in clients.values()) == 1
    assert any(r.outcome == "DENY" for r in store.values)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "budget",
    [RecoveryBudget(max_capability_checks=0), RecoveryBudget(max_cross_provider_switches=0)],
)
async def test_zero_check_or_provider_budget_never_calls_mimo(tmp_path, budget):
    recovery, clients, store = setup(budget)
    with pytest.raises(ResearchAgentInvocationError):
        await agent(tmp_path, recovery, clients).execute(context())
    assert [clients[k].calls for k in clients] == [1, 1, 0]


@pytest.mark.asyncio
async def test_failed_provider_cannot_mutate_context_for_next_call(tmp_path):
    recovery, clients, store = setup()
    original = clients["teamorouter-sol"].complete_structured
    ctx = context()

    async def mutate_then_fail(**kwargs):
        ctx.inputs["scheme_id"] = "SCHEME-other"
        return await original(**kwargs)

    clients["teamorouter-sol"].complete_structured = mutate_then_fail
    with pytest.raises(ResearchAgentInvocationError):
        await agent(tmp_path, recovery, clients).execute(ctx)
    assert [clients[k].calls for k in clients] == [1, 0, 0]
    assert store.values[-1].reason_code == "NONRECOVERABLE"


@pytest.mark.asyncio
async def test_supervisor_failure_records_safe_terminal(tmp_path):
    class Broken:
        def decide(self, ctx):
            raise ValueError("SENTINEL_SECRET")

    recovery, clients, store = setup(supervisor=Broken())
    with pytest.raises(ResearchAgentInvocationError):
        await agent(tmp_path, recovery, clients).execute(context())
    assert sum(c.calls for c in clients.values()) == 1
    assert store.values[-1].reason_code == "POLICY_DENIED"
    assert "SENTINEL_SECRET" not in str([r.model_dump() for r in store.values])
