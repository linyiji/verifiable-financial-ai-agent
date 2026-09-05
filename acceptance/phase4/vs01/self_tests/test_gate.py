from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

import acceptance.phase4.vs01.harness.gate as gate_module
from acceptance.phase4.vs01.harness.gate import (
    GateConfigurationError,
    GateError,
    ManagedService,
    PostgreSQLIsolation,
    PublicSurfaceViolation,
    _libpq_env,
    aggregate_manifest,
    application_database_url,
    build_result,
    collect_delivery_metadata,
    collect_integrated_x_delivery_metadata,
    load_control_fragments,
    parse_playwright_result,
    redact_url,
    result_markdown,
    scan_public_surface,
    validate_integrated_config,
)


def _checks() -> list[dict[str, object]]:
    return [{"check_id": "SELF", "status": "PASS", "passed": 7, "executed": 7}]


def _delivery() -> dict[str, object]:
    return {
        "requested_branch": "phase4/vs01-acceptance",
        "actual_branch": "p4-vs01-acceptance",
        "authorized_branch": "p4-vs01-acceptance",
        "branch_substitution_authorized": True,
        "remote_branch": "origin/p4-vs01-acceptance",
        "expected_remote_branch": "origin/p4-vs01-acceptance",
        "base_sha": "4b6721b6db433aae300f94750e1a405b6b450501",
        "source_parent_is_ancestor": True,
        "source_parent_tree": "35c47508ed65220c26620f5ec4bdd14cb798480d",
        "source_parent_tree_matches_authority": True,
        "branch_sha_at_execution": "a" * 40,
        "final_branch_sha": "a" * 40,
        "final_branch_sha_resolution": "EXACT_HARNESS_REVISION_AT_EXECUTION",
        "delivery_snapshot_semantics": "PUSHED_CLEAN_HARNESS_REVISION_AT_EXECUTION",
        "remote_branch_sha_at_execution": "a" * 40,
        "upstream_sha_at_execution": "a" * 40,
        "branch_pushed": True,
        "worktree_clean_at_execution": True,
        "branch_pushed_and_clean_at_execution": True,
        "worktree": "/tmp/repository",
        "worktree_portable": "$HOME/Verifiable_Financial_Agent_System_phase4/vs01-acceptance",
        "changed_path_count": 10,
        "outside_acceptance_owned_scope": [],
        "product_source_files_modified": False,
        "parent_only_files_modified": False,
        "parent_semantic_patch_proposals": 0,
        "phase4_integration_branch_sha": "4b6721b6db433aae300f94750e1a405b6b450501",
        "phase4_integration_branch_modified_from_base": False,
        "main_sha": "4b6721b6db433aae300f94750e1a405b6b450501",
        "main_modified_from_base": False,
    }


def _integrated_delivery() -> dict[str, object]:
    return {
        "x_delivery_sha": "c" * 40,
        "remote_x_branch": "origin/p4-vs01-acceptance",
        "remote_x_branch_sha_at_execution": "d" * 40,
        "x_delivery_sha_reachable_from_remote": True,
        "x_source_parent_is_ancestor": True,
        "x_source_parent_tree_matches_authority": True,
        "x_changed_path_count": 10,
        "x_acceptance_only_scope": True,
        "x_acceptance_subtree_sha": "e" * 40,
        "parent_acceptance_subtree_sha": "e" * 40,
        "parent_acceptance_subtree_matches_x": True,
        "x_delivery_binding_verified": True,
        # Parent-scope fields remain descriptive and are intentionally allowed.
        "product_source_files_modified": True,
        "parent_only_files_modified": True,
        "outside_acceptance_owned_scope": ["apps/api/main.py"],
    }


def _reality(**updates: object) -> dict[str, object]:
    value: dict[str, object] = {
        "real_backend": True,
        "real_frontend": True,
        "real_sse": True,
        "real_postgresql_16": True,
        "postgresql_causal_binding": True,
        "managed_backend_restart": True,
        "mock_business_responses": False,
        "candidate_tracked_clean_at_start": True,
        "runtime_sse_capture_bound": True,
        "api_sse_public_surface_scan_completed": True,
        "browser_public_surface_scan_completed": True,
        "x_delivery_binding_verified": True,
    }
    value.update(updates)
    return value


