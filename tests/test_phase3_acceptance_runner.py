import json
import subprocess
from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

import scripts.run_phase3_acceptance as acceptance_runner
from scripts.run_phase3_acceptance import (
    _aggregate_snapshot,
    _candidate_preflight,
    _credential_needles,
    _expected_core_gate_ids,
    _expected_financial_semantic_gate_ids,
    _failure_matrix,
    _financial_review_negative_checks,
    _integration_matrix,
    _report_content_matches_metrics,
    _require_formal_mode,
    _resolve_safe_path,
    _scan_artifacts_for_credentials,
)
from src.adapters.finrobot import FINROBOT_PINNED_COMMIT, PinnedFinRobotAdapter
from src.adapters.finrobot.charts import (
    CanonicalReportChartAdapter,
    DeterministicSVGChartBackend,
)
from src.adapters.finrobot.professional_reporting import (
    ControlledArtifactStore,
    ProfessionalReportPublisher,
)
from src.domain.enums import FinancialActuality, FinancialPeriodBasis, FinancialUnit
from src.domain.financial_semantics import ReleasedFinancialMetric
from src.domain.financial_validation import REVENUE_GROWTH_VALIDATION_REASON
from src.domain.report import CanonicalReportDTO
from src.domain.review import ReviewCheck
from src.infrastructure.config import Settings


def _settings() -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://user:database-password@example.test/db",
        fmp_api_key="fmp-credential-value",
        teamorouter_api_key="llm-credential-value",
        mimo_api_key="mimo-credential-value",
        langfuse_public_key="langfuse-public-value",
        langfuse_secret_key="langfuse-secret-value",
    )


def test_artifact_secret_scan_detects_configured_value_without_returning_it(
    tmp_path: Path,
) -> None:
    settings = _settings()
    needles = _credential_needles(settings)
    (tmp_path / "safe.json").write_text('{"status":"PASS"}', encoding="utf-8")
    clean = _scan_artifacts_for_credentials(
        tmp_path,
        needles=needles,
        pending_summary={"status": "RUNNING"},
    )
    assert clean == {"passed": True, "match_count": 0, "scanned_files": 1}

    (tmp_path / "unsafe.bin").write_bytes(b"prefix-fmp-credential-value-suffix")
    finding = _scan_artifacts_for_credentials(
        tmp_path,
        needles=needles,
        pending_summary={"status": "RUNNING"},
    )
    assert finding["passed"] is False
    assert finding["match_count"] == 1
    assert all(
        secret.get_secret_value() not in repr(finding)
        for secret in (
            settings.fmp.api_key,
            settings.llm.api_key,
            settings.mimo.api_key,
            settings.langfuse.public_key,
            settings.langfuse.secret_key,
        )
        if secret is not None
    )


def test_safe_path_rejects_symlink_leaf(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)

    with pytest.raises(RuntimeError, match="unsafe acceptance path"):
        _resolve_safe_path(link, label="acceptance path")


def test_exact_formal_phase3_gate_identity() -> None:
    gate_ids = _expected_core_gate_ids()
    assert len(gate_ids) == 52
    assert {item for item in gate_ids if item.startswith("P3-CAP-")} == {
        f"P3-CAP-{index:03d}" for index in range(1, 17)
    }
    assert {item for item in gate_ids if item.startswith("P3-ZK-")} == {
        f"P3-ZK-{index:03d}" for index in range(1, 15)
    }
    assert {item for item in gate_ids if item.startswith("P3-FIN-")} == {
        f"P3-FIN-{index:03d}" for index in range(1, 13)
    }
    assert {item for item in gate_ids if item.startswith("P3-INT-")} == {
        f"P3-INT-{index:03d}" for index in range(1, 11)
    }
    assert _expected_financial_semantic_gate_ids() == {f"FS-{index:03d}" for index in range(1, 14)}


def test_integration_gate_failure_participates_in_decision() -> None:
    passed = {"status": "PASS", "evidence": {}}
    failed = {"status": "FAIL", "evidence": {}}
    capability = {f"P3-CAP-{index:03d}": passed for index in range(1, 17)}
    proof = {f"P3-ZK-{index:03d}": passed for index in range(1, 15)}
    financial = {f"P3-FIN-{index:03d}": passed for index in range(1, 13)}
    capability["P3-CAP-009"] = failed
    matrix = _integration_matrix(
        run_id="RUN-1",
        regressions={
            "phase1": {"passed": True},
            "phase2": {"passed": True},
            "phase2_1": {"passed": True},
        },
        phase2_1_semantic_failed=[],
        postgresql={"passed": True},
        langfuse={"passed": True},
        capability_matrix=capability,
        proof_matrix=proof,
        financial_matrix=financial,
        proof_ids=["PROOF-1"],
        report_artifacts=[],
        security={"passed": True},
        restore={"passed": True},
    )
    assert matrix["P3-INT-006"]["status"] == "FAIL"


