"""Bounded dependency-aware branches; unavailable data is not a caught code error."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from src.capabilities.generated.validation import GeneratedCapabilityExecutionError
from src.domain.financial_branch import BranchStatus, FinancialBranchResult
from src.domain.output_dependency import LocalOutputFailure
from src.tooling.generated_sandbox import SandboxEnvironmentUnavailableError


@dataclass
class FinancialBranch:
    identity: FinancialBranchResult
    execute: Callable[[], Awaitable[FinancialBranchResult]]


async def execute_financial_branches(
    branches: list[FinancialBranch],
    *,
    publish: Callable[[FinancialBranchResult], Awaitable[None]],
    concurrency: int = 3,
) -> list[FinancialBranchResult]:
    if not 1 <= concurrency <= 8:
        raise ValueError("financial branch concurrency must be between one and eight")
    ids = [branch.identity.branch_id for branch in branches]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate financial branch identity")
    pending = {
        branch.identity.branch_id: set(branch.identity.dependency_ids) for branch in branches
    }
    done: set[str] = set()
    while pending:
        ready = {key for key, deps in pending.items() if deps <= done}
        if not ready:
            raise ValueError("financial branch dependencies are unknown or cyclic")
        done.update(ready)
        pending = {key: deps for key, deps in pending.items() if key not in ready}
    limit = asyncio.Semaphore(concurrency)
    finished = {key: asyncio.Event() for key in ids}
    outcomes: dict[str, FinancialBranchResult] = {}
    errors: dict[str, Exception] = {}

    async def worker(branch: FinancialBranch):
        identity = branch.identity
        for dependency in identity.dependency_ids:
            await finished[dependency].wait()
        if any(
            outcomes[key].status is not BranchStatus.COMPLETED for key in identity.dependency_ids
        ):
            result = identity.model_copy(
                update={
                    "status": BranchStatus.INSUFFICIENT_DATA,
                    "reason_code": "DEPENDENCY_UNAVAILABLE",
                }
            )
        else:
            async with limit:
                operation = asyncio.create_task(branch.execute())
                try:
                    result = await asyncio.shield(operation)
                    if (result.branch_id, result.run_id, result.task_id) != (
                        identity.branch_id,
                        identity.run_id,
                        identity.task_id,
                    ):
                        raise ValueError("financial branch returned foreign identity")
                except asyncio.CancelledError:
                    # Drain owned work (including sandbox threads) before exiting scope.
                    try:
                        await operation
                    except Exception:
                        pass
                    raise
                except SandboxEnvironmentUnavailableError:
                    result = identity.model_copy(
                        update={
                            "status": BranchStatus.BLOCKED_BY_RUNTIME,
                            "reason_code": "SANDBOX_ENVIRONMENT_UNAVAILABLE",
                        }
                    )
                except Exception as error:
                    errors[identity.branch_id] = error
                    result = identity.model_copy(
                        update={"status": BranchStatus.FAILED, "reason_code": "CALCULATION_FAILURE"}
                    )
        await publish(result)
        outcomes[identity.branch_id] = result
        finished[identity.branch_id].set()

    async with asyncio.TaskGroup() as group:
        for branch in branches:
            group.create_task(worker(branch))
    # Do not swallow a real defect or turn it into data unavailability. Independent
    # siblings have settled and durably published before the original error is raised.
    if errors:
        error = next(errors[key] for key in ids if key in errors)
        # Only the owned deterministic execution error is research-local. Unknown
        # validation, authority and persistence defects still terminate globally.
        if all(isinstance(value, GeneratedCapabilityExecutionError) for value in errors.values()):
            raise LocalOutputFailure("Recorded deterministic calculation failure") from error
        raise error
    return [outcomes[key] for key in ids]
