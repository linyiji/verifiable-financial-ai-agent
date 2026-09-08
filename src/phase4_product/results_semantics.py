"""Read-only A/B/C semantic projection. No provider, scheduler or artifact writes."""

import json
from typing import Literal

from pydantic import Field, model_validator
from sqlalchemy import select

from src.application.closure_recovery import (
    ClosureRecoveryRecordRow,
    fingerprint,
    retained_proof_outcome,
)
from src.application.persistence import (
    ResearchObjectRow,
    ResearchRunAggregateRow,
    RuntimeEventRow,
    SQLAlchemyApplicationRepository,
)
from src.assurance.independent_financial_review import financial_review_input_snapshot_hash
from src.domain.enums import ProofRequirement
from src.domain.recovery import RecoveryEvidence
from src.domain.runtime_event import RuntimeEvent
from src.infrastructure.database.recovery import RecoveryEvidenceRow
from src.infrastructure.database.research_memory import ResearchViewVersionRow
from src.phase4_product.contracts import FrozenWireModel, ReviewCheckSelectorV1
from src.phase4_product.errors import product_error
from src.phase4_product.retained_assurance import retained_review_surface
from src.phase4_product.safety import safe_text
from src.runtime.events import validate_event_log

CATEGORIES = (
    "Research Lead",
    "Specialist Agents",
    "Data Providers",
    "Deterministic Code",
    "Runtime & Recovery",
    "Financial Review",
    "Proof",
    "Release / Report / Memory",
)


class Comparison(FrozenWireModel):
    field: str
    expected: str | None
    actual: str | None


class Check(FrozenWireModel):
    selector: ReviewCheckSelectorV1
    status: Literal["PASS", "REVIEW", "BLOCK"]
    comparison: tuple[Comparison, ...]
    execution_refs: tuple[str, ...]


class Block(FrozenWireModel):
    claim_id: str
    metric_id: str
    title: str
    statement: str
    calculation_id: str
    evidence_refs: tuple[str, ...]
    review_selectors: tuple[ReviewCheckSelectorV1, ...]
    execution_refs: tuple[str, ...]


class Record(FrozenWireModel):
    ref: str
    category: str
    label: str
    status: str
    input_refs: tuple[str, ...] = ()
    process: str
    output: str
    report_claim_refs: tuple[str, ...] = ()


class RunRecovery(FrozenWireModel):
    attempt_id: str
    original_terminal_state: Literal["FAILED"]
    failure_stage: str
    authorized_by: Literal["OWNER"]
    resume_from: Literal["Release"]
    reused_artifacts: tuple[str, ...]
    reexecuted_stages: tuple[str, ...]
    new_model_calls: int = Field(ge=0)
    new_calculations: int = Field(ge=0)
    new_proof_calls: int = Field(ge=0)
    final_state: str
    memory_status: str


class ResultsSemantics(FrozenWireModel):
    schema_version: Literal["phase6a-results-semantics/v1"] = "phase6a-results-semantics/v1"
    run_id: str
    object_id: str
    company_name: str
    symbol: str
    as_of: str
    result_id: str
    review_id: str
    review_status: str
    publication: Literal["RELEASED", "RELEASED_WITH_LIMITATIONS"]
    limitations: tuple[str, ...]
    blocks: tuple[Block, ...]
    checks: tuple[Check, ...]
    records: tuple[Record, ...]
    categories: tuple[str, ...] = CATEGORIES
    recovery: RunRecovery | None
    memory_refs: tuple[str, ...]
    html_artifact_id: str
    legacy_export: bool

    @model_validator(mode="after")
    def close_refs(self):
        def validate_public(value):
            if isinstance(value, str):
                safe_text(value, context="Results semantic field", allow_empty=True)
            elif isinstance(value, dict):
                for child in value.values():
                    validate_public(child)
            elif isinstance(value, (list, tuple)):
                if len(value) > 20000:
                    raise ValueError("Unbounded Results collection")
                for child in value:
                    validate_public(child)

        validate_public(self.model_dump(mode="json"))
        known = {r.ref for r in self.records}
        if len(known) != len(self.records):
            raise ValueError("Ambiguous execution identities")
        claims = {b.claim_id for b in self.blocks}
        selectors = {(c.selector.check_code, c.selector.subject_refs) for c in self.checks}
        passed = {
            (c.selector.check_code, c.selector.subject_refs)
            for c in self.checks
            if c.status == "PASS"
        }
        if len(selectors) != len(self.checks) or len(claims) != len(self.blocks):
            raise ValueError("Ambiguous review or claim identities")
        for record in self.records:
            if record.category not in CATEGORIES or not set(record.input_refs) <= known:
                raise ValueError("Foreign execution inputs")
            if not set(record.report_claim_refs) <= claims:
                raise ValueError("Unobserved report contribution")
        for check in self.checks:
            if check.selector.review_id != self.review_id or not set(check.execution_refs) <= known:
                raise ValueError("Foreign review execution target")
        for block in self.blocks:
            if block.calculation_id not in known or not set(block.evidence_refs) <= known:
                raise ValueError("Foreign material block input")
            if not set(block.execution_refs) <= known or not block.review_selectors:
                raise ValueError("Unreviewed material block")
            if any(
                s.review_id != self.review_id or (s.check_code, s.subject_refs) not in passed
                for s in block.review_selectors
            ):
                raise ValueError("Foreign material block review")
        if not set(self.memory_refs) <= known:
            raise ValueError("Foreign Memory identity")
        if self.recovery and not set(self.recovery.reused_artifacts) <= known:
            raise ValueError("Foreign reused artifact")
        return self