def test_failure_matrix_is_exact_and_preserves_completed_regression_evidence() -> None:
    matrix = _failure_matrix(
        run_id="RUN-FAIL",
        audit_state={
            "failed_stage": "postgresql_migration",
            "regressions": {
                "phase1": {"passed": True, "stdout_sha256": "sha256:one"},
                "phase2": {"passed": False, "stdout_sha256": "sha256:two"},
                "phase2_1": {"passed": True, "stdout_sha256": "sha256:three"},
            },
        },
        error_type="RuntimeError",
    )
    assert set(matrix) == _expected_core_gate_ids()
    assert matrix["P3-INT-001"]["status"] == "PASS"
    assert matrix["P3-INT-002"]["status"] == "FAIL"
    assert matrix["P3-INT-003"]["status"] == "PASS"
    assert matrix["P3-INT-004"]["status"] == "FAIL"
    assert matrix["P3-INT-010"]["status"] == "FAIL"


def test_financial_review_evidence_negatives_never_replace_calculation_with_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Copyable(SimpleNamespace):
        def model_copy(self, *, update: dict[str, object]) -> "Copyable":
            return Copyable(**{**vars(self), **update})

    prior = Copyable(
        evidence_id="E-PRIOR",
        period="FY2025",
        normalized_field="revenue",
        statement_cohort="COHORT-2025",
        unit="USD",
        currency="USD",
    )
    current = Copyable(
        evidence_id="E-CURRENT",
        period="FY2026",
        normalized_field="revenue",
        statement_cohort="COHORT-2026",
        unit="USD",
        currency="USD",
    )
    ebitda = Copyable(
        evidence_id="E-EBITDA",
        period="FY2026",
        normalized_field="ebitda",
        statement_cohort="COHORT-2026",
        unit="USD",
        currency="USD",
    )
    growth = Copyable(
        calculation_id="CALC-GROWTH",
        formula_id="revenue_growth_v1",
        input_evidence_ids=[prior.evidence_id, current.evidence_id],
        output_value=Decimal("0.25"),
    )
    margin = Copyable(
        calculation_id="CALC-MARGIN",
        formula_id="ebitda_margin_v1",
        input_evidence_ids=[ebitda.evidence_id, current.evidence_id],
        output_value=Decimal("0.50"),
    )
    aggregate = SimpleNamespace(
        run=SimpleNamespace(run_id="RUN-1", as_of=date(2026, 9, 4)),
        artifacts=SimpleNamespace(
            evidence=[prior, current, ebitda],
            calculations=[growth, margin],
            released_result=SimpleNamespace(released_metrics=(), material_claims=()),
            judgments=[],
        ),
    )

    class Reviewer:
        def review(self, **kwargs: object) -> SimpleNamespace:
            calculations = kwargs["calculations"]
            assert isinstance(calculations, list)
            assert calculations and all(item is not None for item in calculations)
            return SimpleNamespace(
                status=acceptance_runner.ReviewStatus.BLOCK,
                checks=[
                    ReviewCheck(
                        code="FIN_CALCULATION_RECOMPUTATION",
                        status=acceptance_runner.ReviewStatus.BLOCK,
                        detail=REVENUE_GROWTH_VALIDATION_REASON,
                    )
                ],
            )

    monkeypatch.setattr(acceptance_runner, "IndependentFinancialReviewer", Reviewer)
    checks = _financial_review_negative_checks(
        aggregate=aggregate,
        proof_requirements={},
    )
    assert checks == {
        "period_mismatch_blocked": True,
        "unit_mismatch_blocked": True,
        "currency_mismatch_blocked": True,
        "cohort_mismatch_blocked": True,
        "calculation_tamper_blocked": True,
        "zero_prior_blocked": True,
        "zero_prior_reason_stable": True,
        "negative_prior_blocked": True,
        "negative_prior_reason_stable": True,
    }


