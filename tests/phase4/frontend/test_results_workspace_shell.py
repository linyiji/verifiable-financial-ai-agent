from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PAGE = ROOT / "apps/web/src/pages/ResultsWorkspacePage.tsx"
APP = ROOT / "apps/web/src/Phase4Application.tsx"
ROUTE = ROOT / "apps/web/src/routing/resultsRoute.ts"
HTTP_SOURCE = ROOT / "apps/web/src/data/HttpFrontendDataSource.ts"
EXECUTION_SURFACE = ROOT / "apps/web/src/components/results/InteractiveExecutionRecord.tsx"


def _page() -> str:
    return PAGE.read_text(encoding="utf-8")


def _app() -> str:
    return APP.read_text(encoding="utf-8")


def test_01_exact_run_route_opens_results_workspace() -> None:
    script = textwrap.dedent(
        f"""
        import assert from "node:assert/strict";
        import {{ readFile }} from "node:fs/promises";
        import {{ stripTypeScriptTypes }} from "node:module";
        const source = await readFile({str(ROUTE)!r}, "utf8");
        const stripped = stripTypeScriptTypes(source);
        const module = await import(`data:text/javascript,${{encodeURIComponent(stripped)}}`);
        assert.deepEqual(
          module.parseResultsRoute("/runs/RUN-exact/results/report"),
          {{runId: "RUN-exact", surface: "report"}}
        );
        assert.equal(module.parseResultsRoute("/runs/RUN-exact/results/report/extra"), null);
        """
    )
    subprocess.run(
        ["node", "--experimental-strip-types", "--input-type=module", "--eval", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def test_02_workspace_root_identity_matches_requested_run() -> None:
    page = _page()
    assert "source.getResultsWorkspace(runId" in page
    assert 'data-run-id={workspace.runId}' in page
    assert "workspace.runId" in page


def test_03_all_surface_urls_preserve_the_same_exact_run() -> None:
    route = ROUTE.read_text(encoding="utf-8")
    assert 'RESULTS_SURFACES = ["report", "review", "execution"]' in route
    assert "`/runs/${encodeURIComponent(runId)}/results/${surface}`" in route


def test_04_tab_selection_replaces_surface_without_changing_run() -> None:
    page = _page()
    app = _app()
    assert "onReplace(resultsPath(runId, next))" in page
    assert "window.history.replaceState" in app


def test_05_refresh_recovers_run_and_selected_surface_from_url() -> None:
    app = _app()
    assert "parseResultsRoute(window.location.pathname)" in app
    assert "runId={route.runId}" in app
    assert "surface={route.surface}" in app


def test_06_browser_back_and_forward_share_the_existing_route_listener() -> None:
    app = _app()
    assert 'window.addEventListener("popstate", onRoute)' in app
    assert 'window.removeEventListener("popstate", onRoute)' in app


def test_07_partial_ready_partial_are_rendered_from_contract_availability() -> None:
    page = _page()
    assert "root.reportSurface.availability" in page
    assert "root.reviewSurface.availability" in page
    assert "root.executionSurface.availability" in page
    assert 'status === "PARTIAL"' in page
    assert "availabilityLabel(itemAvailability.status)" in page


def test_08_unavailable_surface_does_not_render_a_product_payload() -> None:
    page = _page()
    unavailable = page.index('availability.status === "UNAVAILABLE"')
    product_host = page.index("<SurfaceHost", unavailable)
    assert "<UnavailableSurface" in page[unavailable:product_host]
    assert 'aria-disabled={itemAvailability.status === "UNAVAILABLE"}' in page
    assert 'availabilityFor(root.value, next).status === "UNAVAILABLE"' in page


def test_09_cross_run_or_object_surface_payload_fails_closed() -> None:
    page = _page()
    http_source = HTTP_SOURCE.read_text(encoding="utf-8")
    assert "getReportSurface(runId, root.value.objectId" in page
    assert "getFinancialReviewSurface(runId, root.value.objectId" in page
    assert "getExecutionRecordSurface(runId, root.value.objectId" in page
    assert "decodeReportSurface(value, expectedRunId, expectedObjectId)" in http_source
    assert "decodeFinancialReviewSurface(value, expectedRunId, expectedObjectId)" in http_source
    assert "decodeExecutionRecordSurface(value, expectedRunId, expectedObjectId)" in http_source


def test_10_results_workspace_has_no_fixture_or_demo_fallback() -> None:
    page = _page().lower()
    assert "fixture" not in page
    assert "demodata" not in page
    assert "run-57aed683" not in page
    assert "nvidia corporation" not in page


def test_11_unsafe_review_and_execution_fields_are_not_rendered() -> None:
    page = _page()
    forbidden = (
        "safeExplanation",
        "inputRefs",
        "outputRefs",
        "keyFindings",
        "risks",
        "limitations",
    )
    for field in forbidden:
        assert field not in page


def test_12_hidden_cot_and_raw_events_are_not_rendered() -> None:
    page = _page()
    execution_surface = EXECUTION_SURFACE.read_text(encoding="utf-8")
    assert "actorDetails" not in page
    assert "observableProcess" not in page
    assert "InteractiveExecutionRecord" in page
    assert "execution.actors.reduce" in execution_surface
    assert "模型内部推理或供应商原始响应" in execution_surface
