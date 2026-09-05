from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest
from pydantic import ValidationError

from src.domain.research_goal import ResearchGoal
from src.domain.research_object import ResearchObject
from src.domain.research_scheme import ResearchSchemeSnapshot
from src.phase4_product.admission import (
    DRAFT_EXPIRY,
    IdempotencyDecisionKind,
    ResearchRunDraftRecordV1,
    SchedulerAdmissionState,
    build_confirm_response,
    build_prepare_draft,
    build_run_admission,
    build_scheduler_admission,
    confirmation_request_hash,
    create_object_request_hash,
    decide_idempotency,
    draft_hash_is_valid,
    mark_draft_consumed,
    prepare_request_hash,
    require_idempotency_match,
    validate_confirm_request,
)
from src.phase4_product.contracts import (
    ConfirmResearchRunRequestV1,
    CreateResearchObjectRequestV1,
    GoalProjectionV1,
    PrepareResearchRunRequestV1,
    SchemeProjectionV1,
)
from src.phase4_product.durability import (
    AtomicObjectCreateCommit,
    AtomicPrepareCommit,
    DurableObjectCreateOutcomeV1,
    DurablePrepareOutcomeV1,
)
from src.phase4_product.errors import ErrorCodeV1, ProductError
from src.phase4_product.hashing import idempotency_key_digest

NOW = datetime(2026, 9, 5, 9, tzinfo=UTC)


def _prepare_values(
    *,
    object_id: str = "OBJ-A",
    goal_id: str = "GOAL-A",
    scheme_id: str = "SCHEME-A",
) -> tuple[PrepareResearchRunRequestV1, GoalProjectionV1, SchemeProjectionV1]:
    request = PrepareResearchRunRequestV1(
        research_object_id=object_id,
        research_goal="Evaluate durable product admission",
        as_of=date(2026, 9, 5),
        preferences={"currency": "USD", "include_peers": True},
    )
    goal = GoalProjectionV1(
        goal_id=goal_id,
        research_object_id=object_id,
        goal_text=request.research_goal,
        as_of=request.as_of,
        preferences=request.preferences,
        created_at=NOW,
    )
    scheme = SchemeProjectionV1(
        scheme_id=scheme_id,
        research_object_id=object_id,
        goal_id=goal_id,
        research_scope=("fundamentals", "technical"),
        generated_by="planner-v1",
        created_at=NOW,
        confirmed_at=None,
    )
    return request, goal, scheme


def _draft():
    request, goal, scheme = _prepare_values()
    return build_prepare_draft(
        request,
        draft_id="DRAFT-A",
        goal=goal,
        scheme_snapshot=scheme,
        created_at=NOW,
    )


def _confirm_request(draft=None, **updates: object) -> ConfirmResearchRunRequestV1:
    draft = draft or _draft()
    payload = {
        "draft_id": draft.draft_id,
        "draft_version": draft.draft_version,
        "draft_hash": draft.draft_hash,
        "research_object_id": draft.object_id,
        "confirm_scheme": True,
    }
    payload.update(updates)
    return ConfirmResearchRunRequestV1.model_validate(payload)


def _validated(draft=None):
    draft = draft or _draft()
    return validate_confirm_request(draft, _confirm_request(draft), now=NOW + timedelta(minutes=1))


def _admission(draft=None):
    return build_run_admission(
        _validated(draft),
        admission_id="ADMISSION-A",
        run_id="RUN-A",
        planned_graph_id="GRAPH-A",
        admitted_at=NOW + timedelta(minutes=1),
    )


def _assert_product_error(
    exc_info: pytest.ExceptionInfo[ProductError],
    *,
    code: ErrorCodeV1,
    reason_code: str | None = None,
) -> None:
    error = exc_info.value
    assert error.code is code
    if reason_code is not None:
        assert error.details == {"reason_code": reason_code}


def test_prepare_is_scheme_only_hash_bound_and_deterministic() -> None:
    request, goal, scheme = _prepare_values()
    first = build_prepare_draft(
        request,
        draft_id="DRAFT-A",
        goal=goal,
        scheme_snapshot=scheme,
        created_at=NOW,
    )
    second = build_prepare_draft(
        request,
        draft_id="DRAFT-A",
        goal=goal,
        scheme_snapshot=scheme,
        created_at=NOW,
    )

    assert first == second
    assert first.preview_kind == "SCHEME_ONLY"
    assert first.status == "AWAITING_CONFIRMATION"
    assert first.scheme_snapshot.confirmed_at is None
    assert first.planned_graph_availability.model_dump(mode="json") == {
        "status": "NOT_GENERATED",
        "reason_code": "PLAN_CREATED_ON_CONFIRM",
        "retryable": False,
    }
    assert first.expires_at - first.created_at == DRAFT_EXPIRY
    assert draft_hash_is_valid(first)