def text(value):
    return safe_text(str(value), context="Results semantic display")


COMPARISON_FIELDS = frozenset(
    {
        "value",
        "formula_id",
        "formula_ids",
        "tolerance",
        "status",
        "bound_to_evidence",
        "input_count",
        "resolved_input_count",
        "count",
        "unique_count",
        "unique",
        "calculations",
        "claims",
        "metrics",
        "metric_id",
        "must_prove_formula",
        "required_calculation_ids",
        "run_id",
        "implementation_hash",
    }
)


def compare(expected, actual):
    def display(value):
        if value is None:
            return None
        return text(
            json.dumps(value, ensure_ascii=False, sort_keys=True)
            if isinstance(value, (dict, list, bool))
            else value
        )

    return tuple(
        Comparison(field=k, expected=display(expected.get(k)), actual=display(actual.get(k)))
        for k in sorted((expected.keys() | actual.keys()) & COMPARISON_FIELDS)
    )


def build_semantics(aggregate, obj, events, adaptive, audits, memories):
    run, art = aggregate.run, aggregate.artifacts
    run_id = run.run_id
    released, review, canonical = art.released_result, art.review, art.canonical_record
    if run.status.value != "RELEASED" or not released or not review or not canonical:
        raise product_error("NOT_RELEASED", "Semantic Results require an exact released Run")
    if (
        released.run_id != run_id
        or review.run_id != run_id
        or canonical.run_id != run_id
        or released.canonical_record_id != canonical.record_id
        or canonical.object_snapshot_ref != run.research_object_id
        or review.status.value != "PASS"
        or review.review_id not in canonical.review_refs
    ):
        raise ValueError("Canonical identity mismatch")
    terminal = validate_event_log(run_id, events)
    if terminal is None or terminal.payload.get("status") != "RELEASED":
        raise ValueError("Released event closure is missing")
    retained_review_surface(run, art, aggregate.runtime.actual_graph.tasks)
    if aggregate.goal.goal_id != run.goal_id or aggregate.scheme.scheme_id != run.scheme_id:
        raise ValueError("Confirmed intent identity mismatch")
    if review.reviewer == "independent-financial-review-v2":
        snapshot = financial_review_input_snapshot_hash(
            run_id=run_id,
            run_as_of=run.as_of,
            evidence=art.evidence,
            calculations=art.calculations,
            metrics=released.released_metrics,
            claims=released.material_claims,
            judgments=art.judgments,
            proof_requirements={
                c.calculation_id: ProofRequirement.MUST_PROVE
                if c.calculation_id in review.required_proof_calculation_refs
                else ProofRequirement.NOT_REQUIRED
                for c in art.calculations
            },
            requirement_context=review.requirement_context,
        )
        if snapshot != review.input_snapshot_hash:
            raise ValueError("Released material differs from exact reviewed inputs")
    for items, key in (
        (aggregate.runtime.actual_graph.tasks, "task_id"),
        (art.calculations, "calculation_id"),
        (art.evidence, "evidence_id"),
        (art.agent_outputs, "output_id"),
        (released.released_metrics, "metric_id"),
        (released.material_claims, "claim_id"),
    ):
        if len({getattr(item, key) for item in items}) != len(items):
            raise ValueError("Ambiguous retained identity")
    records = []

    def add(ref, category, label, status, process, output, inputs=(), claims=()):
        records.append(
            Record(
                ref=ref,
                category=category,
                label=text(label),
                status=text(status),
                process=text(process),
                output=text(output),
                input_refs=tuple(inputs),
                report_claim_refs=tuple(claims),
            )
        )

    add(
        aggregate.goal.goal_id,
        CATEGORIES[0],
        "Research Goal",
        "CONFIRMED",
        "Confirmed research intent",
        aggregate.goal.goal_text,
    )
    add(
        aggregate.scheme.scheme_id,
        CATEGORIES[0],
        "Research Scheme",
        "CONFIRMED",
        "Persisted Scheme",
        aggregate.scheme.scheme_id,
    )
    tasks = {t.task_id: t for t in aggregate.runtime.actual_graph.tasks}
    calculations = {c.calculation_id: c for c in art.calculations}
    evidence = {e.evidence_id: e for e in art.evidence}
    metrics = {m.metric_id: m for m in released.released_metrics}
    claims = {c.claim_id: c for c in released.material_claims}
    event_index = {e.event_id: e for e in events}
    if len(event_index) != len(events):
        raise ValueError("Ambiguous events")
    calculation_events = {}
    for event in events:
        if event.type.value != "calculation.completed":
            continue
        cid = event.payload.get("calculation_id")
        calc = calculations.get(cid)
        if calc is None or event.task_id != calc.task_id or cid in calculation_events:
            raise ValueError("Ambiguous or foreign calculation event")
        if event.payload.get("capability_id", calc.capability_id) != calc.capability_id:
            raise ValueError("Calculation event capability mismatch")
        calculation_events[cid] = event.event_id
    calculation_claims = {
        cid: tuple(c.claim_id for c in claims.values() if cid in c.calculation_refs)
        for cid in calculations
    }
    for task in tasks.values():
        if task.run_id != run_id:
            raise ValueError("Foreign task")
        add(
            task.task_id,
            CATEGORIES[1],
            task.task_type,
            task.status.value,
            "Retained Task · " + (task.assigned_agent or "unassigned"),
            task.result_ref or "No completed output",
        )
    for item in evidence.values():
        if item.run_id != run_id:
            raise ValueError("Foreign evidence")
        add(
            item.evidence_id,
            CATEGORIES[2],
            item.provider + " · " + item.normalized_field,
            "RETAINED",
            "Accepted evidence · " + item.period,
            str(item.normalized_value),
        )
    for calc in calculations.values():
        if (
            calc.run_id != run_id
            or calc.task_id not in tasks
            or not set(calc.input_evidence_ids) <= evidence.keys()
        ):
            raise ValueError("Foreign calculation")
        add(
            calc.calculation_id,
            CATEGORIES[3],
            calc.capability_id,
            calc.status.value,
            calc.formula_id,
            str(calc.output_value) + " " + calc.output_unit,
            calc.input_evidence_ids,
            calculation_claims[calc.calculation_id],
        )
    for output in art.agent_outputs:
        if output.run_id != run_id or output.task_id not in tasks:
            raise ValueError("Foreign AgentOutput")
        task = tasks[output.task_id]
        if task.assigned_agent != output.actor or (
            output.status == "SUCCESS" and task.result_ref != output.artifact_ref
        ):
            raise ValueError("AgentOutput task binding mismatch")
        summary = (
            output.structured_output.summary if output.structured_output else "No successful output"
        )
        add(
            output.output_id,
            CATEGORIES[1],
            output.actor,
            output.status,
            "Observable AgentOutput · model " + (output.actual_model or "not observed"),
            summary,
            (output.task_id,),
        )
    for proof in art.proofs:
        if proof.run_id != run_id or proof.calculation_id not in calculations:
            raise ValueError("Foreign Proof")
        add(
            proof.proof_id,
            CATEGORIES[6],
            "Proof",
            proof.status.value,
            "Retained verification; no new proving",
            proof.receipt_hash or proof.status.value,
            (proof.calculation_id,),
        )
    add(
        review.review_id,
        CATEGORIES[5],
        "Financial Review",
        review.status.value,
        review.reviewer,
        f"{len(review.checks)} persisted checks",
        review.reviewed_calculation_refs,
    )
    for item in adaptive:
        if item.scope.object_id != run.research_object_id or item.scope.scheme_id != run.scheme_id:
            raise ValueError("Foreign recovery intent")
        if item.scope.run_id != run_id or item.scope.task_id not in tasks:
            raise ValueError("Foreign recovery attempt")
        add(
            item.record_id,
            CATEGORIES[4],
            item.kind,
            item.outcome,
            f"{item.provider or 'policy'} / {item.model or 'not recorded'}"
            f" → {item.actual_model or 'not observed'}",
            str(item.failure_class or item.policy_gate_result or item.reason_code),
            (item.scope.task_id,),
        )
    for event in events:
        category = (
            CATEGORIES[0]
            if event.type.value.startswith(("plan.", "scheme."))
            else CATEGORIES[5]
            if event.type.value.startswith("review.")
            else CATEGORIES[6]
            if event.type.value.startswith("proof.")
            else CATEGORIES[7]
            if event.type.value in {"release.completed", "run.completed"}
            else CATEGORIES[4]
        )
        if event.type.value == "calculation.completed":
            calc = calculations[event.payload["calculation_id"]]
            add(
                event.event_id,
                CATEGORIES[3],
                "Calculation completed · " + calc.capability_id,
                calc.status.value,
                calc.formula_id,
                str(calc.output_value) + " " + calc.output_unit,
                (calc.calculation_id,),
                calculation_claims[calc.calculation_id],
            )
            continue
        add(
            event.event_id,
            category,
            event.type.value,
            str(event.payload.get("status", "OBSERVED")),
            "Persisted event · sequence " + str(event.sequence),
            str(event.payload.get("failure_code", event.type.value)),
            (event.task_id,) if event.task_id in tasks else (),
        )
    add(
        canonical.record_id,
        CATEGORIES[7],
        "Canonical Execution",
        "RELEASED",
        "Exact release gate",
        canonical.record_id,
    )
    add(
        released.result_id,
        CATEGORIES[7],
        "Released Result",
        "RELEASED",
        "Reviewed material claims",
        released.result_id,
        (canonical.record_id, review.review_id),
    )
    html = [a for a in art.report_artifacts if a.artifact_type == "text/html"]
    if (
        len(html) != 1
        or html[0].run_id != run_id
        or html[0].released_result_id != released.result_id
    ):
        raise ValueError("Exact HTML report missing")
    for artifact in art.report_artifacts:
        if artifact.run_id != run_id or artifact.released_result_id != released.result_id:
            raise ValueError("Foreign report artifact")
        add(
            artifact.artifact_id,
            CATEGORIES[7],
            "Report " + artifact.artifact_type,
            "GENERATED",
            artifact.renderer_version,
            artifact.content_hash,
            (released.result_id,),
        )
    memory_refs = []
    for memory in memories:
        if memory.source_run_id != run_id or memory.research_object_id != run.research_object_id:
            raise ValueError("Foreign Memory")
        memory_refs.append(memory.research_view_version_id)
        add(
            memory.research_view_version_id,
            CATEGORIES[7],
            "Research Memory",
            "MATERIALIZED",
            "Released research view · version " + str(memory.research_view_version),
            memory.research_view_version_id,
            (released.result_id,),
        )
    checks = []
    for check in review.checks:
        calc_refs = set(check.subject_refs) & calculations.keys()
        for ref in check.subject_refs:
            if ref in claims:
                calc_refs.update(claims[ref].calculation_refs)
            if ref in metrics:
                calc_refs.add(metrics[ref].calculation_id)
        targets = tuple(
            calculation_events[cid] for cid in sorted(calc_refs) if cid in calculation_events
        )
        checks.append(
            Check(
                selector=ReviewCheckSelectorV1(
                    review_id=review.review_id,
                    check_code=check.code,
                    subject_refs=tuple(check.subject_refs),
                ),
                status=check.status.value,
                comparison=compare(check.expected, check.actual),
                execution_refs=targets,
            )
        )
    blocks = []
    for claim in claims.values():
        if claim.claim_id not in review.reviewed_claim_refs or claim.metric_id not in metrics:
            raise ValueError("Unreviewed report claim")
        metric = metrics[claim.metric_id]
        cid = metric.calculation_id
        if cid not in claim.calculation_refs or cid not in calculations:
            raise ValueError("Wrong claim calculation")
        selectors = tuple(
            c.selector
            for c in checks
            if claim.claim_id in c.selector.subject_refs and c.status == "PASS"
        )
        targets = (calculation_events[cid],) if cid in calculation_events else ()
        blocks.append(
            Block(
                claim_id=claim.claim_id,
                metric_id=metric.metric_id,
                title=text(metric.name),
                statement=text(claim.statement),
                calculation_id=cid,
                evidence_refs=tuple(metric.evidence_ids),
                review_selectors=selectors,
                execution_refs=targets,
            )
        )
    recovery = project_recovery(aggregate, events, audits, records, memory_refs)
    if recovery:
        add(
            recovery.attempt_id,
            CATEGORIES[4],
            "Owner-authorized closure recovery",
            recovery.final_state,
            "FAILED → Release → Report → Memory",
            "Reused assurance; no new model/calculation/Proof",
            recovery.reused_artifacts,
        )
    limitations = tuple(text(v) for v in released.limitations)
    return ResultsSemantics(
        run_id=run_id,
        object_id=run.research_object_id,
        company_name=text(obj["company_name"]),
        symbol=text(obj["symbol"]),
        as_of=run.as_of.isoformat(),
        result_id=released.result_id,
        review_id=review.review_id,
        review_status=review.status.value,
        publication="RELEASED_WITH_LIMITATIONS" if limitations else "RELEASED",
        limitations=limitations,
        blocks=tuple(blocks),
        checks=tuple(checks),
        records=tuple(records),
        recovery=recovery,
        memory_refs=tuple(memory_refs),
        html_artifact_id=html[0].artifact_id,
        legacy_export="reviewed-claims" not in html[0].renderer_version,
    )


