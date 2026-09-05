from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest


def _load_driver() -> ModuleType:
    path = Path(__file__).resolve().parents[4] / "scripts/run_phase4_vs01_sse_scenarios.py"
    spec = importlib.util.spec_from_file_location("phase4_vs01_sse_driver", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def driver() -> ModuleType:
    return _load_driver()


def _watcher(driver: ModuleType) -> object:
    watcher = driver.EventWatcher("http://127.0.0.1:1", "RUN-CHECKPOINT")
    watcher.events.extend(
        [
            {"sequence": 7, "type": "calculation.completed"},
            {"sequence": 8, "type": "task.correction_resolved"},
        ]
    )
    return watcher


def test_success_keeps_normal_index_and_discards_failure_checkpoint(
    tmp_path: Path,
    driver: ModuleType,
) -> None:
    output = tmp_path / "runtime-sse-capture-index.json"
    expected = {
        "schema_version": "phase4-vs01-runtime-sse-capture-index/v1",
        "scenarios": {"event_inventory": {"streams": ["CAPTURE-A"]}},
    }
    checkpoint = driver.FailureCheckpoint(output, candidate_sha="a" * 40)
    checkpoint.start_stage(
        "WRITE_FINAL_CAPTURE_INDEX",
        "normal immutable runtime SSE capture index",
        scenario_id="finalize",
        run_id="RUN-CHECKPOINT",
    )
    driver._write_final_index(output, expected)
    checkpoint.pass_stage()
    checkpoint.discard()

    assert json.loads(output.read_text(encoding="utf-8")) == expected
    assert not driver._checkpoint_path(output).exists()


def test_failure_checkpoint_retains_stage_events_run_and_safe_failure(
    tmp_path: Path,
    driver: ModuleType,
) -> None:
    output = tmp_path / "runtime-sse-capture-index.json"
    watcher = _watcher(driver)
    checkpoint = driver.FailureCheckpoint(output, candidate_sha="b" * 40)
    checkpoint.start_stage(
        "WAIT_FOR_RISK_TASK_STARTED",
        "task.started for the exact Run risk task",
        scenario_id="success",
        run_id="RUN-CHECKPOINT",
        watcher=watcher,
    )
    checkpoint.fail(
        driver.DriverError("timed out waiting for a real runtime event"),
        watcher=watcher,
        run_status="FAILED",
        safe_failure_stage="GENERATED_CAPABILITY",
        safe_failure_code="CAPABILITY_BUILD_FAILED",
    )

    value = json.loads(driver._checkpoint_path(output).read_text(encoding="utf-8"))
    assert value["status"] == "FAIL"
    assert value["failure_stage"] == "WAIT_FOR_RISK_TASK_STARTED"
    assert value["expected_event_or_condition"] == "task.started for the exact Run risk task"
    assert value["observed_event_names"] == [
        "calculation.completed",
        "task.correction_resolved",
    ]
    assert value["last_observed_event"] == "task.correction_resolved"
    assert value["last_observed_sse_sequence"] == 8
    assert value["run_id"] == "RUN-CHECKPOINT"
    assert value["run_status"] == "FAILED"
    assert value["run_terminal"] is True
    assert value["safe_failure_stage"] == "GENERATED_CAPABILITY"
    assert value["safe_failure_code"] == "CAPABILITY_BUILD_FAILED"


def test_timeout_checkpoint_preserves_exact_wait_stage(
    tmp_path: Path,
    driver: ModuleType,
) -> None:
    output = tmp_path / "runtime-sse-capture-index.json"
    checkpoint = driver.FailureCheckpoint(output, candidate_sha="c" * 40)
    checkpoint.start_stage(
        "WAIT_FOR_REPLAN_APPROVED",
        "replan.approved after the requested Replan watermark",
        scenario_id="success",
        run_id="RUN-CHECKPOINT",
    )
    checkpoint.fail(TimeoutError(), run_status="RUNNING")

    value = json.loads(driver._checkpoint_path(output).read_text(encoding="utf-8"))
    assert value["failure_stage"] == "WAIT_FOR_REPLAN_APPROVED"
    assert value["expected_event_or_condition"] == (
        "replan.approved after the requested Replan watermark"
    )
    assert value["exception_class"] == "TimeoutError"
    assert value["safe_error"] == "driver operation timed out"
    assert value["run_status"] == "RUNNING"
    assert value["run_terminal"] is False


def test_checkpoint_redacts_secret_values_and_secret_bearing_urls(
    tmp_path: Path,
    driver: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "owner-secret-value-that-must-not-appear"
    monkeypatch.setenv("FMP_API_KEY_1", secret)
    output = tmp_path / "runtime-sse-capture-index.json"
    checkpoint = driver.FailureCheckpoint(output, candidate_sha="d" * 40)
    checkpoint.start_stage(
        "WAIT_FOR_PROVIDER_EVENT",
        "sanitized runtime event",
        scenario_id="success",
        run_id="RUN-CHECKPOINT",
    )
    checkpoint.fail(
        driver.DriverError(
            f"request failed api_key={secret} at https://user:{secret}@provider.invalid/path"
        )
    )

    raw = driver._checkpoint_path(output).read_text(encoding="utf-8")
    assert secret not in raw
    assert "<redacted>" in raw
    assert driver._checkpoint_path(output).stat().st_mode & 0o777 == 0o600