@pytest.mark.parametrize(
    ("target", "replacement"),
    [
        ("goal_object", "OBJ-B"),
        ("scheme_object", "OBJ-B"),
        ("scheme_goal", "GOAL-B"),
        ("goal_text", "A different request"),
    ],
)
def test_prepare_rejects_exact_identity_or_request_substitution(
    target: str,
    replacement: str,
) -> None:
    request, goal, scheme = _prepare_values()
    if target == "goal_object":
        goal = goal.model_copy(update={"research_object_id": replacement})
    elif target == "scheme_object":
        scheme = scheme.model_copy(update={"research_object_id": replacement})
    elif target == "scheme_goal":
        scheme = scheme.model_copy(update={"goal_id": replacement})
    else:
        goal = goal.model_copy(update={"goal_text": replacement})

    with pytest.raises(ProductError) as exc_info:
        build_prepare_draft(
            request,
            draft_id="DRAFT-A",
            goal=goal,
            scheme_snapshot=scheme,
            created_at=NOW,
        )
    _assert_product_error(exc_info, code=ErrorCodeV1.IDENTITY_MISMATCH)


def test_confirm_hash_binds_exact_body_but_no_transport_metadata() -> None:
    draft = _draft()
    request = _confirm_request(draft)
    validated = validate_confirm_request(draft, request, now=NOW + timedelta(minutes=1))

    assert validated.confirmation_request_hash == confirmation_request_hash(request)
    assert "request_id" not in request.model_dump(mode="json")
    assert "idempotency_key" not in request.model_dump(mode="json")


def test_confirm_rejects_object_mismatch_without_fallback() -> None:
    draft = _draft()
    with pytest.raises(ProductError) as exc_info:
        validate_confirm_request(
            draft,
            _confirm_request(draft, research_object_id="OBJ-B"),
            now=NOW + timedelta(minutes=1),
        )
    _assert_product_error(exc_info, code=ErrorCodeV1.IDENTITY_MISMATCH)
    assert exc_info.value.status_code == 404


@pytest.mark.parametrize(
    ("updates", "reason_code"),
    [
        ({"draft_version": 2}, "DRAFT_VERSION_MISMATCH"),
        ({"draft_hash": "sha256:" + "f" * 64}, "DRAFT_VERSION_MISMATCH"),
    ],
)
def test_confirm_rejects_stale_version_or_hash(
    updates: dict[str, object],
    reason_code: str,
) -> None:
    draft = _draft()
    with pytest.raises(ProductError) as exc_info:
        validate_confirm_request(
            draft,
            _confirm_request(draft, **updates),
            now=NOW + timedelta(minutes=1),
        )
    _assert_product_error(exc_info, code=ErrorCodeV1.CONFLICT, reason_code=reason_code)


def test_confirm_rejects_expired_and_consumed_drafts_with_distinct_reasons() -> None:
    draft = _draft()
    request = _confirm_request(draft)
    with pytest.raises(ProductError) as expired:
        validate_confirm_request(draft, request, now=draft.expires_at)
    _assert_product_error(expired, code=ErrorCodeV1.CONFLICT, reason_code="DRAFT_EXPIRED")

    consumed = mark_draft_consumed(
        draft,
        admission=_admission(draft),
        consumed_at=NOW + timedelta(minutes=2),
    )
    with pytest.raises(ProductError) as duplicate:
        validate_confirm_request(consumed, request, now=NOW + timedelta(minutes=3))
    _assert_product_error(duplicate, code=ErrorCodeV1.CONFLICT, reason_code="DRAFT_CONSUMED")


def test_confirm_builds_one_immutable_planning_admission() -> None:
    admission = _admission()
    assert admission.model_dump(mode="json") == {
        "schema_version": "phase4-run-admission/v1",
        "admission_id": "ADMISSION-A",
        "run_id": "RUN-A",
        "object_id": "OBJ-A",
        "draft_id": "DRAFT-A",
        "draft_version": 1,
        "draft_hash": _draft().draft_hash,
        "goal_id": "GOAL-A",
        "scheme_id": "SCHEME-A",
        "planned_graph_id": "GRAPH-A",
        "status": "PLANNING",
        "auto_start": {"required": True, "admitted": True},
        "confirmation_request_hash": admission.confirmation_request_hash,
        "admitted_at": "2026-09-05T09:01:00Z",
        "projection_ref": "/api/research-runs/RUN-A/projection",
        "events_ref": "/api/research-runs/RUN-A/events",
    }


