"""Exercise existing confirmation/Resume/Replan controls with explicit report opt-in."""

import os

import pytest

from src.application.service import ResearchApplicationService
from src.domain.execution_profile import REPORT_METRIC_MARKER
from tests.phase4.backend_product.test_real_output_projection import database  # noqa: F401
from tests.risk_minimal import test_confirmation_authority as authority

pytestmark = pytest.mark.skipif(not os.environ.get("TEST_POSTGRESQL_URL"), reason="PostgreSQL")


@pytest.fixture
def opted_in(monkeypatch):
    original = ResearchApplicationService.prepare_run
    seen = []

    async def prepare(self, **kwargs):
        kwargs["preferences"] = {
            **kwargs["preferences"],
            "report_metric_requirements": {
                "schema_version": "frozen-report-metric-requirements/v1",
                "report_mode": "METRIC_FOCUSED",
                "required_metric_ids": ["revenue_growth_v1"],
                "period": "FY2026",
            },
        }
        draft = await original(self, **kwargs)
        assert REPORT_METRIC_MARKER in draft.scheme_snapshot.report_requirements
        seen.append(draft.draft_id)
        return draft

    monkeypatch.setattr(ResearchApplicationService, "prepare_run", prepare)
    return seen


async def test_report_survives_legal_replan(database, tmp_path, opted_in):  # noqa: F811
    await authority.test_c07_lawful_replan_preserves_initial_receipt(database, tmp_path)
    assert opted_in


async def test_report_survives_d01_resume(database, tmp_path, opted_in):  # noqa: F811
    await authority.test_c14_d01_resume_keeps_confirmation_receipt(database, tmp_path)
    assert opted_in


async def test_report_confirm_atomic_rollback(database, tmp_path, monkeypatch, opted_in):  # noqa: F811
    await authority.test_c13_alternate_confirm_add_run_atomicity(database, tmp_path, monkeypatch)
    assert opted_in
