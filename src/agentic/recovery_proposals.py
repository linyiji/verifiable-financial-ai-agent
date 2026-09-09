"""Optional bounded proposals, never a source of execution authority.

Not installed in legacy production composition. Both the decider and execution
adapters must represent ONE physical request (no hidden transport retries).
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, Literal

from pydantic import Field

from src.domain.execution_contract import (
    CallPurpose,
    ContractDenied,
    ExecutionContract,
    Immutable,
    LeaseToken,
    fingerprint,
)


class RecoveryProposal(Immutable):
    version: Literal["recovery-proposal/v1"] = "recovery-proposal/v1"
    intent_id: str
    task_id: str
    operation_id: str
    contract_hash: str
    graph_hash: str
    graph_version: int
    failure_hash: str
    evidence_refs: tuple[str, ...]
    action: str
    current_route: str
    target_route: str | None = None
    expires_at: float = Field(gt=0)


class ProposalAuthority(Immutable):
    """Prospective owner policy, passed by composition, never by model output."""

    contract_hash: str
    route_providers: dict[str, str]
    verified_route_evidence: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    approved_cross_provider_routes: tuple[str, ...] = ()
    decider_contract_hash: str | None = None
    deterministic_fallback_allowed: bool = False


class ProposalGate:
    def __init__(self, ledger, authority: ProposalAuthority, clock):
        self.ledger, self.authority, self.clock = ledger, authority, clock

    async def validate(self, token: LeaseToken, proposal: RecoveryProposal):
        doc = await self.ledger.view(token.intent_id)
        op = doc["operations"].get(token.operation_id)
        if op is None:
            raise ContractDenied("LEGACY_NOT_RESUMABLE")
        contract = ExecutionContract.model_validate(op["contract"])
        if contract.contract_hash != op["contract_hash"]:
            raise ContractDenied("CONTRACT_CORRUPT")
        if (
            proposal.intent_id != token.intent_id
            or proposal.operation_id != token.operation_id
            or proposal.task_id != contract.task_id
            or proposal.contract_hash != contract.contract_hash
            or self.authority.contract_hash != contract.contract_hash
            or proposal.graph_hash != contract.graph_hash
            or proposal.graph_version != contract.graph_version
        ):
            raise ContractDenied("PROPOSAL_IDENTITY_MISMATCH")
        now = self.clock()
        if proposal.expires_at <= now:
            raise ContractDenied("PROPOSAL_EXPIRED")
        if not op["failures"] or proposal.failure_hash != fingerprint(op["failures"][-1]):
            raise ContractDenied("PROPOSAL_FAILURE_MISMATCH")
        if not set(proposal.evidence_refs).issubset(contract.input_hashes):
            raise ContractDenied("PROPOSAL_EVIDENCE_MISMATCH")
        if proposal.action not in {"SWITCH_MODEL", "SWITCH_PROVIDER", "FAIL_TASK"}:
            raise ContractDenied("UNSUPPORTED_ACTION")
        if proposal.action == "FAIL_TASK":
            if proposal.target_route is not None:
                raise ContractDenied("SAFE_END_HAS_TARGET")
            return contract
        routes = self.authority.route_providers
        target = proposal.target_route
        if (
            target not in contract.candidates
            or proposal.current_route not in contract.candidates
            or target == proposal.current_route
            or target not in routes
            or proposal.current_route not in routes
        ):
            raise ContractDenied("CANDIDATE_NOT_AUTHORIZED")
        same_provider = routes[target] == routes[proposal.current_route]
        if proposal.action == "SWITCH_MODEL" and not same_provider:
            raise ContractDenied("MODEL_SWITCH_PROVIDER_MISMATCH")
        if proposal.action == "SWITCH_PROVIDER" and (
            same_provider or target not in self.authority.approved_cross_provider_routes
        ):
            raise ContractDenied("CROSS_PROVIDER_NOT_AUTHORIZED")
        verified = self.authority.verified_route_evidence.get(target, ())
        if not verified or not set(verified).issubset(contract.input_hashes):
            raise ContractDenied("CAPABILITY_EVIDENCE_REQUIRED")
        return contract

    async def execute(self, token, proposal, *, send_one, validate_output):
        """Validate immutable policy, then atomically reserve/fence before dispatch."""
        contract = await self.validate(token, proposal)
        if proposal.action == "FAIL_TASK":
            await self.ledger.fail(token, {"code": "PROPOSAL_SAFE_END"}, self.clock())
            return {"status": "FAIL_TASK"}
        # Stable across client retries; caller cannot manufacture a new request
        # ID to execute the exact accepted proposal a second time.
        call_id = "proposal:" + fingerprint(proposal)[7:]
        call = await self.ledger.reserve(
            token,
            call_id,
            CallPurpose.TASK_EXECUTION,
            proposal.target_route,
            self.clock(),
            min(contract.per_call_timeout, proposal.expires_at - self.clock()),
        )
        if self.clock() >= proposal.expires_at:
            await self.ledger.cancel(token, call_id, self.clock())
            raise ContractDenied("PROPOSAL_EXPIRED")
        # A replay cannot reserve the same call twice. The ledger independently
        # rechecks all deadlines, persisted budgets and the current lease epoch.
        call = await self.ledger.dispatch(token, call_id, self.clock())
        try:
            remaining = min(
                call["timeout"],
                call["absolute_deadline"] - self.clock(),
                proposal.expires_at - self.clock(),
            )
            async with asyncio.timeout(max(0, remaining)):
                result = await send_one(proposal.target_route, remaining)
            result = validate_output(result)
        except (Exception, asyncio.CancelledError):
            await self.ledger.mark_unknown(token, call_id, self.clock())
            raise
        await self.ledger.save_result(token, call_id, result, self.clock())
        await self.ledger.settle(token, call_id, self.clock())
        return result


class OptionalModelProposer:
    """Default OFF. No recursive decider retry and no research-profile borrowing."""

    def __init__(self, ledger, authority, clock, *, enabled=False):
        self.ledger, self.authority, self.clock = ledger, authority, clock
        self.enabled = enabled

    async def propose(
        self,
        token,
        *,
        call_id,
        route,
        request: dict[str, Any],
        send_one: Callable[..., Awaitable[dict]],
        deterministic_fallback: Callable[[], RecoveryProposal] | None = None,
    ):
        if not self.enabled:
            raise ContractDenied("MODEL_PROPOSALS_DISABLED")
        doc = await self.ledger.view(token.intent_id)
        op = doc["operations"].get(token.operation_id)
        if (
            op is None
            or self.authority.decider_contract_hash is None
            or op["contract_hash"] != self.authority.decider_contract_hash
            or op["contract"]["task_profile"] != "DECIDER"
        ):
            raise ContractDenied("DECIDER_NOT_AUTHORIZED")
        if op["contract"]["input_hashes"].get("decision_request") != fingerprint(request):
            raise ContractDenied("DECIDER_INPUT_MISMATCH")
        call = await self.ledger.reserve(
            token,
            call_id,
            CallPurpose.DECISION,
            route,
            self.clock(),
            op["contract"]["per_call_timeout"],
        )
        call = await self.ledger.dispatch(token, call_id, self.clock())
        try:
            remaining = min(call["timeout"], call["absolute_deadline"] - self.clock())
            async with asyncio.timeout(max(0, remaining)):
                raw = await send_one(request, route, remaining)
            proposal = RecoveryProposal.model_validate(raw)
        except (Exception, asyncio.CancelledError) as exc:
            # A timed-out external result is unknown, not refunded or relabelled
            # success. No second decider call is made. The finite fallback may
            # propose only; execution still needs its separate gate/ledger.
            await self.ledger.mark_unknown(token, call_id, self.clock())
            if isinstance(exc, asyncio.CancelledError):
                raise
            if self.authority.deterministic_fallback_allowed and deterministic_fallback:
                return deterministic_fallback()
            raise ContractDenied("DECIDER_UNAVAILABLE_SAFE_END") from None
        await self.ledger.save_result(
            token, call_id, proposal.model_dump(mode="json"), self.clock()
        )
        await self.ledger.settle(token, call_id, self.clock())
        return proposal