@pytest.mark.asyncio
async def test_authoritative_run_failure_writes_sanitized_complete_matrix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_authoritative(*args: object, **kwargs: object) -> dict[str, object]:
        del args
        state = kwargs["audit_state"]
        assert isinstance(state, dict)
        state["failed_stage"] = "postgresql_migration"
        state["regressions"] = {
            "phase1": {"passed": True},
            "phase2": {"passed": True},
            "phase2_1": {"passed": True},
        }
        raise RuntimeError("sensitive-upstream-message-must-not-be-persisted")

    monkeypatch.setattr(acceptance_runner, "_repository_root", lambda: tmp_path)
    monkeypatch.setattr(acceptance_runner, "_run_authoritative", fail_authoritative)
    output_root = tmp_path / "artifacts" / "phase3" / "acceptance"
    with pytest.raises(RuntimeError, match="sensitive-upstream"):
        await acceptance_runner.run(
            output_root,
            host_binary=tmp_path / "unused-host",
            candidate_head="a" * 40,
        )

    run_directories = list(output_root.iterdir())
    assert len(run_directories) == 1
    matrix_path = run_directories[0] / "acceptance_matrix.json"
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    assert set(matrix) == _expected_core_gate_ids()
    assert all(f"P3-INT-{index:03d}" in matrix for index in range(1, 11))
    assert matrix["P3-INT-001"]["status"] == "PASS"
    assert matrix["P3-INT-004"]["status"] == "FAIL"
    persisted = (run_directories[0] / "phase3_acceptance.json").read_text(encoding="utf-8")
    assert "sensitive-upstream-message" not in persisted


def test_formal_mode_rejects_dev_mode_presence_even_when_false_like() -> None:
    for value in ("0", "false", ""):
        with pytest.raises(RuntimeError, match="RISC0_DEV_MODE"):
            _require_formal_mode({"RISC0_DEV_MODE": value})


def test_candidate_preflight_binds_clean_full_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    subprocess.run(("git", "init", "-q"), cwd=tmp_path, check=True)
    subprocess.run(
        ("git", "config", "user.email", "phase3@example.test"),
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(("git", "config", "user.name", "Phase 3 Test"), cwd=tmp_path, check=True)
    required = (
        "alembic/versions/20260904_0004_phase3_capability_proof_artifacts.py",
        "alembic/versions/20260904_0005_financial_evidence_semantics.py",
        "alembic/versions/20260904_0006_generated_capability_artifact_retention.py",
        "scripts/run_phase3_acceptance.py",
        "src/adapters/llm/mimo.py",
        "src/adapters/llm/router.py",
        "src/capabilities/generated/artifacts.py",
        "src/domain/financial_validation.py",
        "src/domain/macd_policy.py",
        "src/infrastructure/database/generated_workflow.py",
        "src/observability/langfuse_adapter.py",
        "docs/PHASE3_INDEPENDENT_AUDIT_REMEDIATION.md",
        "docs/PHASE3_PLANNER_PROVIDER_ROUTER_REMEDIATION.md",
        "tests/unit/generated/test_artifact_retention.py",
        "src/adapters/risc0/release_manifest.py",
        "tests/test_phase3_acceptance_runner.py",
        "tests/unit/llm/test_planner_provider_router.py",
        "zk/revenue_growth/RISC_ZERO_RELEASE_MANIFEST.json",
        "zk/revenue_growth/build-host.sh",
        "zk/revenue_growth/normalize_macos_host.py",
    )
    for relative in required:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("release-source\n", encoding="utf-8")
    subprocess.run(("git", "add", "."), cwd=tmp_path, check=True)
    subprocess.run(("git", "commit", "-qm", "candidate"), cwd=tmp_path, check=True)
    head = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    monkeypatch.setattr(
        acceptance_runner,
        "load_and_verify_release_manifest",
        lambda root: {
            "artifacts": {
                "host": {"sha256": acceptance_runner.EXPECTED_REVENUE_GROWTH_HOST_SHA256},
                "guest": {
                    "image_id": acceptance_runner.EXPECTED_REVENUE_GROWTH_IMAGE_ID,
                    "elf_sha256": "sha256:" + "1" * 64,
                    "combined_binary_sha256": "sha256:" + "2" * 64,
                },
            },
            "build": {
                "cargo_locked": True,
                "risc0_build_version": "3.0.6",
                "risc0_zkvm_version": "3.0.6",
            },
            "reproducibility": {
                "build_count": 2,
                "cross_absolute_path": True,
                "guest_combined_binary_equal": True,
                "guest_elf_equal": True,
                "host_binary_equal": True,
                "image_id_equal": True,
            },
            "source_closure": {"source_set_sha256": "sha256:" + "3" * 64},
        },
    )
    monkeypatch.setattr(
        acceptance_runner,
        "release_manifest_sha256",
        lambda path: "sha256:manifest",
    )
    candidate = _candidate_preflight(tmp_path, head)
    assert candidate["candidate_head"] == head
    assert candidate["worktree_clean"] is True
    assert candidate["source_fingerprint"].startswith("sha256:")
    assert len(candidate["source_fingerprint"]) == 71
    assert candidate["migration_chain"] == [
        "20260904_0004",
        "20260904_0005",
        "20260904_0006",
    ]

    (tmp_path / "untracked.txt").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="not clean"):
        _candidate_preflight(tmp_path, head)
    with pytest.raises(RuntimeError, match="does not match"):
        _candidate_preflight(tmp_path, head[:12])