def _all_pass(manifest: dict) -> dict[str, dict[str, str]]:
    return {
        control["control_id"]: {"status": "PASS", "actual_result": "observed"}
        for control in manifest["controls"]
    }


def _config() -> dict:
    return {
        "schema_version": "phase4-vs01-runner-config/v1",
        "x_delivery_sha": "a" * 40,
        "postgres": {
            "admin_url_env": "VS01_POSTGRES_ADMIN_URL",
            "database_prefix": "vfas_vs01_",
            "migration_command": ["python3.11", "scripts/postgresql_migrate.py"],
        },
        "backend": {
            "command": [
                "python3.11",
                "-m",
                "uvicorn",
                "apps.api.main:app",
                "--port",
                "8010",
            ],
            "cwd": ".",
            "url": "http://127.0.0.1:8010",
        },
        "frontend": {
            "command": ["npm", "run", "preview", "--", "--port", "4173"],
            "cwd": "apps/web",
            "url": "http://127.0.0.1:4173",
        },
        "frontend_unavailable": {
            "command": ["npm", "run", "preview", "--", "--port", "4174"],
            "cwd": "apps/web",
            "url": "http://127.0.0.1:4174",
        },
        "frontend_api_base_url": "http://127.0.0.1:8010/api",
        "frontend_unavailable_api_base_url": "http://127.0.0.1:61999/api",
        "unavailable_backend_url": "http://127.0.0.1:61999",
        "sse_scenario_capture": {
            "driver_path": "scripts/run_phase4_vs01_sse_scenarios.py",
            "command": [
                "python3.11",
                "scripts/run_phase4_vs01_sse_scenarios.py",
            ],
            "cwd": ".",
            "timeout_seconds": 900,
        },
        "browser": {
            "command": ["npm", "run", "test:real"],
            "node24_command": [
                "npx",
                "--offline",
                "--yes",
                "--package=node@24.8.0",
                "--call",
            ],
            "cwd": "acceptance/phase4/vs01/browser",
        },
        "object_a": {
            "symbol": "VS1A",
            "company_name": "Alpha",
            "exchange": "TEST",
            "currency": "USD",
        },
        "object_b": {
            "symbol": "VS1B",
            "company_name": "Beta",
            "exchange": "TEST",
            "currency": "USD",
        },
        "goal_a": "Alpha goal",
        "goal_b": "Beta goal",
        "as_of": "2026-09-05",
    }


def test_fragment_aggregate_has_unique_complete_stable_controls() -> None:
    fragments = load_control_fragments()
    assert {fragment["specialist"] for fragment in fragments} == {"X1", "X2", "X3", "X4"}
    manifest = aggregate_manifest(fragments, generated_at="2026-09-05T00:00:00Z")
    controls = manifest["controls"]
    ids = [control["control_id"] for control in controls]
    assert ids == sorted(ids)
    assert len(ids) == len(set(ids))
    assert len(ids) >= 70
    assert manifest["summary"]["total"] == len(ids)


def test_fragment_aggregate_rejects_duplicate_control() -> None:
    fragments = load_control_fragments()
    duplicate = deepcopy(fragments[0])
    duplicate["fragment_id"] = "DUPLICATE-CONTROL-FRAGMENT"
    duplicate["controls"] = [deepcopy(fragments[0]["controls"][0])]
    with pytest.raises(GateConfigurationError, match="duplicate control"):
        aggregate_manifest([*fragments, duplicate])


def test_self_test_can_never_declare_integrated_pass() -> None:
    manifest = aggregate_manifest(load_control_fragments())
    result = build_result(
        manifest,
        _all_pass(manifest),
        mode="HARNESS_SELF_TEST",
        harness_checks=_checks(),
        delivery=_delivery(),
    )
    assert result["harness_status"] == "READY"
    assert result["vs01_integrated_status"] == "NOT_RUN"


def test_integrated_pass_requires_every_reality_predicate_and_control() -> None:
    manifest = aggregate_manifest(load_control_fragments())
    outcomes = _all_pass(manifest)
    incomplete = build_result(
        manifest,
        outcomes,
        mode="REAL_VS01_EXECUTION",
        harness_checks=_checks(),
        environment={"real_backend": True},
        delivery=_integrated_delivery(),
    )
    assert incomplete["vs01_integrated_status"] == "FAIL"
    complete = build_result(
        manifest,
        outcomes,
        mode="REAL_VS01_EXECUTION",
        harness_checks=_checks(),
        environment=_reality(),
        delivery=_integrated_delivery(),
    )
    assert complete["vs01_integrated_status"] == "PASS"