def test_idempotency_decision_has_create_replay_and_exact_mismatch_only() -> None:
    request_hash = "sha256:" + "1" * 64
    another_hash = "sha256:" + "2" * 64

    create = decide_idempotency(
        incoming_request_hash=request_hash,
        stored_request_hash=None,
    )
    replay = decide_idempotency(
        incoming_request_hash=request_hash,
        stored_request_hash=request_hash,
    )
    mismatch = decide_idempotency(
        incoming_request_hash=another_hash,
        stored_request_hash=request_hash,
    )

    assert create.kind is IdempotencyDecisionKind.CREATE
    assert replay.kind is IdempotencyDecisionKind.REPLAY
    assert mismatch.kind is IdempotencyDecisionKind.CONFLICT
    assert mismatch.reason_code == "IDEMPOTENCY_REQUEST_MISMATCH"

    with pytest.raises(ProductError) as exc_info:
        require_idempotency_match(mismatch)
    _assert_product_error(
        exc_info,
        code=ErrorCodeV1.CONFLICT,
        reason_code="IDEMPOTENCY_REQUEST_MISMATCH",
    )


def test_object_create_outcome_is_request_bound_and_atomically_identity_closed() -> None:
    idempotency_key = "object-create-key-a"
    request = CreateResearchObjectRequestV1(
        symbol="ACME",
        company_name="Acme Corp",
        exchange="NASDAQ",
    )
    request_hash = create_object_request_hash(request)
    outcome = DurableObjectCreateOutcomeV1(
        outcome_id="OBJECT-OUTCOME-A",
        effective_access_scope_key="LOCAL_SINGLE_USER",
        idempotency_key_digest=idempotency_key_digest(
            idempotency_key,
            method="POST",
            route_template="/api/objects",
        ),
        method="POST",
        route_template="/api/objects",
        request_hash=request_hash,
        object_id="OBJ-A",
        created_at=NOW,
    )
    research_object = ResearchObject(
        object_id="OBJ-A",
        symbol=request.symbol,
        company_name=request.company_name,
        exchange=request.exchange,
        created_at=NOW,
        updated_at=NOW,
    )

    commit = AtomicObjectCreateCommit(
        outcome=outcome,
        idempotency_key=idempotency_key,
        request=request,
        research_object=research_object,
    )
    replay = decide_idempotency(
        incoming_request_hash=request_hash,
        stored_request_hash=outcome.request_hash,
    )

    assert commit.outcome.object_id == commit.research_object.object_id
    assert replay.kind is IdempotencyDecisionKind.REPLAY
    with pytest.raises(ProductError, match="Research Object disagree"):
        AtomicObjectCreateCommit(
            outcome=outcome,
            idempotency_key=idempotency_key,
            request=request,
            research_object=research_object.model_copy(update={"object_id": "OBJ-B"}),
        )


def test_object_symbol_is_normalized_before_request_hash_and_commit() -> None:
    idempotency_key = "normalized-object-key"
    raw = CreateResearchObjectRequestV1(
        symbol=" nvda ",
        company_name="NVIDIA Corporation",
        exchange="NASDAQ",
    )
    canonical = CreateResearchObjectRequestV1(
        symbol="NVDA",
        company_name="NVIDIA Corporation",
        exchange="NASDAQ",
    )
    assert raw == canonical
    assert raw.symbol == "NVDA"
    assert create_object_request_hash(raw) == create_object_request_hash(canonical)
    outcome = DurableObjectCreateOutcomeV1(
        outcome_id="OBJECT-OUTCOME-NVDA",
        effective_access_scope_key="LOCAL_SINGLE_USER",
        idempotency_key_digest=idempotency_key_digest(
            idempotency_key,
            method="POST",
            route_template="/api/objects",
        ),
        method="POST",
        route_template="/api/objects",
        request_hash=create_object_request_hash(raw),
        object_id="OBJ-NVDA",
        created_at=NOW,
    )
    commit = AtomicObjectCreateCommit(
        outcome=outcome,
        idempotency_key=idempotency_key,
        request=raw,
        research_object=ResearchObject(
            object_id="OBJ-NVDA",
            symbol="NVDA",
            company_name="NVIDIA Corporation",
            exchange="NASDAQ",
            created_at=NOW,
            updated_at=NOW,
        ),
    )
    assert commit.research_object.symbol == raw.symbol


