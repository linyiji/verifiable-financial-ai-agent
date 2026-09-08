import asyncio

import pytest

from src.domain.financial_branch import (
    BranchRequirement,
    BranchStatus,
    FinancialBranchResult,
    claim_dependencies_available,
)
from src.runtime.financial_branches import FinancialBranch, execute_financial_branches


def identity(name, dependencies=()):
    return FinancialBranchResult(
        branch_id=name,
        run_id="RUN-TEST",
        task_id="TASK-TEST",
        calculation_type=name,
        status=BranchStatus.NOT_APPLICABLE,
        requirement=BranchRequirement.SUPPORTING,
        required_inputs=1,
        available_inputs=1,
        dependency_ids=list(dependencies),
    )


@pytest.mark.asyncio
async def test_independent_parallelism_dependency_block_and_claim_gating():
    active = 0
    peak = 0
    reached = set()
    both_started = asyncio.Event()
    published = []

    def branch(name, dependencies=(), unavailable=False):
        spec = identity(name, dependencies)

        async def execute():
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            reached.add(name)
            if name in {"FCF", "C"}:
                if {"FCF", "C"} <= reached:
                    both_started.set()
                await asyncio.wait_for(both_started.wait(), timeout=2)
            active -= 1
            return spec.model_copy(
                update={
                    "status": BranchStatus.INSUFFICIENT_DATA
                    if unavailable
                    else BranchStatus.COMPLETED,
                    "calculation_ids": [] if unavailable else [f"CALC-{name}"],
                    "reason_code": "INSUFFICIENT_TECHNICAL_HISTORY" if unavailable else None,
                }
            )

        return FinancialBranch(identity=spec, execute=execute)

    async def publish(result):
        published.append(result)

    results = await execute_financial_branches(
        [
            branch("FCF"),
            branch("SMA200", unavailable=True),
            branch("C"),
            branch("D", dependencies=("SMA200",)),
        ],
        publish=publish,
    )
    assert peak >= 2
    assert "C" in reached and "D" not in reached
    assert claim_dependencies_available(["FCF"], results)
    assert not claim_dependencies_available(["SMA200"], results)
    assert not claim_dependencies_available(["missing"], results)
    assert len(published) == 4


@pytest.mark.asyncio
async def test_true_error_is_not_data_shortfall_and_successful_sibling_is_published():
    published = []

    async def fail():
        raise ValueError("deterministic output defect")

    async def complete():
        return identity("B").model_copy(
            update={"status": BranchStatus.COMPLETED, "calculation_ids": ["CALC-B"]}
        )

    async def publish(result):
        published.append(result)

    with pytest.raises(ValueError, match="deterministic output defect"):
        await execute_financial_branches(
            [FinancialBranch(identity("A"), fail), FinancialBranch(identity("B"), complete)],
            publish=publish,
        )
    assert {p.branch_id: p.status for p in published} == {
        "A": BranchStatus.FAILED,
        "B": BranchStatus.COMPLETED,
    }


@pytest.mark.asyncio
async def test_cancellation_drains_owned_work():
    started, finish = asyncio.Event(), asyncio.Event()

    async def operation():
        started.set()
        await finish.wait()
        return identity("A").model_copy(
            update={"status": BranchStatus.COMPLETED, "calculation_ids": ["CALC-A"]}
        )

    async def publish(result):
        pass

    task = asyncio.create_task(
        execute_financial_branches([FinancialBranch(identity("A"), operation)], publish=publish)
    )
    await started.wait()
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