def test_integrated_pass_requires_runtime_bound_sse_capture() -> None:
    manifest = aggregate_manifest(load_control_fragments())
    result = build_result(
        manifest,
        _all_pass(manifest),
        mode="REAL_VS01_EXECUTION",
        harness_checks=_checks(),
        environment=_reality(runtime_sse_capture_bound=False),
        delivery=_integrated_delivery(),
    )
    assert result["vs01_integrated_status"] == "FAIL"
    assert "REALITY:runtime_sse_capture_bound" in result["next_exact_action"]
    assert "RERUN_SAME_INTEGRATED_COMMAND" in result["next_exact_action"]


def test_integrated_missing_control_is_required_evidence_absent() -> None:
    manifest = aggregate_manifest(load_control_fragments())
    result = build_result(
        manifest,
        {},
        mode="REAL_VS01_EXECUTION",
        harness_checks=_checks(),
        environment={},
        delivery=_integrated_delivery(),
    )
    integrated = [
        control for control in result["controls"] if control["layer"] != "HARNESS_SELF_TEST"
    ]
    assert integrated
    assert {control["status"] for control in integrated} == {"FAIL"}
    assert {control["actual_result"] for control in integrated} == {"REQUIRED_EVIDENCE_ABSENT"}


def test_public_surface_scan_rejects_secrets_hidden_reasoning_and_paths() -> None:
    assert scan_public_surface({"run_id": "RUN-A", "status": "RUNNING"})["secret_leakage"] == 0
    with pytest.raises(PublicSurfaceViolation, match="forbidden public field"):
        scan_public_surface({"authorization": "redacted"})
    with pytest.raises(PublicSurfaceViolation, match="hidden reasoning"):
        scan_public_surface({"message": "system prompt details"})
    with pytest.raises(PublicSurfaceViolation, match="internal path"):
        scan_public_surface({"message": "/Users/example/private.txt"})
    with pytest.raises(PublicSurfaceViolation, match="sentinel"):
        scan_public_surface({"message": "prefix-SENTINEL-suffix"}, sentinel="SENTINEL")
    with pytest.raises(PublicSurfaceViolation, match="forbidden public field"):
        scan_public_surface({"LANGFUSE_PUBLIC_KEY": "redacted"})
    with pytest.raises(PublicSurfaceViolation, match="forbidden public field"):
        scan_public_surface({"qiji_token": "redacted"})
    with pytest.raises(PublicSurfaceViolation, match="stack trace"):
        scan_public_surface({"message": "Traceback (most recent call last):\nValueError"})


def test_postgresql_urls_are_driver_normalized_and_redacted() -> None:
    admin = "postgresql://alice:p%40ss@db.example:5432/postgres?sslmode=require"
    application = application_database_url(admin, "vfas_vs01_1234_abcdef")
    assert application.startswith("postgresql://alice:p%40ss@db.example:5432/")
    assert "/vfas_vs01_1234_abcdef" in application
    assert application.endswith("?sslmode=require")
    redacted = redact_url(admin)
    assert "p%40ss" not in redacted
    assert "alice" not in redacted
    assert redacted.endswith("/postgres")
    assert _libpq_env(application)["PGSSLMODE"] == "require"

    driver_specific = application_database_url(
        admin,
        "vfas_vs01_1234_abcdef",
        application_scheme="postgresql+psycopg",
    )
    assert driver_specific.startswith("postgresql+psycopg://")