@pytest.mark.asyncio
async def test_audited_trace_events_inherit_active_root_trace_id() -> None:
    class Handle:
        trace_id = "TRACE-ROOT"
        span_id = "SPAN-ROOT"

    class Delegate:
        @asynccontextmanager
        async def span(self, name: str, *, attributes: object = None):
            del name, attributes
            yield Handle()

        async def event(self, name: str, *, attributes: object = None) -> None:
            del name, attributes

    audited = acceptance_runner.AuditedTraceAdapter(Delegate())
    async with audited.span("vfas.run", attributes={"run_id": "RUN-1"}):
        await audited.event("vfas.proof.verified", attributes={"run_id": "RUN-1"})
    event = next(item for item in audited.observations if item["kind"] == "event")
    assert event["trace_id"] == "TRACE-ROOT"


def test_failure_envelope_refuses_to_overwrite_unknown_run_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(acceptance_runner, "_repository_root", lambda: tmp_path)
    output_root = tmp_path / "artifacts" / "phase3" / "acceptance"
    run_root = output_root / "RUN-COLLISION"
    run_root.mkdir(parents=True)
    marker = run_root / "existing.txt"
    marker.write_text("unchanged\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="refusing to overwrite"):
        acceptance_runner._write_failure_envelope(
            output_root=Path("artifacts/phase3/acceptance"),
            run_id="RUN-COLLISION",
            candidate_head="a" * 40,
            audit_state={"failed_stage": "runtime_output_preflight"},
            error_type="FileExistsError",
        )
    assert marker.read_text(encoding="utf-8") == "unchanged\n"


def test_aggregate_snapshot_serializes_dataclass_runtime_without_model_dump() -> None:
    class Dump:
        def __init__(self, value: object) -> None:
            self.value = value

        def model_dump(self, *, mode: str) -> object:
            assert mode == "json"
            return self.value

    aggregate = SimpleNamespace(
        run=Dump({"run_id": "RUN-1"}),
        goal=Dump({"goal_id": "GOAL-1"}),
        scheme=Dump({"scheme_id": "SCHEME-1"}),
        runtime=SimpleNamespace(
            planned_graph=Dump({"graph_id": "PLANNED"}),
            actual_graph=Dump({"graph_id": "ACTUAL"}),
            run_status=SimpleNamespace(value="RELEASED"),
            completed_output_refs={"TASK-1": ["OUTPUT-1"]},
            evidence_refs=["E-1"],
            workspace_refs=["W-1"],
            review_state={"status": "PASS"},
            proof_state={"status": "VERIFIED"},
            cost=0.0,
        ),
        artifacts=Dump({"calculations": [{"calculation_id": "CALC-1"}]}),
    )
    snapshot = _aggregate_snapshot(aggregate)
    assert snapshot["runtime"]["actual_graph"] == {"graph_id": "ACTUAL"}
    assert snapshot["runtime"]["run_status"] == "RELEASED"


@pytest.mark.asyncio
async def test_cross_view_content_contains_metric_value_unit_period_and_as_of(
    tmp_path: Path,
) -> None:
    metric = ReleasedFinancialMetric(
        metric_id="METRIC-GROWTH",
        calculation_id="CALC-GROWTH",
        name="Revenue Growth",
        canonical_value="0.654735",
        canonical_unit=FinancialUnit.RATIO,
        display_value="65.47",
        display_unit="%",
        period="FY2026",
        period_basis=FinancialPeriodBasis.FY,
        actuality=FinancialActuality.ACTUAL,
        as_of=date(2026, 1, 31),
        currency="USD",
        formula_id="revenue_growth_v1",
        capability_id="revenue_growth",
        evidence_ids=("E-PRIOR", "E-CURRENT"),
    )
    dto = CanonicalReportDTO(
        canonical_record_id="CAN-1",
        released_result_id="RESULT-1",
        run_id="RUN-1",
        research_object="NVDA",
        released_metrics=(metric,),
    )
    chart = await CanonicalReportChartAdapter(
        PinnedFinRobotAdapter(
            backend=DeterministicSVGChartBackend(tmp_path / "charts"),
            source_revision=FINROBOT_PINNED_COMMIT,
        )
    ).render(dto)
    store = ControlledArtifactStore(tmp_path / "reports")
    report = ProfessionalReportPublisher(store).publish(dto)
    assert _report_content_matches_metrics(
        metrics=(metric,),
        chart_path=Path(chart.record.artifact_ref),
        html_path=store.resolve(report.html.artifact_ref),
        pdf_path=store.resolve(report.pdf.artifact_ref),
    )
