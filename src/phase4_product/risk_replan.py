"""Structured human controls; free-form chat/voice never enter this authority."""

from typing import Literal

from pydantic import Field

from src.domain.node_binding import BindingValue, GraphIdentity


class ProposalExpectations(BindingValue):
    run_id: str = Field(min_length=1)
    proposal_id: str = Field(min_length=1)
    expected_proposal_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    expected_base_graph: GraphIdentity
    expected_decision_revision: int = Field(ge=0, strict=True)


class ApproveReplan(ProposalExpectations):
    authorize_replan: Literal[True]


class DeclineReplan(ProposalExpectations):
    reject_replan: Literal[True]


class ReopenReplan(ProposalExpectations):
    reopen_declined_replan: Literal[True]


class CancelResearch(BindingValue):
    run_id: str = Field(min_length=1)
    expected_control_revision: int = Field(ge=0, strict=True)
    abandon: Literal[True]


async def read(backend, run_id):
    # Existing server-local access surface validates the durable Run and Object association.
    await backend.get_run(run_id)
    return await backend.service.repository.replan_projection(run_id)


async def decide(backend, run_id, proposal_id, payload, action, key):
    from src.domain.node_binding import BindingDenied
    from src.phase4_product.errors import product_error

    if payload.run_id != run_id or (action != "CANCEL" and payload.proposal_id != proposal_id):
        raise backend._not_found("research_run", run_id)
    current = await read(backend, run_id)
    active = current.get("active_proposal")
    if active is None or (proposal_id is not None and proposal_id != active["proposal_id"]):
        raise backend._not_found("replan", proposal_id or run_id)
    command = payload.model_dump(mode="json")
    command.update(object_id=current["object_id"], proposal_id=active["proposal_id"], action=action)
    if "expected_base_graph" in command:
        command["expected_graph"] = command.pop("expected_base_graph")
    try:
        receipt = await backend.service.repository.decide_replan(
            run_id, command, actor="LOCAL_SINGLE_USER", key=key
        )
    except BindingDenied as exc:
        raise product_error(
            "IDEMPOTENCY_CONFLICT", "Replan command conflicts with current authority"
        ) from exc
    backend._wake.set()
    return {"receipt": receipt, "projection": await read(backend, run_id)}