def project_recovery(aggregate, events, audits, records, memories):
    if not audits:
        return None
    by_kind = {r.kind: r.payload for r in audits}
    if len(by_kind) != len(audits) or "STARTED" not in by_kind:
        raise ValueError("Ambiguous recovery history")
    start = by_kind["STARTED"]
    attempt_id = start["attempt_id"]
    if any(
        r.run_id != aggregate.run.run_id or r.payload.get("attempt_id") != attempt_id
        for r in audits
    ):
        raise ValueError("Foreign recovery audit")
    original = start["failed_snapshot"]
    if (
        fingerprint(original) != start["snapshot_hash"]
        or original["run"]["status"] != "FAILED"
        or original["run"]["run_id"] != aggregate.run.run_id
        or start["owner_authorization"]
        != "REUSE_REVIEW_AND_VERIFIED_PROOF_RELEASE_REPORT_MEMORY_ONCE"
    ):
        raise ValueError("Invalid recovery authorization snapshot")
    boundary = [e for e in events if e.type.value == "closure.recovery_started"]
    if len(boundary) != 1 or boundary[0].payload["attempt_id"] != attempt_id:
        raise ValueError("Missing recovery boundary")
    if (
        boundary[0].payload["snapshot_hash"] != start["snapshot_hash"]
        or boundary[0].payload["failed_event_id"] != start["failed_event_id"]
    ):
        raise ValueError("Recovery boundary snapshot mismatch")
    prefix = [e for e in events if e.sequence < boundary[0].sequence]
    if (
        not prefix
        or prefix[-1].event_id != start["failed_event_id"]
        or fingerprint([e.model_dump(mode="json") for e in prefix]) != start["event_hash"]
    ):
        raise ValueError("Failure history changed")
    released = by_kind.get("RELEASED")
    if released is None:
        raise ValueError("Released Run lacks recovery release audit")
    if released["projection_sequence"] != events[-1].sequence:
        raise ValueError("Recovery projection sequence mismatch")
    if original["artifacts"]["review"] != aggregate.artifacts.review.model_dump(mode="json"):
        raise ValueError("Reused Review changed")
    current = aggregate.artifacts
    for name in ("evidence", "agent_outputs"):
        if original["artifacts"][name] != [
            v.model_dump(mode="json") for v in getattr(current, name)
        ]:
            raise ValueError("Reused inputs changed")
    for name in ("goal", "scheme"):
        if original[name] != getattr(aggregate, name).model_dump(mode="json"):
            raise ValueError("Confirmed recovery intent changed")
    lineage = {"review_status", "review_record_id", "canonical_record_id", "proof_ref"}
    before = [
        {k: v for k, v in c.items() if k not in lineage}
        for c in original["artifacts"]["calculations"]
    ]
    after = [
        {k: v for k, v in c.model_dump(mode="json").items() if k not in lineage}
        for c in current.calculations
    ]
    if before != after or any(
        released[k] != 0 for k in ("model_calls", "calculation_calls", "proof_calls")
    ):
        raise ValueError("Closure-only recovery contract changed")
    reused = [c["calculation_id"] for c in original["artifacts"]["calculations"]]
    reused += [original["artifacts"]["review"]["review_id"]]
    reused += [p.proof_id for p in aggregate.artifacts.proofs]
    reused += [
        o["output_id"] for o in original["artifacts"]["agent_outputs"] if o["status"] == "SUCCESS"
    ]
    return RunRecovery(
        attempt_id=attempt_id,
        original_terminal_state="FAILED",
        failure_stage=text(prefix[-1].payload["failure_stage"]),
        authorized_by="OWNER",
        resume_from="Release",
        reused_artifacts=tuple(reused),
        reexecuted_stages=("Release", "Report", "Memory")
        if "COMPLETED" in by_kind and memories
        else ("Release", "Report"),
        new_model_calls=released["model_calls"],
        new_calculations=released["calculation_calls"],
        new_proof_calls=released["proof_calls"],
        final_state=aggregate.run.status.value,
        memory_status="MATERIALIZED" if "COMPLETED" in by_kind and memories else "NOT_MATERIALIZED",
    )