def test_prepare_outcome_replays_exact_draft_and_changed_request_conflicts() -> None:
    idempotency_key = "prepare-key-a"
    request, goal_projection, scheme_projection = _prepare_values()
    draft = build_prepare_draft(
        request,
        draft_id="DRAFT-A",
        goal=goal_projection,
        scheme_snapshot=scheme_projection,
        created_at=NOW,
    )
    outcome = DurablePrepareOutcomeV1(
        outcome_id="PREPARE-OUTCOME-A",
        effective_access_scope_key="LOCAL_SINGLE_USER",
        idempotency_key_digest=idempotency_key_digest(
            idempotency_key,
            method="POST",
            route_template="/api/research-runs/prepare",
        ),
        method="POST",
        route_template="/api/research-runs/prepare",
        request_hash=prepare_request_hash(request),
        draft=draft,
        created_at=NOW,
    )
    commit = AtomicPrepareCommit(
        outcome=outcome,
        idempotency_key=idempotency_key,
        request=request,
        draft_record=ResearchRunDraftRecordV1(draft=draft),
        goal=ResearchGoal.model_validate(goal_projection.model_dump(mode="python")),
        scheme=ResearchSchemeSnapshot.model_validate(scheme_projection.model_dump(mode="python")),
    )

    replay = decide_idempotency(
        incoming_request_hash=prepare_request_hash(request),
        stored_request_hash=outcome.request_hash,
    )
    changed = request.model_copy(update={"research_goal": "A changed immutable request"})
    conflict = decide_idempotency(
        incoming_request_hash=prepare_request_hash(changed),
        stored_request_hash=outcome.request_hash,
    )

    assert commit.outcome.draft is draft
    assert replay.kind is IdempotencyDecisionKind.REPLAY
    assert conflict.kind is IdempotencyDecisionKind.CONFLICT
    with pytest.raises(ProductError, match="different request"):
        require_idempotency_match(conflict)

    tampered_draft = draft.model_copy(update={"draft_hash": "sha256:" + "e" * 64})
    with pytest.raises(ProductError, match="immutable hash check"):
        tampered_outcome = replace(outcome, draft=tampered_draft)
        AtomicPrepareCommit(
            outcome=tampered_outcome,
            idempotency_key=idempotency_key,
            request=request,
            draft_record=ResearchRunDraftRecordV1(draft=tampered_draft),
            goal=commit.goal,
            scheme=commit.scheme,
        )


def test_exact_replay_changes_response_metadata_not_business_admission() -> None:
    admission = _admission()
    first = build_confirm_response(
        admission,
        request_id="REQ-FIRST",
        idempotency_replayed=False,
    )
    replay = build_confirm_response(
        admission,
        request_id="REQ-REPLAY",
        idempotency_replayed=True,
    )

    assert first.admission is replay.admission
    assert first.admission.model_dump(mode="json") == replay.admission.model_dump(mode="json")
    assert first.response_meta.idempotency_replayed is False
    assert replay.response_meta.idempotency_replayed is True
    assert first.response_meta.request_id != replay.response_meta.request_id


def test_consumption_tombstone_is_atomic_and_keeps_public_draft_immutable() -> None:
    draft = _draft()
    admission = _admission(draft)
    record = mark_draft_consumed(draft, admission=admission)

    assert record.draft is draft
    assert record.consumed is True
    assert record.consumed_admission_id == admission.admission_id
    assert record.consumed_run_id == admission.run_id

    with pytest.raises(ValidationError, match="atomically"):
        ResearchRunDraftRecordV1(
            draft=draft,
            consumed_at=NOW + timedelta(minutes=1),
            consumed_admission_id=admission.admission_id,
            consumed_run_id=None,
        )


def test_scheduler_record_is_one_pending_durable_effect_per_run() -> None:
    admission = _admission()
    scheduler = build_scheduler_admission(
        admission,
        idempotency_outcome_id="IDEMPOTENCY-OUTCOME-A",
        created_at=admission.admitted_at,
    )

    assert scheduler.admission_id == admission.admission_id
    assert scheduler.run_id == admission.run_id
    assert scheduler.state is SchedulerAdmissionState.PENDING
    assert scheduler.delivery_attempt_count == 0
    assert scheduler.next_attempt_at == admission.admitted_at
    assert scheduler.policy_version == "phase4-run-admission-delivery/v1"
