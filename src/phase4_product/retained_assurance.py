"""Read-only, exact-Run assurance existence independent of release availability."""

from src.assurance.independent_financial_review import financial_review_input_snapshot_hash
from src.domain.enums import ProofRequirement
from src.domain.financial_branch import BRANCH_FORMULAS, BranchStatus
from src.domain.proof import ProofRecord
from src.output.financial_metrics import build_material_financial_release
from src.phase4_product.results import ResultsIdentityError, build_financial_review_surface


def retained_review_surface(run, artifacts, tasks):
    review = artifacts.review
    if review is None or review.run_id != run.run_id:
        raise ResultsIdentityError("Retained Review identity is missing or foreign")
    children = (
        *artifacts.evidence,
        *artifacts.calculations,
        *artifacts.agent_outputs,
        *(p for p in artifacts.proofs if isinstance(p, ProofRecord)),
        *artifacts.financial_branches,
        *tasks,
    )
    if any(item.run_id != run.run_id for item in children):
        raise ResultsIdentityError("Retained assurance child belongs to another Run")
    refs = {
        run.run_id,
        run.research_object_id,
        run.goal_id,
        run.scheme_id,
        review.review_id,
        *(t.task_id for t in tasks),
        *(e.evidence_id for e in artifacts.evidence),
        *(c.calculation_id for c in artifacts.calculations),
        *(b.branch_id for b in artifacts.financial_branches),
        *(p.proof_id for p in artifacts.proofs),
    }
    metrics, claims = (), ()
    if review.reviewed_metric_refs or review.reviewed_claim_refs:
        metrics, claims, _ = build_material_financial_release(
            run_id=run.run_id,
            evidence=artifacts.evidence,
            calculations=artifacts.calculations,
            judgments=artifacts.judgments,
            unavailable_formulas=frozenset(
                f
                for b in artifacts.financial_branches
                if b.status in {BranchStatus.INSUFFICIENT_DATA, BranchStatus.BLOCKED_BY_RUNTIME}
                for f in BRANCH_FORMULAS[b.calculation_type]
            ),
        )
        refs.update(m.metric_id for m in metrics)
        refs.update(c.claim_id for c in claims)
    for judgment in artifacts.judgments:
        if judgment.get("run_id") != run.run_id:
            raise ResultsIdentityError("Judgment belongs to another Run")
        refs.add(judgment["judgment_id"])
    for retained, known in (
        (review.reviewed_evidence_refs, {e.evidence_id for e in artifacts.evidence}),
        (review.reviewed_calculation_refs, {c.calculation_id for c in artifacts.calculations}),
        (review.reviewed_metric_refs, {m.metric_id for m in metrics}),
        (review.reviewed_claim_refs, {c.claim_id for c in claims}),
        (review.reviewed_judgment_refs, {j["judgment_id"] for j in artifacts.judgments}),
        (
            review.required_proof_calculation_refs,
            {c.calculation_id for c in artifacts.calculations},
        ),
    ):
        if not set(retained).issubset(known):
            raise ResultsIdentityError("Review reference has wrong type or identity")
    if review.reviewer == "independent-financial-review-v2":
        requirements = {
            c.calculation_id: ProofRequirement.MUST_PROVE
            if c.calculation_id in review.required_proof_calculation_refs
            else ProofRequirement.NOT_REQUIRED
            for c in artifacts.calculations
        }
        snapshot = financial_review_input_snapshot_hash(
            run_id=run.run_id,
            run_as_of=run.as_of,
            evidence=artifacts.evidence,
            calculations=artifacts.calculations,
            metrics=metrics,
            claims=claims,
            judgments=artifacts.judgments,
            proof_requirements=requirements,
            requirement_context=review.requirement_context,
        )
        if snapshot != review.input_snapshot_hash:
            raise ResultsIdentityError("Review input snapshot differs from retained inputs")
    return build_financial_review_surface(
        expected_run_id=run.run_id,
        expected_object_id=run.research_object_id,
        review=review,
        canonical_record=None,
        released_result=None,
        authoritative_subject_refs=refs,
    )


def validate_retained_proofs(run, artifacts):
    calculations = {c.calculation_id for c in artifacts.calculations if c.run_id == run.run_id}
    if any(
        p.run_id != run.run_id or p.calculation_id not in calculations
        for p in artifacts.proofs
        if isinstance(p, ProofRecord)
    ):
        raise ResultsIdentityError("Proof does not bind an exact retained calculation")