def test_blank_pgservicefile_is_unset_for_libpq_child(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PGSERVICEFILE", "")
    libpq_env = _libpq_env("postgresql://user:password@localhost/postgres")
    observation = gate_module.run_command(
        [
            sys.executable,
            "-c",
            "import os, sys; sys.exit(0 if 'PGSERVICEFILE' not in os.environ else 1)",
        ],
        cwd=Path(__file__).parent,
        env=libpq_env,
    )
    assert observation.returncode == 0

    monkeypatch.setenv("PGSERVICEFILE", "/local/explicit-service.conf")
    assert _libpq_env("postgresql://user:password@localhost/postgres")[
        "PGSERVICEFILE"
    ] == "/local/explicit-service.conf"


def test_postgresql_connection_block_is_verified_and_recoverable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    isolation = PostgreSQLIsolation(
        admin_url="postgresql://user:password@localhost/postgres",
        database_prefix="vfas_vs01_",
        database_name="vfas_vs01_1234_abcdef",
        server_version_num=160001,
        created=True,
    )
    calls: list[str] = []

    def psql(sql: str, *, database_url: str | None = None) -> str:
        assert database_url is None
        calls.append(sql)
        if "pg_terminate_backend" in sql:
            return "2"
        if "count(*) FROM pg_stat_activity" in sql:
            return "0"
        if "datallowconn" in sql:
            return "true" if any("ALLOW_CONNECTIONS true" in call for call in calls) else "false"
        return ""

    monkeypatch.setattr(isolation, "_psql", psql)
    evidence = isolation.block_connections()
    assert evidence["terminated_sessions"] == 2
    assert isolation.connections_blocked is True
    restored = isolation.restore_connections()
    assert restored["allow_connections"] is True
    assert isolation.connections_blocked is False
    assert calls[0].endswith("ALLOW_CONNECTIONS false;")
    assert calls[-2].endswith("ALLOW_CONNECTIONS true;")


def test_postgresql_cleanup_refuses_non_generated_database_before_calling_psql() -> None:
    isolation = PostgreSQLIsolation(
        admin_url="postgresql://user:password@localhost/postgres",
        database_prefix="vfas_vs01_",
        database_name="developer_database",
        created=True,
    )
    with pytest.raises(GateError, match="refusing to drop"):
        isolation.drop()


def test_integrated_configuration_rejects_mock_commands_and_inline_secrets() -> None:
    checked = validate_integrated_config(_config())
    assert checked["backend"]["command"][2] == "uvicorn"
    missing_x = _config()
    missing_x.pop("x_delivery_sha")
    with pytest.raises(GateConfigurationError, match="x_delivery_sha"):
        validate_integrated_config(missing_x)
    neutral = _config()
    neutral["backend"]["command"] = ["./bin/product-api", "--port", "8010"]
    neutral["frontend"]["command"] = ["./bin/product-web", "--port", "4173"]
    neutral["frontend_unavailable"]["command"] = [
        "./bin/product-web",
        "--port",
        "4174",
    ]
    neutral["sse_scenario_capture"]["command"] = [
        "./tools/capture-runtime",
        "scripts/run_phase4_vs01_sse_scenarios.py",
    ]
    assert validate_integrated_config(neutral)["backend"]["command"][0] == "./bin/product-api"
    mock = _config()
    mock["backend"]["command"] = ["python3.11", "mock_backend.py", "uvicorn", "apps.api"]
    with pytest.raises(GateConfigurationError, match="mock/Demo/fixture"):
        validate_integrated_config(mock)
    secret = _config()
    secret["frontend"]["extra_env"] = {"API_KEY": "must-not-be-in-json"}
    with pytest.raises(GateConfigurationError, match="secret/DSN"):
        validate_integrated_config(secret)

    forged_browser = _config()
    forged_browser["browser"]["command"] = ["node", "write-forged-report.mjs"]
    with pytest.raises(GateConfigurationError, match="Playwright entry point exactly"):
        validate_integrated_config(forged_browser)

    wrapped_capture = _config()
    wrapped_capture["sse_scenario_capture"]["command"] = [
        "sh",
        "-c",
        "python3.11 scripts/run_phase4_vs01_sse_scenarios.py",
    ]
    with pytest.raises(GateConfigurationError, match="shell wrapper"):
        validate_integrated_config(wrapped_capture)

    wrong_api_prefix = _config()
    wrong_api_prefix["frontend_api_base_url"] = "http://127.0.0.1:8010/private-api"
    with pytest.raises(GateConfigurationError, match="frozen /api route prefix"):
        validate_integrated_config(wrong_api_prefix)

    unrelated_primary = _config()
    unrelated_primary["frontend_api_base_url"] = "http://127.0.0.1:8020/api"
    with pytest.raises(GateConfigurationError, match="managed backend URL"):
        validate_integrated_config(unrelated_primary)

    unrelated_unavailable = _config()
    unrelated_unavailable["frontend_unavailable_api_base_url"] = "http://127.0.0.1:62000/api"
    with pytest.raises(GateConfigurationError, match="verified unreachable URL"):
        validate_integrated_config(unrelated_unavailable)


def test_playwright_result_requires_exactly_six_real_scenarios(tmp_path: Path) -> None:
    path = tmp_path / "playwright-result.json"
    path.write_text(
        json.dumps({"stats": {"expected": 6, "unexpected": 0, "skipped": 0, "flaky": 0}}),
        encoding="utf-8",
    )
    assert parse_playwright_result(path)["expected"] == 6
    path.write_text(
        json.dumps({"stats": {"expected": 6, "unexpected": 0, "skipped": 1, "flaky": 0}}),
        encoding="utf-8",
    )
    with pytest.raises(GateError, match="exact six real VS01"):
        parse_playwright_result(path)


def test_managed_service_rejects_a_preexisting_health_responder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = ManagedService(
        name="backend",
        command=("python3.11", "-m", "uvicorn", "apps.api.main:app"),
        cwd=Path.cwd(),
        url="http://127.0.0.1:8010",
        health_path="/health",
    )
    started = False

    def occupied(url: str) -> None:
        assert url == "http://127.0.0.1:8010/health"
        raise GateConfigurationError("unavailable backend URL is reachable")

    def unexpected_popen(*args: object, **kwargs: object) -> object:
        nonlocal started
        started = True
        raise AssertionError("process launch must not occur")

    monkeypatch.setattr(gate_module, "assert_url_unreachable", occupied)
    monkeypatch.setattr(gate_module.subprocess, "Popen", unexpected_popen)
    with pytest.raises(GateConfigurationError, match="reachable"):
        service.start(inherited_env={})
    assert started is False


def test_result_markdown_keeps_harness_and_integrated_status_separate() -> None:
    manifest = aggregate_manifest(load_control_fragments())
    result = build_result(
        manifest,
        {},
        mode="HARNESS_SELF_TEST",
        harness_checks=_checks(),
        delivery=_delivery(),
    )
    rendered = result_markdown(result)
    assert "HARNESS_STATUS = READY" in rendered
    assert "VS01_INTEGRATED_STATUS = NOT_RUN" in rendered
    assert "BRANCH_SHA_AT_EXECUTION = " + "a" * 40 in rendered
    assert "FINAL_BRANCH_SHA = " + "a" * 40 in rendered
    assert "DELIVERY_SNAPSHOT_SEMANTICS = PUSHED_CLEAN_HARNESS_REVISION_AT_EXECUTION" in rendered


def test_result_security_scopes_harness_delivery_separately_from_integrated_scan() -> None:
    manifest = aggregate_manifest(load_control_fragments())
    self_test = build_result(
        manifest,
        {},
        mode="HARNESS_SELF_TEST",
        harness_checks=_checks(),
        delivery=_delivery(),
    )
    assert self_test["safety"]["integrated_public_surface_scan"] == "NOT_RUN"
    assert self_test["safety"]["attestation_scope"] == "ACCEPTANCE_HARNESS_DELIVERY_ONLY"
    assert self_test["safety"]["secret_leakage"] == 0
    assert self_test["safety"]["hidden_cot_exposed"] is False

    outcomes = _all_pass(manifest)
    integrated = build_result(
        manifest,
        outcomes,
        mode="REAL_VS01_EXECUTION",
        harness_checks=_checks(),
        environment=_reality(),
        delivery=_integrated_delivery(),
    )
    assert integrated["safety"]["integrated_public_surface_scan"] == "PASS"
    assert integrated["safety"]["attestation_scope"] == "INTEGRATED_PRODUCT_PUBLIC_SURFACES"
    assert integrated["safety"]["secret_leakage"] == 0
    assert integrated["safety"]["hidden_cot_exposed"] is False


def test_result_contains_required_handoff_schema() -> None:
    manifest = aggregate_manifest(load_control_fragments())
    result = build_result(
        manifest,
        {},
        mode="HARNESS_SELF_TEST",
        harness_checks=_checks(),
        delivery=_delivery(),
    )
    assert result["phase4_codex_x"] == "PASS"
    assert set(result["specialists"].values()) == {"PASS"}
    assert set(result["harness_components"].values()) == {"YES"}
    assert set(result["named_tests"].values()) == {"READY"}
    assert result["manifest_summary"] == {
            "total": 70,
        "ready": 3,
        "blocked_by_a": 15,
        "blocked_by_b": 9,
            "blocked_by_c": 33,
        "blocked_by_parent": 10,
    }
    assert result["harness_self_tests"] == {"passed": 7, "executed": 7}
    assert result["next_exact_action"].startswith("PARENT_WAIT_FOR_A_B_C")


def test_delivery_metadata_uses_live_remote_not_stale_tracking_ref(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    head = "a" * 40
    stale_tracking = "b" * 40
    base = "4b6721b6db433aae300f94750e1a405b6b450501"

    def fake_git_text(*arguments: str, repository: Path) -> str | None:
        del repository
        if arguments == ("rev-parse", "HEAD"):
            return head
        if arguments == ("branch", "--show-current"):
            return "p4-vs01-acceptance"
        if arguments == (
            "rev-parse",
            "--abbrev-ref",
            "--symbolic-full-name",
            "@{upstream}",
        ):
            return "origin/p4-vs01-acceptance"
        if arguments == ("rev-parse", "@{upstream}"):
            return stale_tracking
        if arguments == ("merge-base", "--is-ancestor", base, "HEAD"):
            return ""
        if arguments == ("rev-parse", f"{base}^{{tree}}"):
            return "35c47508ed65220c26620f5ec4bdd14cb798480d"
        if arguments == (
            "ls-remote",
            "--refs",
            "origin",
            "refs/heads/p4-vs01-acceptance",
        ):
            return f"{head}\trefs/heads/p4-vs01-acceptance"
        if arguments == (
            "ls-remote",
            "--refs",
            "origin",
            "refs/heads/phase4",
        ):
            return f"{base}\trefs/heads/phase4"
        if arguments == (
            "ls-remote",
            "--refs",
            "origin",
            "refs/heads/main",
        ):
            return f"{base}\trefs/heads/main"
        if arguments in {
            ("diff", "--name-only", base),
            ("ls-files", "--others", "--exclude-standard"),
            ("status", "--porcelain", "--untracked-files=all"),
        }:
            return ""
        raise AssertionError(f"unexpected git arguments: {arguments!r}")

    monkeypatch.setattr(gate_module, "_git_text", fake_git_text)
    delivery = collect_delivery_metadata(tmp_path)
    assert delivery["local_tracking_sha_at_execution"] == stale_tracking
    assert delivery["remote_branch_sha_at_execution"] == head
    assert delivery["branch_pushed"] is True
    assert delivery["final_branch_sha"] == head
    assert delivery["delivery_snapshot_semantics"] == "PUSHED_CLEAN_HARNESS_REVISION_AT_EXECUTION"


def test_integrated_x_delivery_binds_parent_subtree_to_remote_revision(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    base = "4b6721b6db433aae300f94750e1a405b6b450501"
    x_sha = "c" * 40
    remote_tip = "d" * 40
    subtree = "e" * 40

    def fake_git_text(*arguments: str, repository: Path) -> str | None:
        del repository
        values: dict[tuple[str, ...], str] = {
            (
                "ls-remote",
                "--refs",
                "origin",
                "refs/heads/p4-vs01-acceptance",
            ): f"{remote_tip}\trefs/heads/p4-vs01-acceptance",
            ("merge-base", "--is-ancestor", x_sha, remote_tip): "",
            ("merge-base", "--is-ancestor", base, x_sha): "",
            ("rev-parse", f"{base}^{{tree}}"): ("35c47508ed65220c26620f5ec4bdd14cb798480d"),
            ("diff", "--name-only", base, x_sha): (
                "acceptance/phase4/vs01/README.md\nacceptance/phase4/vs01/run_vs01.py"
            ),
            ("rev-parse", f"{x_sha}:acceptance/phase4/vs01"): subtree,
            ("rev-parse", "HEAD:acceptance/phase4/vs01"): subtree,
        }
        if arguments not in values:
            raise AssertionError(f"unexpected git arguments: {arguments!r}")
        return values[arguments]

    monkeypatch.setattr(gate_module, "_git_text", fake_git_text)
    delivery = collect_integrated_x_delivery_metadata(x_sha, tmp_path)
    assert delivery["x_delivery_binding_verified"] is True
    assert delivery["x_delivery_sha_reachable_from_remote"] is True
    assert delivery["parent_acceptance_subtree_matches_x"] is True


@pytest.mark.parametrize(
    "field",
    [
        "x_delivery_sha_reachable_from_remote",
        "x_source_parent_tree_matches_authority",
        "x_acceptance_only_scope",
        "parent_acceptance_subtree_matches_x",
        "x_delivery_binding_verified",
    ],
)
def test_integrated_pass_rejects_unbound_x_delivery(field: str) -> None:
    manifest = aggregate_manifest(load_control_fragments())
    delivery = _integrated_delivery()
    delivery[field] = False
    result = build_result(
        manifest,
        _all_pass(manifest),
        mode="REAL_VS01_EXECUTION",
        harness_checks=_checks(),
        environment=_reality(),
        delivery=delivery,
    )
    assert result["phase4_codex_x"] == "FAIL"
    assert result["vs01_integrated_status"] == "FAIL"
    assert result["codex_x_delivery_failures"]
    assert "DELIVERY:" in result["next_exact_action"]


@pytest.mark.parametrize(
    ("field", "value", "failure_name"),
    [
        ("actual_branch", "phase4", "AUTHORIZED_BRANCH"),
        ("remote_branch_sha_at_execution", "b" * 40, "REMOTE_BRANCH_AT_EXECUTION_HEAD"),
        ("worktree_clean_at_execution", False, "WORKTREE_CLEAN_AT_EXECUTION"),
        ("outside_acceptance_owned_scope", ["apps/api.py"], "ACCEPTANCE_ONLY_SCOPE"),
        (
            "phase4_integration_branch_modified_from_base",
            True,
            "ORIGIN_PHASE4_UNCHANGED_FROM_BASE",
        ),
        ("main_modified_from_base", True, "ORIGIN_MAIN_UNCHANGED_FROM_BASE"),
    ],
)
def test_self_test_codex_x_requires_each_delivery_invariant(
    field: str, value: object, failure_name: str
) -> None:
    manifest = aggregate_manifest(load_control_fragments())
    delivery = _delivery()
    delivery[field] = value
    result = build_result(
        manifest,
        {},
        mode="HARNESS_SELF_TEST",
        harness_checks=_checks(),
        delivery=delivery,
    )
    assert result["phase4_codex_x"] == "FAIL"
    assert failure_name in result["codex_x_delivery_failures"]
    assert "RESOLVE_HARNESS_OR_DELIVERY_FAILURES" in result["next_exact_action"]
    assert "RERUN_CODEX_X_SELF_TEST" in result["next_exact_action"]


def test_integrated_parent_branch_and_product_changes_do_not_fail_x_harness() -> None:
    manifest = aggregate_manifest(load_control_fragments())
    delivery = _integrated_delivery()
    result = build_result(
        manifest,
        _all_pass(manifest),
        mode="REAL_VS01_EXECUTION",
        harness_checks=_checks(),
        environment=_reality(),
        delivery=delivery,
    )
    assert result["phase4_codex_x"] == "PASS"
    assert result["vs01_integrated_status"] == "PASS"
    assert result["codex_x_delivery_gate_applied"] is True
    assert "PHASE5_AND_QIJI_REMAIN_UNAUTHORIZED" in result["next_exact_action"]


def test_failed_harness_check_names_failure_and_requires_self_test_rerun() -> None:
    manifest = aggregate_manifest(load_control_fragments())
    result = build_result(
        manifest,
        {},
        mode="HARNESS_SELF_TEST",
        harness_checks=[{"check_id": "PYTHON_SELF_TESTS", "status": "FAIL"}],
        delivery=_delivery(),
    )
    assert result["phase4_codex_x"] == "FAIL"
    assert "HARNESS_CHECK:PYTHON_SELF_TESTS" in result["next_exact_action"]
    assert result["next_exact_action"].endswith("RERUN_CODEX_X_SELF_TEST")