async def read_semantics(sessions, run_id):
    from src.phase4_product.memory_contracts import ResearchViewVersion

    async with sessions() as session, session.begin():
        row = await session.get(ResearchRunAggregateRow, run_id)
        if row is None:
            raise product_error("NOT_FOUND", "Research Run not found")
        aggregate = SQLAlchemyApplicationRepository._to_aggregate(row.payload)
        obj = await session.get(ResearchObjectRow, row.object_id)
        if (
            obj is None
            or aggregate.run.run_id != run_id
            or aggregate.run.research_object_id != row.object_id
            or obj.payload.get("object_id") != row.object_id
        ):
            raise ValueError("Requested Run identity mismatch")

        async def owned(row_type, field="run_id"):
            rows = list(
                await session.scalars(select(row_type).where(getattr(row_type, field) == run_id))
            )
            for child in rows:
                for key in ("event_id", "sequence", "record_id", "research_view_version_id"):
                    if hasattr(child, key) and key in child.payload:
                        if getattr(child, key) != child.payload[key]:
                            raise ValueError("Stored row identity mismatch")
            return rows

        events = sorted(
            [RuntimeEvent.model_validate(r.payload) for r in await owned(RuntimeEventRow)],
            key=lambda e: e.sequence,
        )
        adaptive = [
            RecoveryEvidence.model_validate(r.payload) for r in await owned(RecoveryEvidenceRow)
        ]
        audits = await owned(ClosureRecoveryRecordRow)
        if audits:
            outcome, manifest_hash = await retained_proof_outcome(session, aggregate)
            starts = [r for r in audits if r.kind == "STARTED"]
            if len(starts) != 1 or starts[0].payload["proof_manifest_hash"] != manifest_hash:
                raise ValueError("Reused Proof manifest changed")
            if {p.proof_id: p for p in aggregate.artifacts.proofs} != {
                p.proof_id: p for p in outcome.proofs.values()
            }:
                raise ValueError("Retained Proof payload changed")
        memories = [
            ResearchViewVersion.model_validate(r.payload)
            for r in await owned(ResearchViewVersionRow, "source_run_id")
        ]
        return build_semantics(aggregate, obj.payload, events, adaptive, audits, memories)
