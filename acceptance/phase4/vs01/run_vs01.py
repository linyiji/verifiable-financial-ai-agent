#!/usr/bin/env python3
"""Top-level Phase 4 VS01 acceptance runner.

Modes are intentionally separate:

* ``self-test`` validates the acceptance harness and always emits
  ``VS01_INTEGRATED_STATUS=NOT_RUN``.
* ``integrated`` provisions PostgreSQL 16, launches the real product processes,
  exercises X1/X2/X3/X4, crosses a real backend restart, and fails unless every
  required control has applicable evidence.

No mode implements or mocks a product response.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import math
import os
import re
import secrets
import shlex
import subprocess
import sys
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from typing import Any
from urllib.parse import quote, unquote, urlsplit

from acceptance.phase4.vs01.harness.authority import verify_authority
from acceptance.phase4.vs01.harness.backend import (
    BackendHarnessConfig,
    HttpObservation,
    RestartEvidence,
    TransportUnavailable,
    UrllibJsonTransport,
    run_backend_vs01,
    validate_confirm_response,
    validate_research_run_draft,
    validate_released_result_projection,
    validate_run_collection,
    validate_standalone_run_detail,
    verify_restart_checkpoint,
)
from acceptance.phase4.vs01.harness.backend import (
    validate_error_envelope as validate_backend_error,
)
from acceptance.phase4.vs01.harness.capture_proxy import (
    AuditedCaptureProxy,
    CaptureProxyError,
    CaptureRecord,
)
from acceptance.phase4.vs01.harness.gate import (
    CONTRACT_REVISION,
    FINAL_FREEZE_DECISION_SHA256,
    MANIFEST_PATH,
    REPOSITORY_ROOT,
    VS01_ROOT,
    GateError,
    ManagedService,
    PostgreSQLIsolation,
    PublicSurfaceViolation,
    aggregate_manifest,
    assert_url_unreachable,
    build_result,
    collect_integrated_x_delivery_metadata,
    load_control_fragments,
    load_integrated_config,
    materialize_manifest,
    parse_playwright_result,
    run_command,
    scan_public_surface,
    sha256_json,
    sqlalchemy_async_database_url,
    write_json,
    write_result_bundle,
)
from acceptance.phase4.vs01.harness.sse import (
    CORE_CONTRACT_VERSION,
    EVENT_CONTRACT_VERSION,
    RAW_EVENT_TYPES,
    SUPPORTED_V1_EVENTS,
    UNSUPPORTED_V1_EVENTS,
    EventDisposition,
    LiveStreamObservation,
    SSEAcceptanceError,
    SSEBusinessFrame,
    SSECommentFrame,
    SSEProjectionOracle,
    assert_controlled_replan,
    assert_cursor_error_response,
    assert_exact_run_event_url,
    assert_numeric_opaque_suffix_equal,
    assert_numeric_resume,
    assert_self_correction_same_task_same_graph,
    assert_sse_success_headers,
    assert_terminal_cursor_response,
    assert_terminal_stream,
    collect_live_sse,
    parse_sse_bytes,
    validate_run_projection,
    validate_runtime_event,
)

JsonObject = dict[str, Any]

EVIDENCE_SCHEMA_VERSION = "phase4-vs01-real-sse-evidence/v1"
CAPTURE_INDEX_SCHEMA_VERSION = "phase4-vs01-capture-index/v1"
EVIDENCE_SCENARIOS = frozenset(
    {
        "event_inventory",
        "duplicate",
        "ordering_recovery",
        "heartbeat",
        "terminal_failure",
        "snapshot_race",
        "sparse_graph_refresh",
        "self_correction",
        "replan_pending",
        "replan_approved",
    }
)
MAX_EVIDENCE_BYTES = 32 * 1024 * 1024
MAX_CAPTURE_INDEX_BYTES = 256 * 1024
CAPTURE_ID_PATTERN = re.compile(r"CAP-[0-9A-F]{48}")
EVIDENCE_CAPTURE_PATH = re.compile(
    r"^/api/research-runs/(?P<run>[^/?]+)/(?P<kind>projection|events)$"
)
EXPECTED_FRONTEND_CONTROLS = frozenset(f"VS01-FE-{index:03d}" for index in range(3, 13))
EXPECTED_BROWSER_CONTROLS = EXPECTED_FRONTEND_CONTROLS | frozenset(
    {"VS01-DYN-001", "VS01-REC-008", "VS01-REC-009", "VS01-ID-003"}
)


class RecordingJsonTransport:
    """Delegate real HTTP requests while retaining response-only public evidence."""

    def __init__(self, delegate: UrllibJsonTransport, public_values: list[Any]) -> None:
        self.delegate = delegate
        self.public_values = public_values

    def request(
        self,
        method: str,
        path: str,
        *,
        headers: Mapping[str, str] | None = None,
        json_body: Mapping[str, Any] | None = None,
    ) -> HttpObservation:
        observation = self.delegate.request(
            method,
            path,
            headers=headers,
            json_body=json_body,
        )
        body_text = observation.body.decode("utf-8", errors="replace")
        try:
            body_value: Any = json.loads(body_text)
        except json.JSONDecodeError:
            body_value = body_text
        self.public_values.append(
            {
                "surface": "product_api_response",
                "status_code": observation.status_code,
                "headers": dict(observation.headers),
                "body": body_value,
                "body_utf8": body_text,
            }
        )
        return observation


def _pass(actual_result: str, evidence: Mapping[str, Any] | None = None) -> JsonObject:
    value: JsonObject = {"status": "PASS", "actual_result": actual_result}
    if evidence is not None:
        value["evidence"] = dict(evidence)
    return value


def _fail(actual_result: str, evidence: Mapping[str, Any] | None = None) -> JsonObject:
    value: JsonObject = {"status": "FAIL", "actual_result": actual_result}
    if evidence is not None:
        value["evidence"] = dict(evidence)
    return value


def _check_counts(check_id: str, stdout: str) -> dict[str, int]:
    if check_id == "VS01-HARNESS-PYTHON":
        counts = {
            name: sum(int(value) for value in re.findall(rf"\b(\d+) {name}\b", stdout))
            for name in ("passed", "failed", "errors", "skipped", "xfailed", "xpassed")
        }
        executed = sum(counts.values())
        return {"passed": counts["passed"], "executed": executed} if executed else {}
    if check_id == "VS01-HARNESS-BROWSER":
        executed = sum(int(value) for value in re.findall(r"(?m)^ℹ tests (\d+)\s*$", stdout))
        passed = sum(int(value) for value in re.findall(r"(?m)^ℹ pass (\d+)\s*$", stdout))
        result = {"passed": passed, "executed": executed} if executed else {}
        collected = re.search(r"(?m)^Total: (\d+) tests? in \d+ files?\s*$", stdout)
        if collected:
            result["real_tests_collected"] = int(collected.group(1))
        return result
    return {}


def _command_check(
    check_id: str,
    command: Sequence[str],
    *,
    cwd: Path,
    timeout_seconds: float,
    env: Mapping[str, str] | None = None,
) -> JsonObject:
    try:
        observation = run_command(
            command,
            cwd=cwd,
            env=env,
            timeout_seconds=timeout_seconds,
        )
    except GateError as exc:
        return {"check_id": check_id, "status": "FAIL", "summary": str(exc)}
    result = {
        "check_id": check_id,
        "status": "PASS" if observation.returncode == 0 else "FAIL",
        "returncode": observation.returncode,
        "duration_seconds": observation.duration_seconds,
        "stdout_sha256": hashlib.sha256(observation.stdout.encode()).hexdigest(),
        "stderr_sha256": hashlib.sha256(observation.stderr.encode()).hexdigest(),
    }
    result.update(_check_counts(check_id, observation.stdout))
    return result


def _harness_checks() -> list[JsonObject]:
    checks: list[JsonObject] = []
    try:
        evidence = verify_authority()
        checks.append(
            {
                "check_id": "VS01-HARNESS-AUTHORITY",
                "status": "PASS",
                "contract_revision": evidence["contract_revision"],
                "contract_set_sha256": evidence["phase4_contract_set_sha256"],
            }
        )
    except Exception as exc:
        checks.append(
            {
                "check_id": "VS01-HARNESS-AUTHORITY",
                "status": "FAIL",
                "summary": f"authority verification failed ({type(exc).__name__})",
            }
        )
    checks.append(
        _command_check(
            "VS01-HARNESS-PYTHON",
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "acceptance/phase4/vs01/self_tests",
            ],
            cwd=REPOSITORY_ROOT,
            timeout_seconds=180,
        )
    )
    checks.append(
        _command_check(
            "VS01-HARNESS-BROWSER",
            [
                "npx",
                "--yes",
                "--package=node@24.8.0",
                "--call",
                "npm run check",
            ],
            cwd=VS01_ROOT / "browser",
            timeout_seconds=180,
        )
    )
    return checks


def _self_test_outcomes(
    manifest: Mapping[str, Any], checks: Sequence[Mapping[str, Any]]
) -> dict[str, JsonObject]:
    passed = bool(checks) and all(check.get("status") == "PASS" for check in checks)
    return {
        control["control_id"]: (
            _pass("controlled harness self-tests passed")
            if passed
            else _fail("one or more controlled harness self-tests failed")
        )
        for control in manifest["controls"]
        if control["layer"] == "HARNESS_SELF_TEST"
    }


def _recorded_findings() -> list[JsonObject]:
    path = VS01_ROOT / "DEPENDENCIES_AND_FINDINGS.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GateError("dependencies/findings register is invalid") from exc
    findings = value.get("findings") if isinstance(value, dict) else None
    if not isinstance(findings, list) or not all(isinstance(item, dict) for item in findings):
        raise GateError("dependencies/findings register lacks a findings array")
    return [dict(item) for item in findings]


def _exact_object(value: Any, fields: set[str], *, label: str) -> JsonObject:
    if not isinstance(value, dict) or set(value) != fields:
        raise GateError(f"{label} must contain exactly {sorted(fields)}")
    return dict(value)


def _candidate_git_sha() -> str:
    observation = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    value = observation.stdout.strip()
    if observation.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40}", value):
        raise GateError("cannot resolve the integrated candidate git revision")
    return value


def _validate_external_sse_document(
    value: Any,
    *,
    expected_binding: Mapping[str, Any],
) -> JsonObject:
    document = _exact_object(
        value,
        {"schema_version", "candidate", "scenarios"},
        label="SSE scenario evidence",
    )
    if document["schema_version"] != EVIDENCE_SCHEMA_VERSION:
        raise GateError("SSE scenario evidence schema is unsupported")
    candidate = _exact_object(
        document["candidate"],
        {
            "git_sha",
            "contract_revision",
            "event_contract_version",
            "final_freeze_decision_sha256",
            "postgresql_major",
            "capture_source",
            "mock_business_responses",
            "capture_session_nonce_sha256",
            "database_name_sha256",
            "backend_process_boundary_id",
            "backend_base_url",
            "capture_driver_sha256",
        },
        label="SSE scenario evidence candidate",
    )
    if (
        not isinstance(candidate["git_sha"], str)
        or not isinstance(candidate["contract_revision"], str)
        or not isinstance(candidate["event_contract_version"], str)
        or not isinstance(candidate["final_freeze_decision_sha256"], str)
        or type(candidate["postgresql_major"]) is not int
        or not isinstance(candidate["capture_source"], str)
        or candidate["mock_business_responses"] is not False
    ):
        raise GateError("SSE scenario evidence candidate fields have invalid types")
    binding = _exact_object(
        expected_binding,
        {
            "capture_session_nonce_sha256",
            "database_name_sha256",
            "backend_process_boundary_id",
            "backend_base_url",
            "capture_driver_sha256",
        },
        label="expected SSE capture binding",
    )
    for name in (
        "capture_session_nonce_sha256",
        "database_name_sha256",
        "capture_driver_sha256",
    ):
        if not isinstance(binding[name], str) or not re.fullmatch(r"[0-9a-f]{64}", binding[name]):
            raise GateError(f"expected SSE capture binding {name} is invalid")
    if (
        not isinstance(binding["backend_process_boundary_id"], str)
        or not binding["backend_process_boundary_id"]
    ):
        raise GateError("expected SSE backend process boundary is invalid")
    parsed_backend = urlsplit(str(binding["backend_base_url"]))
    if parsed_backend.scheme not in {"http", "https"} or not parsed_backend.netloc:
        raise GateError("expected SSE backend base URL is invalid")
    expected_candidate = {
        "git_sha": _candidate_git_sha(),
        "contract_revision": CONTRACT_REVISION,
        "event_contract_version": EVENT_CONTRACT_VERSION,
        "final_freeze_decision_sha256": FINAL_FREEZE_DECISION_SHA256,
        "postgresql_major": 16,
        "capture_source": "REAL_PRODUCT_PUBLIC_API_SSE",
        "mock_business_responses": False,
        **binding,
    }
    if candidate != expected_candidate:
        raise GateError(
            "SSE scenario evidence is not runtime-bound real-product evidence for this candidate"
        )
    scenarios = document["scenarios"]
    if not isinstance(scenarios, dict) or set(scenarios) != EVIDENCE_SCENARIOS:
        raise GateError("SSE scenario evidence must provide every required named real scenario")
    return document


def _load_driver_capture_index(path: Path) -> tuple[JsonObject, str, dict[str, str]]:
    """Load only untrusted capture receipts, never driver-authored evidence.

    The external C-owned scenario driver may select gate-issued capture IDs, but
    it cannot supply candidate claims, response bodies, response headers,
    digests, Run identities, or PostgreSQL/process bindings.  Those facts are
    reconstructed below from the gate-owned in-memory proxy ledger.
    """

    try:
        size = path.stat().st_size
        raw = path.read_bytes()
    except OSError as exc:
        raise GateError("runtime SSE capture index is unavailable") from exc
    if (
        not path.is_file()
        or path.is_symlink()
        or size <= 0
        or size > MAX_CAPTURE_INDEX_BYTES
        or len(raw) != size
    ):
        raise GateError("runtime SSE capture index has an unsafe size/type")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GateError("runtime SSE capture index is not valid UTF-8 JSON") from exc
    index = _exact_object(
        value,
        {"schema_version", "scenarios"},
        label="runtime SSE capture index",
    )
    if index["schema_version"] != CAPTURE_INDEX_SCHEMA_VERSION:
        raise GateError("runtime SSE capture index schema is unsupported")
    scenarios = index["scenarios"]
    if not isinstance(scenarios, dict) or set(scenarios) != EVIDENCE_SCENARIOS:
        raise GateError("runtime SSE capture index must name every required scenario")

    references: dict[str, str] = {}

    def add(label: str, capture_id: Any) -> None:
        if not isinstance(capture_id, str) or CAPTURE_ID_PATTERN.fullmatch(capture_id) is None:
            raise GateError(f"runtime SSE capture index {label} is not a gate capture ID")
        if capture_id in references.values():
            raise GateError("runtime SSE capture index reuses a capture ID")
        references[label] = capture_id

    inventory = _exact_object(
        scenarios["event_inventory"],
        {"streams"},
        label="runtime SSE capture index event_inventory",
    )
    streams = inventory["streams"]
    if not isinstance(streams, list) or not 1 <= len(streams) <= 64:
        raise GateError("runtime SSE capture index inventory must contain 1..64 streams")
    for index_value, capture_id in enumerate(streams):
        add(f"event_inventory.streams[{index_value}]", capture_id)

    field_sets = {
        "duplicate": {"before_projection", "stream"},
        "ordering_recovery": {"before_projection", "stream", "recovered_projection"},
        "heartbeat": {"before_projection", "stream"},
        "terminal_failure": {"stream"},
        "snapshot_race": {"before_projection", "stream", "after_projection"},
        "sparse_graph_refresh": {"before_projection", "stream", "after_projection"},
        "self_correction": {"before_projection", "stream", "after_projection"},
        "replan_pending": {"before_projection", "stream", "after_projection"},
        "replan_approved": {"before_projection", "stream", "after_projection"},
    }
    for scenario_name, fields in field_sets.items():
        scenario = _exact_object(
            scenarios[scenario_name],
            fields,
            label=f"runtime SSE capture index {scenario_name}",
        )
        for field_name in sorted(fields):
            add(f"{scenario_name}.{field_name}", scenario[field_name])
    return index, hashlib.sha256(raw).hexdigest(), references


def _capture_record_identity(record: CaptureRecord, *, label: str) -> tuple[str, str]:
    parsed = urlsplit(record.canonical_path_query)
    match = EVIDENCE_CAPTURE_PATH.fullmatch(parsed.path)
    if record.method != "GET" or match is None or parsed.query or parsed.fragment:
        raise GateError(f"{label} is not one exact-Run public evidence GET")
    try:
        run_id = unquote(match.group("run"), errors="strict")
    except UnicodeDecodeError as exc:
        raise GateError(f"{label} Run identity is not valid UTF-8") from exc
    if not run_id or quote(run_id, safe="") != match.group("run"):
        raise GateError(f"{label} Run identity is not canonically encoded")
    return match.group("kind"), run_id


def _one_header(
    record: CaptureRecord,
    name: str,
    *,
    label: str,
    required: bool,
) -> str | None:
    values = record.request_header_values(name)
    upstream_values = record.upstream_request_header_values(name)
    if values != upstream_values:
        raise GateError(f"{label} {name} changed across the audited proxy")
    if not values:
        if required:
            raise GateError(f"{label} omitted required request header {name}")
        return None
    if len(values) != 1:
        raise GateError(f"{label} supplied ambiguous request header {name}")
    return values[0]


def _response_header_map(record: CaptureRecord, *, label: str) -> dict[str, str]:
    headers: dict[str, str] = {}
    for raw_name, raw_value in record.upstream_response_headers:
        name = raw_name.strip().lower()
        if not name or name in headers:
            raise GateError(f"{label} has empty or duplicate response headers")
        headers[name] = raw_value.strip()
    content_encoding = headers.get("content-encoding")
    if content_encoding is not None and content_encoding.lower() != "identity":
        raise GateError(f"{label} response bytes are not identity encoded")
    return headers


def _projection_artifact_from_record(record: CaptureRecord, *, label: str) -> JsonObject:
    kind, _ = _capture_record_identity(record, label=label)
    if kind != "projection" or not record.complete or record.status_code != 200:
        raise GateError(f"{label} is not a complete successful public projection capture")
    if record.sensitive_request_header_names:
        raise GateError(f"{label} used a sensitive request header")
    if (
        _one_header(
            record,
            "X-Phase4-Contract-Version",
            label=label,
            required=True,
        )
        != CORE_CONTRACT_VERSION
    ):
        raise GateError(f"{label} used the wrong core contract request header")
    headers = _response_header_map(record, label=label)
    if not headers.get("content-type", "").lower().startswith("application/json"):
        raise GateError(f"{label} response is not JSON")
    if headers.get("x-phase4-contract-version") != CORE_CONTRACT_VERSION:
        raise GateError(f"{label} response selected the wrong core contract")
    try:
        projection = json.loads(record.response_body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GateError(f"{label} response is not valid UTF-8 JSON") from exc
    if not isinstance(projection, dict):
        raise GateError(f"{label} projection response root is not an object")
    return {
        "capture_kind": "REAL_PUBLIC_PROJECTION",
        "request_url": record.canonical_proxy_url,
        "sha256": sha256_json(projection),
        "value": projection,
    }


def _stream_artifact_from_record(record: CaptureRecord, *, label: str) -> JsonObject:
    kind, run_id = _capture_record_identity(record, label=label)
    if kind != "events" or record.status_code != 200:
        raise GateError(f"{label} is not a successful public SSE capture")
    if not (record.complete or record.deliberate_sse_cut):
        raise GateError(f"{label} ended outside an audited complete-frame boundary")
    if record.sensitive_request_header_names:
        raise GateError(f"{label} used a sensitive request header")
    if _one_header(record, "Accept", label=label, required=True) != "text/event-stream":
        raise GateError(f"{label} did not request text/event-stream exactly")
    if (
        _one_header(
            record,
            "X-Phase4-Contract-Version",
            label=label,
            required=True,
        )
        != CORE_CONTRACT_VERSION
    ):
        raise GateError(f"{label} used the wrong core contract request header")
    if (
        _one_header(
            record,
            "X-Phase4-Event-Contract-Version",
            label=label,
            required=True,
        )
        != EVENT_CONTRACT_VERSION
    ):
        raise GateError(f"{label} used the wrong event contract request header")
    cursor = _one_header(record, "Last-Event-ID", label=label, required=False)
    headers = _response_header_map(record, label=label)
    return {
        "capture_kind": "REAL_PUBLIC_SSE_BYTES",
        "request_url": record.canonical_proxy_url,
        "run_id": run_id,
        "requested_cursor": cursor,
        "status_code": record.status_code,
        "headers": headers,
        "raw_sse_base64": base64.b64encode(record.response_body).decode("ascii"),
        "sha256": record.response_sha256,
        "stream_exhausted": record.complete,
    }


def _reconstruct_sse_evidence(
    index: Mapping[str, Any],
    records: Mapping[str, CaptureRecord],
    *,
    binding: Mapping[str, Any],
) -> JsonObject:
    scenarios = index["scenarios"]

    def projection(label: str) -> JsonObject:
        return _projection_artifact_from_record(records[label], label=label)

    def stream(label: str) -> JsonObject:
        return _stream_artifact_from_record(records[label], label=label)

    reconstructed: JsonObject = {
        "event_inventory": {
            "streams": [
                stream(f"event_inventory.streams[{position}]")
                for position in range(len(scenarios["event_inventory"]["streams"]))
            ]
        },
        "duplicate": {
            "before_projection": projection("duplicate.before_projection"),
            "stream": stream("duplicate.stream"),
        },
        "ordering_recovery": {
            "before_projection": projection("ordering_recovery.before_projection"),
            "stream": stream("ordering_recovery.stream"),
            "recovered_projection": projection("ordering_recovery.recovered_projection"),
        },
        "heartbeat": {
            "before_projection": projection("heartbeat.before_projection"),
            "stream": stream("heartbeat.stream"),
        },
        "terminal_failure": {"stream": stream("terminal_failure.stream")},
    }
    for name in (
        "snapshot_race",
        "sparse_graph_refresh",
        "self_correction",
        "replan_pending",
        "replan_approved",
    ):
        reconstructed[name] = {
            "before_projection": projection(f"{name}.before_projection"),
            "stream": stream(f"{name}.stream"),
            "after_projection": projection(f"{name}.after_projection"),
        }
    document = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "candidate": {
            "git_sha": _candidate_git_sha(),
            "contract_revision": CONTRACT_REVISION,
            "event_contract_version": EVENT_CONTRACT_VERSION,
            "final_freeze_decision_sha256": FINAL_FREEZE_DECISION_SHA256,
            "postgresql_major": 16,
            "capture_source": "REAL_PRODUCT_PUBLIC_API_SSE",
            "mock_business_responses": False,
            **dict(binding),
        },
        "scenarios": reconstructed,
    }
    return _validate_external_sse_document(document, expected_binding=binding)


def _capture_external_sse_evidence(
    config: Mapping[str, Any],
    *,
    database_name_sha256: str,
    backend_url: str,
    backend_process_boundary_id: str,
    run_ids: Mapping[str, str],
    output_root: Path,
) -> tuple[JsonObject, JsonObject]:
    capture = config.get("sse_scenario_capture")
    if not isinstance(capture, Mapping):
        raise GateError("sse_scenario_capture configuration is required")
    driver_path = capture.get("driver_path")
    if not isinstance(driver_path, str):
        raise GateError("SSE scenario capture driver path is invalid")
    driver = (REPOSITORY_ROOT / driver_path).resolve()
    try:
        driver.relative_to(REPOSITORY_ROOT)
    except ValueError as exc:
        raise GateError("SSE scenario capture driver escapes the repository") from exc
    if VS01_ROOT == driver or VS01_ROOT in driver.parents:
        raise GateError("SSE scenario capture driver cannot be supplied by this harness")
    if not driver.is_file() or driver.is_symlink():
        raise GateError("SSE scenario capture driver is unavailable or unsafe")
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", driver_path],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if tracked.returncode != 0:
        raise GateError("SSE scenario capture driver is not tracked in the candidate")
    driver_sha256 = hashlib.sha256(driver.read_bytes()).hexdigest()
    output_root.mkdir(parents=True, exist_ok=True)
    capture_path = output_root / "runtime-sse-capture-index.json"
    if capture_path.exists() or capture_path.is_symlink():
        raise GateError("SSE capture output already exists; use a fresh output directory")
    proxy = AuditedCaptureProxy(
        backend_url,
        upstream_timeout_seconds=float(capture["timeout_seconds"]),
    )
    try:
        with proxy:
            observation = run_command(
                capture["command"],
                cwd=Path(capture["cwd"]),
                env={
                    "VS01_BACKEND_URL": proxy.origin,
                    "VS01_EVIDENCE_OUTPUT_PATH": str(capture_path.resolve()),
                },
                timeout_seconds=float(capture["timeout_seconds"]),
                inherit_environment=False,
            )
            if observation.returncode != 0:
                raise GateError("tracked real SSE scenario capture command failed")
    except CaptureProxyError as exc:
        raise GateError("gate-owned SSE capture proxy failed closed") from exc
    index, index_sha256, references = _load_driver_capture_index(capture_path)
    try:
        records = proxy.verifier().verify_driver_capture_ids(
            references,
            seed_run_ids=(run_ids["A"], run_ids["B"]),
        )
    except CaptureProxyError as exc:
        raise GateError("driver capture IDs did not close against the gate ledger") from exc
    binding: JsonObject = {
        "capture_session_nonce_sha256": hashlib.sha256(proxy.session_id.encode()).hexdigest(),
        "database_name_sha256": database_name_sha256,
        "backend_process_boundary_id": backend_process_boundary_id,
        "backend_base_url": proxy.origin,
        "capture_driver_sha256": driver_sha256,
    }
    document = _reconstruct_sse_evidence(index, records, binding=binding)
    if not _tracked_candidate_clean():
        raise GateError("SSE scenario capture changed or added candidate files")
    return document, {
        **binding,
        "capture_index_sha256": index_sha256,
        "evidence_sha256": sha256_json(document),
        "capture_reference_set_sha256": sha256_json(dict(sorted(references.items()))),
        "capture_driver_path": driver_path,
        "capture_command_returncode": observation.returncode,
        "capture_duration_seconds": observation.duration_seconds,
        "gate_owned_ledger_records": len(proxy.session.records),
        "verified_evidence_reads": len(records),
        "direct_backend_origin_sha256": hashlib.sha256(
            backend_url.rstrip("/").encode()
        ).hexdigest(),
        "raw_database_url_recorded": False,
        "raw_capture_session_recorded": False,
        "driver_received_database_url": False,
        "driver_received_direct_backend_url": False,
        "driver_received_candidate_claims": False,
    }


def _projection_artifact(
    value: Any,
    *,
    label: str,
    backend_base_url: str,
) -> JsonObject:
    artifact = _exact_object(
        value,
        {"capture_kind", "request_url", "sha256", "value"},
        label=label,
    )
    if artifact["capture_kind"] != "REAL_PUBLIC_PROJECTION":
        raise GateError(f"{label}.capture_kind is not a real public projection")
    digest = artifact["sha256"]
    projection = artifact["value"]
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise GateError(f"{label}.sha256 is invalid")
    if not isinstance(projection, dict) or sha256_json(projection) != digest:
        raise GateError(f"{label} projection digest mismatch")
    view = validate_run_projection(projection)
    expected_url = (
        f"{backend_base_url.rstrip('/')}/api/research-runs/{quote(view.run_id, safe='')}/projection"
    )
    if artifact["request_url"] != expected_url:
        raise GateError(f"{label}.request_url is not the exact public projection URL")
    return dict(projection)


def _stream_artifact(
    value: Any,
    *,
    label: str,
    backend_base_url: str,
) -> tuple[LiveStreamObservation, JsonObject]:
    artifact = _exact_object(
        value,
        {
            "capture_kind",
            "request_url",
            "run_id",
            "requested_cursor",
            "status_code",
            "headers",
            "raw_sse_base64",
            "sha256",
            "stream_exhausted",
        },
        label=label,
    )
    if artifact["capture_kind"] != "REAL_PUBLIC_SSE_BYTES":
        raise GateError(f"{label}.capture_kind is not real public SSE bytes")
    run_id = artifact["run_id"]
    cursor = artifact["requested_cursor"]
    status_code = artifact["status_code"]
    headers = artifact["headers"]
    exhausted = artifact["stream_exhausted"]
    if not isinstance(run_id, str) or not run_id:
        raise GateError(f"{label}.run_id is invalid")
    expected_url = (
        f"{backend_base_url.rstrip('/')}/api/research-runs/{quote(run_id, safe='')}/events"
    )
    if artifact["request_url"] != expected_url:
        raise GateError(f"{label}.request_url is not the exact public SSE URL")
    assert_exact_run_event_url(str(artifact["request_url"]), run_id)
    if cursor is not None and not isinstance(cursor, str):
        raise GateError(f"{label}.requested_cursor is invalid")
    if isinstance(status_code, bool) or not isinstance(status_code, int):
        raise GateError(f"{label}.status_code is invalid")
    if not isinstance(headers, dict) or not all(
        isinstance(key, str) and isinstance(item, str) for key, item in headers.items()
    ):
        raise GateError(f"{label}.headers is invalid")
    if not isinstance(exhausted, bool):
        raise GateError(f"{label}.stream_exhausted is invalid")
    encoded = artifact["raw_sse_base64"]
    digest = artifact["sha256"]
    if not isinstance(encoded, str) or not isinstance(digest, str):
        raise GateError(f"{label} raw SSE fields are invalid")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as exc:
        raise GateError(f"{label}.raw_sse_base64 is invalid") from exc
    if not raw or len(raw) > MAX_EVIDENCE_BYTES:
        raise GateError(f"{label} raw SSE capture has an unsafe size")
    if not re.fullmatch(r"[0-9a-f]{64}", digest) or hashlib.sha256(raw).hexdigest() != digest:
        raise GateError(f"{label} raw SSE digest mismatch")
    assert_sse_success_headers(status_code, headers)
    frames = parse_sse_bytes([raw])
    events = tuple(
        validate_runtime_event(frame, expected_run_id=run_id)
        for frame in frames
        if isinstance(frame, SSEBusinessFrame)
    )
    sequences = tuple(event.sequence for event in events)
    if sequences != tuple(sorted(set(sequences))):
        raise GateError(f"{label} business sequences are not strictly increasing")
    observation = LiveStreamObservation(
        requested_run_id=run_id,
        requested_cursor=cursor,
        status_code=status_code,
        headers=dict(headers),
        frames=frames,
        events=events,
        dispositions=(),
        stream_exhausted=exhausted,
    )
    public = {
        "surface": "reviewed_real_sse_capture",
        "status_code": status_code,
        "headers": dict(headers),
        "business_events": [dict(event.raw) for event in events],
        "comments": [
            list(frame.comments) for frame in frames if isinstance(frame, SSECommentFrame)
        ],
    }
    return observation, public


def _scenario_object(value: Any, fields: set[str], *, label: str) -> JsonObject:
    return _exact_object(value, fields, label=f"SSE scenario {label}")


def _scenario_window(
    before: Mapping[str, Any],
    stream: LiveStreamObservation,
    after: Mapping[str, Any],
    *,
    label: str,
) -> tuple[Any, Any]:
    initial = validate_run_projection(before)
    final = validate_run_projection(after, expected_run_id=initial.run_id)
    if stream.requested_run_id != initial.run_id or not stream.events:
        raise GateError(f"{label} does not contain exact-Run business events")
    if stream.requested_cursor != str(initial.projection_sequence):
        raise GateError(f"{label} did not subscribe from the snapshot watermark")
    expected = tuple(range(initial.projection_sequence + 1, final.projection_sequence + 1))
    if (
        stream.business_sequences != expected
        or final.projection_sequence <= initial.projection_sequence
    ):
        raise GateError(f"{label} does not cover the exact projection sequence window")
    if final.projection_revision <= initial.projection_revision:
        raise GateError(f"{label} projection revision did not advance")
    return initial, final


def _business_frames(observation: LiveStreamObservation) -> list[SSEBusinessFrame]:
    return [frame for frame in observation.frames if isinstance(frame, SSEBusinessFrame)]


def _derived_event_frame(
    frame: SSEBusinessFrame,
    *,
    event_updates: Mapping[str, Any] | None = None,
    payload_updates: Mapping[str, Any] | None = None,
    payload_replace: Mapping[str, Any] | None = None,
) -> SSEBusinessFrame:
    """Create a deterministic negative mutation from a digest-pinned real frame."""
    body = json.loads(frame.data)
    if not isinstance(body, dict) or not isinstance(body.get("payload"), dict):
        raise GateError("reviewed base event is not mutable normalized JSON")
    body.update(dict(event_updates or {}))
    body["payload"] = (
        dict(payload_replace)
        if payload_replace is not None
        else {**body["payload"], **dict(payload_updates or {})}
    )
    data = json.dumps(body, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    raw = f"id: {body['sequence']}\nevent: {body['type']}\ndata: {data}\n\n".encode()
    derived = parse_sse_bytes([raw])
    if len(derived) != 1 or not isinstance(derived[0], SSEBusinessFrame):
        raise GateError("could not derive the controlled negative SSE frame")
    return derived[0]


def _conflicting_derivative(frame: SSEBusinessFrame) -> SSEBusinessFrame:
    body = json.loads(frame.data)
    if not isinstance(body, dict) or not isinstance(body.get("event_id"), str):
        raise GateError("reviewed duplicate base event lacks event_id")
    return _derived_event_frame(
        frame,
        event_updates={"event_id": f"{body['event_id']}-VS01-CONFLICT"},
    )


def _expect_event_rejection(
    frame: SSEBusinessFrame,
    *,
    run_id: str,
    label: str,
) -> str:
    try:
        validate_runtime_event(frame, expected_run_id=run_id)
    except SSEAcceptanceError as exc:
        return exc.code
    raise GateError(f"controlled {label} mutation was incorrectly admitted")


def _evaluate_external_sse_evidence(
    document: Mapping[str, Any],
    *,
    expected_binding: Mapping[str, Any],
) -> tuple[dict[str, JsonObject], list[Any]]:
    evidence = _validate_external_sse_document(document, expected_binding=expected_binding)
    backend_base_url = str(expected_binding["backend_base_url"])
    scenarios = evidence["scenarios"]
    outcomes: dict[str, JsonObject] = {}
    public_values: list[Any] = [dict(evidence["candidate"])]

    inventory = _scenario_object(scenarios["event_inventory"], {"streams"}, label="event_inventory")
    inventory_streams = inventory["streams"]
    if not isinstance(inventory_streams, list) or not inventory_streams:
        raise GateError("event_inventory.streams must be a non-empty array")
    observed_types: set[str] = set()
    real_frames_by_type: dict[str, SSEBusinessFrame] = {}
    inventory_events = 0
    for index, raw_stream in enumerate(inventory_streams):
        stream, public = _stream_artifact(
            raw_stream,
            label=f"event_inventory.streams[{index}]",
            backend_base_url=backend_base_url,
        )
        if not stream.events:
            raise GateError("event_inventory contains a stream without business events")
        observed_types.update(event.type for event in stream.events)
        for frame, event in zip(_business_frames(stream), stream.events, strict=True):
            real_frames_by_type.setdefault(event.type, frame)
        inventory_events += len(stream.events)
        public_values.append(public)
    if observed_types != set(SUPPORTED_V1_EVENTS):
        missing = sorted(set(SUPPORTED_V1_EVENTS) - observed_types)
        extra = sorted(observed_types - set(SUPPORTED_V1_EVENTS))
        raise GateError(
            f"real event inventory is incomplete or unsupported (missing={missing}, extra={extra})"
        )
    representative = next(iter(real_frames_by_type.values()))
    unsupported_rejections: dict[str, str] = {}
    for event_type in sorted(UNSUPPORTED_V1_EVENTS):
        derived = _derived_event_frame(
            representative,
            event_updates={
                "type": event_type,
                "task_id": None,
                "effect": "OBSERVATION_ONLY",
                "projection_refresh_required": False,
            },
        )
        code = _expect_event_rejection(
            derived,
            run_id=json.loads(representative.data)["run_id"],
            label=f"unsupported {event_type}",
        )
        if code != "UNSUPPORTED_EVENT":
            raise GateError(f"unsupported {event_type} did not use UNSUPPORTED_EVENT")
        unsupported_rejections[event_type] = code

    progress = real_frames_by_type["task.progress"]
    run_created = real_frames_by_type["run.created"]
    status_change = real_frames_by_type["run.status_changed"]
    graph_change = real_frames_by_type["graph.version_changed"]
    representative_body = json.loads(representative.data)
    graph_body = json.loads(graph_change.data)
    negative_frames = {
        "missing_required_payload_field": _derived_event_frame(run_created, payload_replace={}),
        "unknown_payload_field": _derived_event_frame(
            representative, payload_updates={"vs01_unknown": "forbidden"}
        ),
        "unsafe_payload_field": _derived_event_frame(
            representative, payload_updates={"authorization": "Bearer REDACTEDVALUE"}
        ),
        "wrong_effect": _derived_event_frame(
            representative,
            event_updates={
                "effect": (
                    "OBSERVATION_ONLY"
                    if representative_body["effect"] != "OBSERVATION_ONLY"
                    else "PATCH_PROJECTION"
                )
            },
        ),
        "bad_progress": _derived_event_frame(
            progress,
            payload_replace={"progress": 50, "progress_scale": "PERCENT"},
        ),
        "bad_status": _derived_event_frame(
            status_change, payload_updates={"status": "NOT_A_RUN_STATUS"}
        ),
        "bad_graph_version": _derived_event_frame(
            graph_change,
            payload_updates={"version_before": graph_body["graph_version"]},
        ),
        "bad_payload_schema_version": _derived_event_frame(
            representative, event_updates={"payload_schema_version": 2}
        ),
    }
    negative_rejections = {
        label: _expect_event_rejection(
            frame,
            run_id=json.loads(frame.data)["run_id"],
            label=label,
        )
        for label, frame in negative_frames.items()
    }
    inventory_evidence = {
        "real_stream_count": len(inventory_streams),
        "real_event_count": inventory_events,
        "supported_types_observed": len(observed_types),
        "declared_raw_types": len(RAW_EVENT_TYPES),
        "unsupported_types_admitted": len(observed_types & set(UNSUPPORTED_V1_EVENTS)),
        "unsupported_derivatives_rejected": len(unsupported_rejections),
        "payload_derivatives_rejected": len(negative_rejections),
    }
    outcomes["VS01-SSE-003"] = _pass(
        "reviewed real captures exercised every supported family; all declared "
        "unsupported derivatives were rejected",
        inventory_evidence,
    )
    outcomes["VS01-SSE-010"] = _pass(
        "all supported real payloads validated and real-frame malformed/unsafe "
        "derivatives failed closed",
        inventory_evidence,
    )

    duplicate = _scenario_object(
        scenarios["duplicate"],
        {"before_projection", "stream"},
        label="duplicate",
    )
    duplicate_before = _projection_artifact(
        duplicate["before_projection"],
        label="duplicate.before_projection",
        backend_base_url=backend_base_url,
    )
    duplicate_stream, duplicate_public = _stream_artifact(
        duplicate["stream"],
        label="duplicate.stream",
        backend_base_url=backend_base_url,
    )
    public_values.extend([duplicate_before, duplicate_public])
    duplicate_frames = _business_frames(duplicate_stream)
    duplicate_view = validate_run_projection(duplicate_before)
    if (
        len(duplicate_frames) != 1
        or duplicate_stream.requested_run_id != duplicate_view.run_id
        or duplicate_stream.requested_cursor != str(duplicate_view.projection_sequence)
        or duplicate_stream.events[0].sequence != duplicate_view.projection_sequence + 1
        or duplicate_stream.events[0].projection_refresh_required
    ):
        raise GateError("duplicate scenario is not one applicable non-refresh real N+1 frame")
    duplicate_oracle = SSEProjectionOracle(duplicate_before)
    first = duplicate_oracle.admit(duplicate_frames[0])
    committed = duplicate_oracle.committed_sequence
    repeated = duplicate_oracle.admit(duplicate_frames[0])
    if (
        first.disposition is not EventDisposition.APPLIED
        or repeated.disposition is not EventDisposition.DUPLICATE_IGNORED
        or duplicate_oracle.committed_sequence != committed
        or duplicate_oracle.task_ids != duplicate_view.task_ids
    ):
        raise GateError("real-frame duplicate was not ignored without state mutation")
    outcomes["VS01-SSE-007"] = _pass(
        "a digest-pinned real frame was applied once and its byte-identical replay was ignored",
        {"run_id": duplicate_view.run_id, "sequence": committed},
    )

    ordering = _scenario_object(
        scenarios["ordering_recovery"],
        {"before_projection", "stream", "recovered_projection"},
        label="ordering_recovery",
    )
    ordering_before = _projection_artifact(
        ordering["before_projection"],
        label="ordering_recovery.before_projection",
        backend_base_url=backend_base_url,
    )
    ordering_stream, ordering_public = _stream_artifact(
        ordering["stream"],
        label="ordering_recovery.stream",
        backend_base_url=backend_base_url,
    )
    ordering_after = _projection_artifact(
        ordering["recovered_projection"],
        label="ordering_recovery.recovered_projection",
        backend_base_url=backend_base_url,
    )
    public_values.extend([ordering_before, ordering_public, ordering_after])
    ordering_initial, ordering_final = _scenario_window(
        ordering_before,
        ordering_stream,
        ordering_after,
        label="ordering_recovery",
    )
    ordering_frames = _business_frames(ordering_stream)
    if len(ordering_frames) != 2 or ordering_stream.events[0].projection_refresh_required:
        raise GateError("ordering_recovery must contain two real frames with patchable N+1")
    conflict_oracle = SSEProjectionOracle(ordering_before)
    if conflict_oracle.admit(ordering_frames[0]).disposition is not EventDisposition.APPLIED:
        raise GateError("ordering_recovery N+1 base frame was not applicable")
    conflict = conflict_oracle.admit(_conflicting_derivative(ordering_frames[0]))
    if (
        conflict.disposition is not EventDisposition.QUARANTINED
        or conflict_oracle.committed_sequence != ordering_initial.projection_sequence + 1
    ):
        raise GateError("controlled conflicting derivative was not quarantined")
    gap_oracle = SSEProjectionOracle(ordering_before)
    gap = gap_oracle.admit(ordering_frames[1])
    if (
        gap.disposition is not EventDisposition.QUARANTINED
        or gap.reason != "SEQUENCE_GAP"
        or gap_oracle.committed_sequence != ordering_initial.projection_sequence
    ):
        raise GateError("dropped/reordered real frame did not trigger sequence recovery")
    gap_oracle.reconcile(ordering_after)
    stale = gap_oracle.admit(ordering_frames[0])
    if (
        stale.disposition is not EventDisposition.QUARANTINED
        or gap_oracle.committed_sequence != ordering_final.projection_sequence
    ):
        raise GateError("delayed stale real frame mutated recovered state")
    outcomes["VS01-SSE-008"] = _pass(
        "real complete frames plus a controlled real-frame derivative proved "
        "conflict/gap/order recovery",
        {
            "run_id": ordering_initial.run_id,
            "before_sequence": ordering_initial.projection_sequence,
            "recovered_sequence": ordering_final.projection_sequence,
        },
    )

    heartbeat = _scenario_object(
        scenarios["heartbeat"],
        {"before_projection", "stream"},
        label="heartbeat",
    )
    heartbeat_before = _projection_artifact(
        heartbeat["before_projection"],
        label="heartbeat.before_projection",
        backend_base_url=backend_base_url,
    )
    heartbeat_stream, heartbeat_public = _stream_artifact(
        heartbeat["stream"],
        label="heartbeat.stream",
        backend_base_url=backend_base_url,
    )
    public_values.extend([heartbeat_before, heartbeat_public])
    heartbeat_oracle = SSEProjectionOracle(heartbeat_before)
    heartbeat_sequence = heartbeat_oracle.committed_sequence
    heartbeat_task_ids = heartbeat_oracle.task_ids
    heartbeat_comments = [
        frame for frame in heartbeat_stream.frames if isinstance(frame, SSECommentFrame)
    ]
    if (
        not heartbeat_comments
        or heartbeat_stream.events
        or heartbeat_stream.stream_exhausted
        or heartbeat_stream.requested_run_id != heartbeat_oracle.expected_run_id
        or heartbeat_stream.requested_cursor != str(heartbeat_sequence)
        or heartbeat_oracle.committed_sequence != heartbeat_sequence
        or heartbeat_oracle.task_ids != heartbeat_task_ids
    ):
        raise GateError("heartbeat scenario is not an open idle real comment-only capture")
    outcomes["VS01-SSE-009"] = _pass(
        "real idle stream emitted comment-only heartbeat frames with no business sequence",
        {"run_id": heartbeat_stream.requested_run_id, "comments": len(heartbeat_comments)},
    )

    failure = _scenario_object(scenarios["terminal_failure"], {"stream"}, label="terminal_failure")
    failure_stream, failure_public = _stream_artifact(
        failure["stream"],
        label="terminal_failure.stream",
        backend_base_url=backend_base_url,
    )
    public_values.append(failure_public)
    if not failure_stream.events or failure_stream.events[-1].type != "run.failed":
        raise GateError("terminal_failure does not end in a real run.failed event")
    if failure_stream.requested_cursor not in {None, "0"} or any(
        event.type == "release.completed" for event in failure_stream.events
    ):
        raise GateError("terminal_failure must be a full failure stream with no success release")
    failure_outcome = {
        "FAILED": "FAILURE",
        "CANCELLED": "CANCELLED",
    }.get(failure_stream.events[-1].payload.get("status"))
    if failure_outcome is None:
        raise GateError("terminal_failure has an unsupported status")
    assert_terminal_stream(failure_stream, outcome=failure_outcome)
    outcomes["VS01-SSE-012"] = _pass(
        "reviewed controlled real failure closed with the exact frozen terminal payload",
        {
            "run_id": failure_stream.requested_run_id,
            "failure_stage": failure_stream.events[-1].payload["failure_stage"],
            "status": failure_stream.events[-1].payload["status"],
        },
    )

    race = _scenario_object(
        scenarios["snapshot_race"],
        {"before_projection", "stream", "after_projection"},
        label="snapshot_race",
    )
    race_before = _projection_artifact(
        race["before_projection"],
        label="snapshot_race.before_projection",
        backend_base_url=backend_base_url,
    )
    race_stream, race_public = _stream_artifact(
        race["stream"],
        label="snapshot_race.stream",
        backend_base_url=backend_base_url,
    )
    race_after = _projection_artifact(
        race["after_projection"],
        label="snapshot_race.after_projection",
        backend_base_url=backend_base_url,
    )
    public_values.extend([race_before, race_public, race_after])
    race_initial, race_final = _scenario_window(
        race_before, race_stream, race_after, label="snapshot_race"
    )
    race_oracle = SSEProjectionOracle(race_before)
    race_frames = _business_frames(race_stream)
    for index, frame in enumerate(race_frames):
        admitted = race_oracle.admit(frame)
        permitted = {EventDisposition.APPLIED}
        if index == len(race_frames) - 1:
            permitted.add(EventDisposition.REFRESH_REQUIRED)
        if admitted.disposition not in permitted:
            raise GateError("snapshot_race did not admit its exact contiguous live suffix")
    race_oracle.reconcile(race_after)
    if race_oracle.committed_sequence != race_final.projection_sequence:
        raise GateError("snapshot_race did not converge to the fresh projection")
    if any(
        race_oracle.admit(frame).disposition is not EventDisposition.DUPLICATE_IGNORED
        for frame in race_frames
    ):
        raise GateError("snapshot_race reapplied an already covered fact")
    outcomes["VS01-REC-007"] = _pass(
        "real N+1 race suffix converged exactly once to a fresh authoritative projection",
        {
            "run_id": race_initial.run_id,
            "from_sequence": race_initial.projection_sequence,
            "to_sequence": race_final.projection_sequence,
        },
    )

    sparse = _scenario_object(
        scenarios["sparse_graph_refresh"],
        {"before_projection", "stream", "after_projection"},
        label="sparse_graph_refresh",
    )
    sparse_before = _projection_artifact(
        sparse["before_projection"],
        label="sparse_graph_refresh.before_projection",
        backend_base_url=backend_base_url,
    )
    sparse_stream, sparse_public = _stream_artifact(
        sparse["stream"],
        label="sparse_graph_refresh.stream",
        backend_base_url=backend_base_url,
    )
    sparse_after = _projection_artifact(
        sparse["after_projection"],
        label="sparse_graph_refresh.after_projection",
        backend_base_url=backend_base_url,
    )
    public_values.extend([sparse_before, sparse_public, sparse_after])
    sparse_initial, sparse_final = _scenario_window(
        sparse_before, sparse_stream, sparse_after, label="sparse_graph_refresh"
    )
    sparse_frames = _business_frames(sparse_stream)
    if len(sparse_frames) != 1 or not sparse_stream.events[0].type.startswith("graph."):
        raise GateError("sparse_graph_refresh must contain one real sparse graph event")
    sparse_oracle = SSEProjectionOracle(sparse_before)
    task_ids_before = sparse_oracle.task_ids
    sparse_admission = sparse_oracle.admit(sparse_frames[0])
    if (
        sparse_admission.disposition is not EventDisposition.REFRESH_REQUIRED
        or sparse_oracle.task_ids != task_ids_before
    ):
        raise GateError("sparse graph event fabricated state instead of requiring refresh")
    sparse_oracle.reconcile(sparse_after)
    outcomes["VS01-DYN-002"] = _pass(
        "real sparse graph event changed no local Task and converged only through real projection",
        {
            "run_id": sparse_initial.run_id,
            "event_type": sparse_stream.events[0].type,
            "projection_sequence": sparse_final.projection_sequence,
        },
    )

    dynamic_controls = (
        ("self_correction", "VS01-DYN-003", None),
        ("replan_pending", "VS01-DYN-004", "PENDING"),
        ("replan_approved", "VS01-DYN-006", "APPROVED"),
    )
    dynamic_evidence: dict[str, JsonObject] = {}
    for scenario_name, control_id, decision in dynamic_controls:
        scenario = _scenario_object(
            scenarios[scenario_name],
            {"before_projection", "stream", "after_projection"},
            label=scenario_name,
        )
        before = _projection_artifact(
            scenario["before_projection"],
            label=f"{scenario_name}.before_projection",
            backend_base_url=backend_base_url,
        )
        stream, public = _stream_artifact(
            scenario["stream"],
            label=f"{scenario_name}.stream",
            backend_base_url=backend_base_url,
        )
        after = _projection_artifact(
            scenario["after_projection"],
            label=f"{scenario_name}.after_projection",
            backend_base_url=backend_base_url,
        )
        public_values.extend([before, public, after])
        initial, final = _scenario_window(before, stream, after, label=scenario_name)
        if decision is None:
            assert_self_correction_same_task_same_graph(before, stream.events, after)
            summary = "real correction remained same-Task/same-Graph with one durable path row"
        else:
            assert_controlled_replan(
                before,
                stream.events,
                after,
                expected_decision=decision,
            )
            summary = f"real {decision} Replan obeyed the Lead/graph-mutation boundary"
        item_evidence = {
            "run_id": initial.run_id,
            "from_sequence": initial.projection_sequence,
            "to_sequence": final.projection_sequence,
        }
        outcomes[control_id] = _pass(summary, item_evidence)
        dynamic_evidence[control_id] = item_evidence
    outcomes["VS01-DYN-007"] = _pass(
        "real correction and pending/approved Replan captures proved "
        "exclusive graph authority",
        {"validated_controls": sorted(dynamic_evidence)},
    )
    return outcomes, public_values


def _backend_config(config: Mapping[str, Any], alias: str, base_url: str) -> BackendHarnessConfig:
    suffix = alias.lower()
    return BackendHarnessConfig(
        base_url=base_url,
        object_request=config[f"object_{suffix}"],
        research_goal=config[f"goal_{suffix}"],
        as_of=config["as_of"],
        preferences={},
        request_timeout_seconds=float(config.get("request_timeout_seconds", 10)),
        auto_start_timeout_seconds=float(config.get("auto_start_timeout_seconds", 120)),
        poll_interval_seconds=float(config.get("poll_interval_seconds", 0.25)),
    )


def _record_backend_report(
    report: Any,
    outcomes: dict[str, JsonObject],
    *,
    source: str,
) -> None:
    for control in report.controls:
        value = control.to_dict()
        existing = outcomes.get(control.control_id)
        if existing is not None and existing["status"] == "PASS" and control.status == "FAIL":
            outcomes[control.control_id] = _fail(f"{source}: {control.summary}", {"source": source})
        elif existing is None or existing["status"] != "FAIL":
            outcomes[control.control_id] = {
                "status": control.status,
                "actual_result": f"{source}: {control.summary}",
                "evidence": {"source": source, **dict(value.get("evidence", {}))},
            }


def _public_projection(
    transport: UrllibJsonTransport,
    run_id: str,
) -> JsonObject:
    observation = transport.request(
        "GET",
        f"/api/research-runs/{quote(run_id, safe='')}/projection",
        headers={"X-Phase4-Contract-Version": CORE_CONTRACT_VERSION},
    )
    if observation.status_code != 200:
        raise GateError(f"exact projection read returned HTTP {observation.status_code}")
    if observation.header("x-phase4-contract-version") != CORE_CONTRACT_VERSION:
        raise GateError("exact projection omitted the selected core contract header")
    return observation.json_object()


def _prove_postgresql_causal_binding(
    isolation: PostgreSQLIsolation,
    transport: UrllibJsonTransport,
    checkpoint: Any,
) -> JsonObject:
    """Prove the managed Product request path depends on the disposable DB.

    Merely passing ``DATABASE_URL`` and observing PostgreSQL 16 is not causal
    evidence.  This probe first validates one exact successful Run read, disables
    new connections to the runner-created database and terminates its sessions,
    then requires that same read to stop succeeding.  Connections are restored in
    a finally block; the caller subsequently restarts the managed backend and
    revalidates persistence.
    """

    path = f"/api/research-runs/{quote(checkpoint.run_id, safe='')}"
    headers = {"X-Phase4-Contract-Version": CORE_CONTRACT_VERSION}
    before = transport.request("GET", path, headers=headers)
    if before.status_code != 200:
        raise GateError("PostgreSQL causal precondition Run read did not return HTTP 200")
    validate_standalone_run_detail(
        before.json_object(),
        object_id=checkpoint.object_id,
        goal_id=checkpoint.goal_id,
        scheme_id=checkpoint.scheme_id,
        expected_as_of=checkpoint.as_of,
        run_id=checkpoint.run_id,
        planned_graph_id=checkpoint.planned_graph_id,
    )

    block_evidence: Mapping[str, Any] | None = None
    failure_mode: str | None = None
    failure_status: int | None = None
    try:
        block_evidence = isolation.block_connections()
        try:
            unavailable = transport.request("GET", path, headers=headers)
        except TransportUnavailable:
            failure_mode = "TRANSPORT_UNAVAILABLE"
        else:
            failure_status = unavailable.status_code
            if 200 <= unavailable.status_code < 300:
                raise GateError(
                    "managed Product Run read still succeeded while its isolated "
                    "PostgreSQL database was connection-blocked"
                )
            failure_mode = "NON_SUCCESS_HTTP"
    finally:
        if isolation.connections_blocked:
            isolation.restore_connections()
    if block_evidence is None or failure_mode is None:
        raise GateError("PostgreSQL causal binding probe produced no blocked-read evidence")
    return {
        **dict(block_evidence),
        "pre_block_status": before.status_code,
        "blocked_read_outcome": failure_mode,
        "blocked_read_status": failure_status,
        "connections_restored": not isolation.connections_blocked,
        "run_id_sha256": hashlib.sha256(checkpoint.run_id.encode()).hexdigest(),
    }


def _object_runs(transport: UrllibJsonTransport, object_id: str) -> tuple[str, ...]:
    observation = transport.request(
        "GET",
        f"/api/objects/{quote(object_id, safe='')}/runs",
        headers={"X-Phase4-Contract-Version": CORE_CONTRACT_VERSION},
    )
    if observation.status_code != 200:
        raise GateError(f"Object Run history returned HTTP {observation.status_code}")
    return validate_run_collection(observation.json_object(), expected_object_id=object_id)


def _check_cross_object_histories(
    transport: UrllibJsonTransport,
    checkpoint_a: Any,
    checkpoint_b: Any,
) -> JsonObject:
    if (
        checkpoint_a.object_id == checkpoint_b.object_id
        or checkpoint_a.run_id == checkpoint_b.run_id
    ):
        raise GateError("A/B setup did not produce distinct canonical identities")
    runs_a = _object_runs(transport, checkpoint_a.object_id)
    runs_b = _object_runs(transport, checkpoint_b.object_id)
    if checkpoint_a.run_id not in runs_a or checkpoint_b.run_id not in runs_b:
        raise GateError("A/B Run is missing from its authoritative Object history")
    if checkpoint_b.run_id in runs_a or checkpoint_a.run_id in runs_b:
        raise GateError("cross-Object Run appeared in the wrong Object history")
    return {
        "object_a_id": checkpoint_a.object_id,
        "run_a_id": checkpoint_a.run_id,
        "object_b_id": checkpoint_b.object_id,
        "run_b_id": checkpoint_b.run_id,
        "run_a_history_count": len(runs_a),
        "run_b_history_count": len(runs_b),
    }


def _check_cross_object_confirm(
    transport: UrllibJsonTransport,
    config_a: BackendHarnessConfig,
    checkpoint_a: Any,
    checkpoint_b: Any,
) -> JsonObject:
    prepare_key = f"vs01-x4-prepare-{secrets.token_urlsafe(24)}"
    request_body = {
        "research_object_id": checkpoint_a.object_id,
        "research_goal": f"{config_a.research_goal} cross-object negative",
        "as_of": config_a.as_of,
        "preferences": {},
    }
    prepare = transport.request(
        "POST",
        "/api/research-runs/prepare",
        headers={
            "X-Phase4-Contract-Version": CORE_CONTRACT_VERSION,
            "Idempotency-Key": prepare_key,
        },
        json_body=request_body,
    )
    if prepare.status_code not in {200, 201}:
        raise GateError("cross-Object setup Prepare did not succeed")
    draft = validate_research_run_draft(
        prepare.json_object(),
        expected_object_id=checkpoint_a.object_id,
        expected_goal_text=request_body["research_goal"],
        expected_as_of=config_a.as_of,
        expected_preferences={},
    )
    before_a = _object_runs(transport, checkpoint_a.object_id)
    before_b = _object_runs(transport, checkpoint_b.object_id)
    mismatch = transport.request(
        "POST",
        "/api/research-runs",
        headers={
            "X-Phase4-Contract-Version": CORE_CONTRACT_VERSION,
            "Idempotency-Key": f"vs01-x4-confirm-{secrets.token_urlsafe(24)}",
        },
        json_body={
            "draft_id": draft.draft_id,
            "draft_version": draft.draft_version,
            "draft_hash": draft.draft_hash,
            "research_object_id": checkpoint_b.object_id,
            "confirm_scheme": True,
        },
    )
    body = mismatch.json_object()
    error = body.get("error") if isinstance(body, dict) else None
    code = error.get("code") if isinstance(error, dict) else None
    if code != "IDENTITY_MISMATCH":
        raise GateError("wrong-Object Confirm did not return frozen IDENTITY_MISMATCH")
    validate_backend_error(mismatch, expected_code="IDENTITY_MISMATCH")
    after_a = _object_runs(transport, checkpoint_a.object_id)
    after_b = _object_runs(transport, checkpoint_b.object_id)
    if before_a != after_a or before_b != after_b:
        raise GateError("wrong-Object Confirm mutated an Object Run history")
    return {
        "error_code": code,
        "http_status": mismatch.status_code,
        "run_cardinality_unchanged": True,
    }


def _check_concurrent_confirm(
    transport: UrllibJsonTransport,
    config: BackendHarnessConfig,
    object_id: str,
) -> JsonObject:
    """Prove an in-flight same-key race admits exactly one immutable Run."""

    prepare_key = f"vs01-x4-concurrent-prepare-{secrets.token_urlsafe(24)}"
    goal = config.research_goal
    prepare_body = {
        "research_object_id": object_id,
        "research_goal": goal,
        "as_of": config.as_of,
        "preferences": dict(config.preferences),
    }
    prepare = transport.request(
        "POST",
        "/api/research-runs/prepare",
        headers={
            "X-Phase4-Contract-Version": CORE_CONTRACT_VERSION,
            "Idempotency-Key": prepare_key,
        },
        json_body=prepare_body,
    )
    if prepare.status_code not in {200, 201}:
        raise GateError("concurrent Confirm setup Prepare did not succeed")
    draft = validate_research_run_draft(
        prepare.json_object(),
        expected_object_id=object_id,
        expected_goal_text=goal,
        expected_as_of=config.as_of,
        expected_preferences=config.preferences,
    )
    before = _object_runs(transport, object_id)
    confirm_key = f"vs01-x4-concurrent-confirm-{secrets.token_urlsafe(24)}"
    confirm_body = {
        "draft_id": draft.draft_id,
        "draft_version": draft.draft_version,
        "draft_hash": draft.draft_hash,
        "research_object_id": object_id,
        "confirm_scheme": True,
    }
    barrier = Barrier(3)

    def confirm_once() -> HttpObservation:
        barrier.wait(timeout=15)
        return transport.request(
            "POST",
            "/api/research-runs",
            headers={
                "X-Phase4-Contract-Version": CORE_CONTRACT_VERSION,
                "Idempotency-Key": confirm_key,
            },
            json_body=confirm_body,
        )

    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="vs01-confirm") as pool:
        futures = [pool.submit(confirm_once) for _ in range(2)]
        barrier.wait(timeout=15)
        responses = [future.result(timeout=30) for future in futures]
    if sorted(response.status_code for response in responses) != [200, 201]:
        raise GateError("concurrent same-key Confirm did not return one create and one replay")
    admissions: list[JsonObject] = []
    for response in responses:
        admissions.append(
            validate_confirm_response(
                response.json_object(),
                expected_draft=draft,
                expected_object_id=object_id,
                expected_replayed=response.status_code == 200,
            )
        )
    if admissions[0] != admissions[1]:
        raise GateError("concurrent same-key Confirm returned different admissions")
    run_id = admissions[0]["run_id"]
    after = _object_runs(transport, object_id)
    if set(after) - set(before) != {run_id} or after.count(run_id) != 1:
        raise GateError("concurrent same-key Confirm did not create exactly one Run")
    consumed = transport.request(
        "POST",
        "/api/research-runs",
        headers={
            "X-Phase4-Contract-Version": CORE_CONTRACT_VERSION,
            "Idempotency-Key": f"vs01-x4-consumed-{secrets.token_urlsafe(24)}",
        },
        json_body=confirm_body,
    )
    validate_backend_error(
        consumed,
        expected_code="CONFLICT",
        expected_reason_code="DRAFT_CONSUMED",
    )
    if _object_runs(transport, object_id) != after:
        raise GateError("new-key consumed-draft Confirm created an extra Run")
    return {
        "concurrent_requests": 2,
        "create_responses": 1,
        "replay_responses": 1,
        "admission_sha256": sha256_json(admissions[0]),
        "run_id": run_id,
        "new_key_consumed_reason": "DRAFT_CONSUMED",
        "run_cardinality_delta": 1,
    }


def _admit_browser_alternate_run(
    transport: UrllibJsonTransport,
    config: BackendHarnessConfig,
    object_id: str,
) -> JsonObject:
    """Create a fresh same-Object Run for the real browser switch/recovery probes."""

    prepare_body = {
        "research_object_id": object_id,
        "research_goal": config.research_goal,
        "as_of": config.as_of,
        "preferences": dict(config.preferences),
    }
    prepare = transport.request(
        "POST",
        "/api/research-runs/prepare",
        headers={
            "X-Phase4-Contract-Version": CORE_CONTRACT_VERSION,
            "Idempotency-Key": f"vs01-browser-alternate-prepare-{secrets.token_urlsafe(24)}",
        },
        json_body=prepare_body,
    )
    if prepare.status_code not in {200, 201}:
        raise GateError("browser alternate Prepare did not succeed")
    draft = validate_research_run_draft(
        prepare.json_object(),
        expected_object_id=object_id,
        expected_goal_text=config.research_goal,
        expected_as_of=config.as_of,
        expected_preferences=config.preferences,
    )
    before = _object_runs(transport, object_id)
    confirm_body = {
        "draft_id": draft.draft_id,
        "draft_version": draft.draft_version,
        "draft_hash": draft.draft_hash,
        "research_object_id": object_id,
        "confirm_scheme": True,
    }
    confirm = transport.request(
        "POST",
        "/api/research-runs",
        headers={
            "X-Phase4-Contract-Version": CORE_CONTRACT_VERSION,
            "Idempotency-Key": f"vs01-browser-alternate-confirm-{secrets.token_urlsafe(24)}",
        },
        json_body=confirm_body,
    )
    if confirm.status_code != 201:
        raise GateError("browser alternate Confirm did not create one fresh Run")
    admission = validate_confirm_response(
        confirm.json_object(),
        expected_draft=draft,
        expected_object_id=object_id,
        expected_replayed=False,
    )
    run_id = admission["run_id"]
    after = _object_runs(transport, object_id)
    if set(after) - set(before) != {run_id} or after.count(run_id) != 1:
        raise GateError("browser alternate Confirm did not add exactly one same-Object Run")
    projection = _public_projection(transport, run_id)
    view = validate_run_projection(
        projection,
        expected_run_id=run_id,
        expected_object_id=object_id,
    )
    if view.run_status in {"RELEASED", "FAILED", "CANCELLED"}:
        raise GateError("browser alternate Run became terminal before browser launch")
    if not view.tasks:
        raise GateError("browser alternate Run projection has no authoritative Task")
    return {
        "objectId": object_id,
        "runId": run_id,
        "taskId": view.tasks[0].task_id,
    }


async def _collect_stream(
    base_url: str,
    run_id: str,
    cursor: str,
    *,
    timeout_seconds: float,
    max_business_events: int | None = None,
) -> LiveStreamObservation:
    try:
        import httpx
    except ImportError as exc:  # pragma: no cover - declared repository dependency
        raise GateError("httpx is required for live SSE acceptance") from exc
    url = f"{base_url}/api/research-runs/{quote(run_id, safe='')}/events"
    assert_exact_run_event_url(url, run_id)
    timeout = httpx.Timeout(timeout_seconds, connect=10.0)
    try:
        async with asyncio.timeout(timeout_seconds):
            async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
                async with client.stream(
                    "GET",
                    url,
                    headers={
                        "Accept": "text/event-stream",
                        "Last-Event-ID": cursor,
                        "X-Phase4-Contract-Version": CORE_CONTRACT_VERSION,
                        "X-Phase4-Event-Contract-Version": EVENT_CONTRACT_VERSION,
                    },
                ) as response:
                    if response.status_code != 200:
                        raw = await response.aread()
                        raise GateError(
                            f"live SSE returned HTTP {response.status_code} ({len(raw)} bytes)"
                        )
                    return await collect_live_sse(
                        response,
                        expected_run_id=run_id,
                        requested_cursor=cursor,
                        max_business_events=max_business_events,
                    )
    except TimeoutError as exc:
        raise GateError("live SSE collection exceeded its total deadline") from exc


async def _cursor_error(
    base_url: str,
    run_id: str,
    cursor: str,
    *,
    expected_code: str,
) -> JsonObject:
    import httpx

    url = f"{base_url}/api/research-runs/{quote(run_id, safe='')}/events"
    async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
        response = await client.get(
            url,
            headers={
                "Accept": "text/event-stream",
                "Last-Event-ID": cursor,
                "X-Phase4-Contract-Version": CORE_CONTRACT_VERSION,
                "X-Phase4-Event-Contract-Version": EVENT_CONTRACT_VERSION,
            },
        )
    try:
        body = response.json()
    except ValueError as exc:
        raise GateError("cursor error response was not JSON") from exc
    assert_cursor_error_response(
        response.status_code,
        response.headers,
        body,
        expected_code=expected_code,
    )
    return {
        "status_code": response.status_code,
        "code": expected_code,
        "headers": dict(response.headers),
        "body": body,
    }


def _public_stream_value(observation: LiveStreamObservation) -> JsonObject:
    return {
        "surface": "live_product_sse_response",
        "status_code": observation.status_code,
        "headers": dict(observation.headers),
        "business_events": [dict(event.raw) for event in observation.events],
        "comments": [
            list(frame.comments)
            for frame in observation.frames
            if isinstance(frame, SSECommentFrame)
        ],
    }


async def _run_live_sse_matrix(
    base_url: str,
    projection_a: Mapping[str, Any],
    projection_b: Mapping[str, Any],
    *,
    timeout_seconds: float,
) -> tuple[
    dict[str, JsonObject],
    list[Any],
    dict[str, LiveStreamObservation],
]:
    outcomes: dict[str, JsonObject] = {}
    public_values: list[Any] = [projection_a, projection_b]
    view_a = validate_run_projection(projection_a)
    view_b = validate_run_projection(projection_b)
    try:
        validate_run_projection(projection_b, expected_run_id=view_a.run_id)
    except SSEAcceptanceError as exc:
        if exc.code != "IDENTITY_MISMATCH":
            raise GateError("Run B projection used the wrong cross-Run error") from exc
        cross_projection_code = exc.code
    else:
        raise GateError("Run B projection was admitted into Run A context")
    outcomes["VS01-REC-001"] = _pass(
        "real A/B projections close exact identities; B snapshot is rejected from A context",
        {
            "run_a_id": view_a.run_id,
            "run_b_id": view_b.run_id,
            "sequence_a": view_a.projection_sequence,
            "sequence_b": view_b.projection_sequence,
            "cross_projection_rejection": cross_projection_code,
        },
    )
    full_a = await _collect_stream(base_url, view_a.run_id, "0", timeout_seconds=timeout_seconds)
    full_b = await _collect_stream(base_url, view_b.run_id, "0", timeout_seconds=timeout_seconds)
    public_values.extend(_public_stream_value(stream) for stream in (full_a, full_b))
    if not full_a.events or not full_b.events:
        raise GateError("A/B real SSE streams did not expose business events")
    outcomes["VS01-SSE-001"] = _pass("real exact-Run SSE headers passed")
    outcomes["VS01-SSE-002"] = _pass(
        "real SSE bytes parsed into frozen normalized envelopes",
        {"run_a_frames": len(full_a.frames), "run_b_frames": len(full_b.frames)},
    )
    outcomes["VS01-SSE-004"] = _pass("all observed real events carried exact effect semantics")
    sequences_ok = all(
        stream.business_sequences == tuple(range(1, stream.business_sequences[-1] + 1))
        for stream in (full_a, full_b)
    )
    if not sequences_ok:
        raise GateError("real SSE replay was not contiguous from sequence 1")
    outcomes["VS01-SSE-006"] = _pass("real A/B sequences were contiguous and Run-scoped")
    if any(
        isinstance(frame, SSECommentFrame) for stream in (full_a, full_b) for frame in stream.frames
    ):
        outcomes["VS01-SSE-009"] = _pass(
            "real SSE response carried comment-only heartbeat frames without business identity"
        )

    frame_a = next(
        (
            frame
            for frame, event in zip(_business_frames(full_a), full_a.events, strict=True)
            if event.task_id is not None
        ),
        None,
    )
    if frame_a is None:
        raise GateError("Run A real SSE exposed no Task-scoped frame for cross-Run rejection")
    oracle_b = SSEProjectionOracle(projection_b)
    foreign = oracle_b.admit(frame_a)
    if foreign.disposition is not EventDisposition.QUARANTINED:
        raise GateError("real Run A frame was not quarantined from Run B context")
    cross_cursor = await _cursor_error(
        base_url,
        view_b.run_id,
        full_a.events[0].event_id,
        expected_code="INVALID_CURSOR",
    )
    public_values.append(cross_cursor)
    outcomes["VS01-SSE-005"] = _pass("a real Task-scoped A frame cannot enter B stream context")
    outcomes["VS01-REC-004"] = _pass("cross-Run opaque cursor returned INVALID_CURSOR")
    outcomes["VS01-REC-008"] = _pass("stale/foreign real stream frame was quarantined")
    outcomes["VS01-ID-004"] = _pass(
        "real cross-Run frame and cursor both failed closed",
        {"foreign_disposition": foreign.disposition.value},
    )

    durable_tail_b = full_b.last_sequence
    if durable_tail_b is None:
        raise GateError("Run B stream has no durable tail")
    ahead = await _cursor_error(
        base_url,
        view_b.run_id,
        str(durable_tail_b + 1),
        expected_code="CURSOR_AHEAD",
    )
    public_values.append(ahead)
    outcomes["VS01-REC-005"] = _pass("cursor ahead returned pre-header CURSOR_AHEAD")

    cut = await _collect_stream(
        base_url,
        view_a.run_id,
        "0",
        timeout_seconds=timeout_seconds,
        max_business_events=1,
    )
    if not cut.events:
        raise GateError("disconnect probe did not capture a complete business frame")
    cut_signature = [
        (event.sequence, event.event_id, event.canonical_content_sha256) for event in cut.events
    ]
    baseline_prefix = [
        (event.sequence, event.event_id, event.canonical_content_sha256)
        for event in full_a.events[: len(cut.events)]
    ]
    if cut_signature != baseline_prefix:
        raise GateError("disconnect probe bytes differ from the captured full baseline")
    committed = cut.events[-1].sequence
    resumed = await _collect_stream(
        base_url,
        view_a.run_id,
        str(committed),
        timeout_seconds=timeout_seconds,
    )
    durable_tail_a = full_a.last_sequence
    if durable_tail_a is None:
        raise GateError("Run A stream has no durable tail")
    assert_numeric_resume(
        cut,
        resumed,
        committed_sequence=committed,
        durable_tail=durable_tail_a,
        full_baseline=full_a,
    )
    outcomes["VS01-REC-002"] = _pass("numeric reconnect replayed strict N+1 suffix")
    outcomes["VS01-REC-006"] = _pass("intentional transport cut retained Run and resumed")
    numeric = await _collect_stream(
        base_url,
        view_a.run_id,
        str(full_a.events[0].sequence),
        timeout_seconds=timeout_seconds,
    )
    opaque = await _collect_stream(
        base_url,
        view_a.run_id,
        full_a.events[0].event_id,
        timeout_seconds=timeout_seconds,
    )
    assert_numeric_resume(
        full_a,
        numeric,
        committed_sequence=full_a.events[0].sequence,
        durable_tail=durable_tail_a,
        full_baseline=full_a,
    )
    assert_numeric_opaque_suffix_equal(numeric, opaque)
    outcomes["VS01-REC-003"] = _pass(
        "numeric and opaque same-Run cursors returned the exact baseline identity/content suffix"
    )

    terminal_event = full_a.events[-1]
    if terminal_event.type in {"run.completed", "run.failed"}:
        if terminal_event.type == "run.completed":
            outcome = "SUCCESS"
        else:
            outcome = {
                "FAILED": "FAILURE",
                "CANCELLED": "CANCELLED",
            }[terminal_event.payload["status"]]
        assert_terminal_stream(full_a, outcome=outcome)
        if outcome == "SUCCESS":
            outcomes["VS01-SSE-011"] = _pass(
                "real success stream closed after release.completed/run.completed"
            )
        else:
            outcomes["VS01-SSE-012"] = _pass(
                "real failure stream closed with the frozen run.failed payload",
                {
                    "status": terminal_event.payload["status"],
                    "failure_stage": terminal_event.payload["failure_stage"],
                },
            )
        terminal_equal = await _collect_stream(
            base_url,
            view_a.run_id,
            str(terminal_event.sequence),
            timeout_seconds=timeout_seconds,
        )
        assert_terminal_cursor_response(terminal_equal, expected_sequence=terminal_event.sequence)
        outcomes["VS01-REC-010"] = _pass("terminal-equal cursor closed with zero frames")
    if any(not frame.events for frame in (full_a, full_b)):
        raise GateError("SSE event capture unexpectedly empty")
    return outcomes, public_values, {"A": full_a, "B": full_b}


async def _verify_post_restart_sse(
    base_url: str,
    baselines: Mapping[str, LiveStreamObservation],
    post_restart_projections: Mapping[str, Mapping[str, Any]],
    *,
    timeout_seconds: float,
    restart_evidence: Mapping[str, Any],
) -> tuple[dict[str, JsonObject], list[Any]]:
    if set(baselines) != {"A", "B"} or set(post_restart_projections) != {"A", "B"}:
        raise GateError("post-restart SSE verification requires exact A/B evidence")
    start_count = restart_evidence.get("start_count")
    boundaries = restart_evidence.get("process_boundary_ids")
    if (
        restart_evidence.get("managed_process") is not True
        or type(start_count) is not int
        or start_count < 2
        or not isinstance(boundaries, list)
        or len(boundaries) != start_count
        or not all(isinstance(value, str) and value for value in boundaries)
        or len(set(boundaries)) != len(boundaries)
    ):
        raise GateError("post-restart SSE evidence lacks distinct managed process boundaries")
    public_values: list[Any] = []
    run_evidence: dict[str, Any] = {}
    for alias in ("A", "B"):
        before = baselines[alias]
        if len(before.events) < 2 or not before.stream_exhausted:
            raise GateError(f"Run {alias} lacks a finite pre-restart durable SSE baseline")
        terminal = before.events[-1]
        if terminal.type not in {"run.completed", "run.failed"}:
            raise GateError(f"Run {alias} pre-restart SSE baseline is not terminal")
        post_projection = post_restart_projections[alias]
        view = validate_run_projection(post_projection, expected_run_id=before.requested_run_id)
        if (
            not view.terminal["is_terminal"]
            or view.terminal["sequence"] != terminal.sequence
            or view.terminal["event_id"] != terminal.event_id
            or view.projection_sequence < terminal.sequence
        ):
            raise GateError(f"Run {alias} post-restart projection lost terminal identity")
        post_full = await _collect_stream(
            base_url,
            before.requested_run_id,
            "0",
            timeout_seconds=timeout_seconds,
        )
        before_signature = [
            (event.sequence, event.event_id, event.canonical_content_sha256)
            for event in before.events
        ]
        post_signature = [
            (event.sequence, event.event_id, event.canonical_content_sha256)
            for event in post_full.events
        ]
        if before_signature != post_signature or not post_full.stream_exhausted:
            raise GateError(f"Run {alias} durable SSE replay changed across restart")
        cursor = before.events[0].sequence
        suffix = await _collect_stream(
            base_url,
            before.requested_run_id,
            str(cursor),
            timeout_seconds=timeout_seconds,
        )
        assert_numeric_resume(
            before,
            suffix,
            committed_sequence=cursor,
            durable_tail=terminal.sequence,
        )
        expected_suffix = [item for item in post_signature if item[0] > cursor]
        actual_suffix = [
            (event.sequence, event.event_id, event.canonical_content_sha256)
            for event in suffix.events
        ]
        if actual_suffix != expected_suffix:
            raise GateError(f"Run {alias} post-restart cursor suffix changed")
        terminal_equal = await _collect_stream(
            base_url,
            before.requested_run_id,
            str(terminal.sequence),
            timeout_seconds=timeout_seconds,
        )
        assert_terminal_cursor_response(terminal_equal, expected_sequence=terminal.sequence)
        public_values.extend(
            [
                post_projection,
                _public_stream_value(post_full),
                _public_stream_value(suffix),
                _public_stream_value(terminal_equal),
            ]
        )
        run_evidence[alias] = {
            "run_id": before.requested_run_id,
            "replayed_events": len(post_full.events),
            "terminal_sequence": terminal.sequence,
            "terminal_event_id_sha256": hashlib.sha256(terminal.event_id.encode()).hexdigest(),
            "full_replay_sha256": sha256_json(post_signature),
            "numeric_cursor_checked": cursor,
            "terminal_equal_checked": True,
        }
    evidence = {"process": dict(restart_evidence), "runs": run_evidence}
    return (
        {
            "VS01-REC-011": _pass(
                "real A/B projection, full SSE replay, numeric suffix and terminal "
                "cursor survived restart",
                evidence,
            ),
            "VS01-REC-015": _pass(
                "new backend process retained exact A/B resources and durable SSE "
                "history in one database",
                evidence,
            ),
        },
        public_values,
    )


def _service(raw: Mapping[str, Any], name: str) -> ManagedService:
    return ManagedService(
        name=name,
        command=tuple(raw["command"]),
        cwd=raw["cwd"],
        url=raw["url"],
        health_path=str(raw.get("health_path", "/")),
        extra_env=raw.get("extra_env", {}),
    )


def _browser_scenario(
    config: Mapping[str, Any],
    checkpoint_a: Any,
    checkpoint_b: Any,
    projection_b: Mapping[str, Any],
    alternate: Mapping[str, Any],
    financial: Mapping[str, Any],
) -> JsonObject:
    object_request = config["object_a"]
    tasks = projection_b.get("tasks")
    if not isinstance(tasks, list) or not tasks or not isinstance(tasks[0], dict):
        raise GateError("foreign real projection does not contain a Task for browser quarantine")
    task_id = tasks[0].get("task_id")
    if not isinstance(task_id, str) or not task_id:
        raise GateError("foreign real Task identity is unavailable")
    return {
        "schemaVersion": "phase4-vs01-frontend-scenario/v1",
        "object": {
            "objectId": checkpoint_a.object_id,
            "symbol": object_request["symbol"].strip().upper(),
            "companyName": object_request["company_name"],
        },
        "goalText": config["goal_a"],
        "asOf": config["as_of"],
        "missingRunId": f"RUN-MISSING-{secrets.token_hex(12).upper()}",
        "missingErrorCode": "NOT_FOUND",
        "foreign": {
            "objectId": checkpoint_b.object_id,
            "runId": checkpoint_b.run_id,
            "taskId": task_id,
            "sentinels": [
                config["object_b"]["symbol"].strip().upper(),
                config["object_b"]["company_name"],
            ],
        },
        "alternate": dict(alternate),
        "financial": dict(financial),
        "backendUnavailableFrontendUrl": config["frontend_unavailable"]["url"],
        "primaryApiBaseUrl": config["frontend_api_base_url"],
        "unavailableApiBaseUrl": config["frontend_unavailable_api_base_url"],
    }


def _browser_financial_scenario(
    transport: UrllibJsonTransport,
    *,
    object_id: str,
    run_id: str,
) -> JsonObject:
    response = transport.request(
        "GET",
        f"/api/research-runs/{quote(run_id, safe='')}/result",
        headers={"X-Phase4-Contract-Version": CORE_CONTRACT_VERSION},
    )
    if response.status_code != 200:
        raise GateError("released financial Run is unavailable for browser evidence")
    body = response.json_object()
    metrics = validate_released_result_projection(
        body,
        expected_object_id=object_id,
        expected_run_id=run_id,
    )
    for metric in metrics:
        if not isinstance(metric, dict):
            continue
        metric_id = metric.get("metric_id")
        metric_run_id = metric.get("run_id")
        canonical = metric.get("canonical_value")
        if (
            isinstance(metric_id, str)
            and metric_id
            and metric_run_id == run_id
            and isinstance(canonical, str)
            and canonical
        ):
            try:
                numeric = float(canonical)
            except ValueError:
                continue
            if math.isfinite(numeric) and str(numeric) != canonical:
                return {
                    "objectId": object_id,
                    "runId": run_id,
                    "metricId": metric_id,
                    "adversarialProperty": "NUMBER_STRING_ROUNDTRIP_CHANGES",
                }
    raise GateError("released result lacks an adversarial canonical decimal")


def _playwright_control_evidence(path: Path) -> dict[str, JsonObject]:
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GateError("Playwright control report is invalid") from exc
    observed: dict[str, JsonObject] = {}

    def visit(value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                visit(item)
            return
        if not isinstance(value, dict):
            return
        annotations = value.get("annotations")
        if isinstance(annotations, list):
            controls = [
                annotation.get("description")
                for annotation in annotations
                if isinstance(annotation, dict) and annotation.get("type") == "vs01-control"
            ]
            if controls:
                results = value.get("results")
                if not isinstance(results, list) or len(results) != 1:
                    raise GateError("each Playwright control annotation needs one no-retry result")
                execution = results[0]
                if not isinstance(execution, dict):
                    raise GateError("Playwright control execution result is malformed")
                passed = (
                    value.get("expectedStatus") == "passed"
                    and value.get("status") == "expected"
                    and execution.get("status") == "passed"
                    and not execution.get("errors")
                )
                duration = execution.get("duration")
                for control_id in controls:
                    if control_id not in EXPECTED_BROWSER_CONTROLS:
                        raise GateError("Playwright emitted an unexpected VS01 control annotation")
                    if control_id in observed:
                        raise GateError("Playwright emitted a duplicate VS01 control annotation")
                    observed[control_id] = {
                        "status": "PASS" if passed else "FAIL",
                        "expected_status": value.get("expectedStatus"),
                        "execution_status": execution.get("status"),
                        "duration_ms": duration if isinstance(duration, int) else None,
                    }
        for item in value.values():
            visit(item)

    visit(report)
    if set(observed) != EXPECTED_BROWSER_CONTROLS:
        raise GateError("Playwright report lacks the exact integrated browser control annotations")
    failed = sorted(
        control_id for control_id, evidence in observed.items() if evidence["status"] != "PASS"
    )
    if failed:
        raise GateError(f"Playwright annotated controls failed: {failed}")
    return observed


def _run_browser(
    config: Mapping[str, Any],
    scenario_path: Path,
    artifact_root: Path,
    *,
    secret_sentinel: str,
) -> JsonObject:
    browser = config["browser"]
    cwd = Path(browser["cwd"])
    if artifact_root.exists() or artifact_root.is_symlink():
        raise GateError("browser artifact directory already exists; use a fresh output directory")
    env = {
        "VS01_FRONTEND_URL": config["frontend"]["url"],
        "VS01_BROWSER_SCENARIO_FILE": str(scenario_path.resolve()),
        "VS01_BROWSER_ARTIFACT_DIR": str(artifact_root.resolve()),
        "VFAS_VS01_SECRET_SENTINEL": secret_sentinel,
    }
    launcher = browser.get("node24_command")
    if (
        not isinstance(launcher, (list, tuple))
        or not launcher
        or not all(isinstance(part, str) and part for part in launcher)
    ):
        raise GateError("browser.node24_command must be a reviewed command-string launcher")
    version = run_command(
        [*launcher, "node --version"],
        cwd=cwd,
        env=env,
        timeout_seconds=60,
    )
    version_text = version.stdout.strip()
    if version.returncode != 0 or re.fullmatch(r"v24\.\d+\.\d+", version_text) is None:
        raise GateError("integrated browser launcher did not prove Node 24")
    observation = run_command(
        [*launcher, shlex.join(browser["command"])],
        cwd=cwd,
        env=env,
        timeout_seconds=float(browser.get("timeout_seconds", 600)),
    )
    if observation.returncode != 0:
        raise GateError("real browser VS01 command failed")
    report_path = artifact_root / "playwright-result.json"
    return {
        "summary": parse_playwright_result(report_path),
        "controls": _playwright_control_evidence(report_path),
        "node_version": version_text,
    }


def _browser_outcomes(report: Mapping[str, Any]) -> dict[str, JsonObject]:
    controls = report.get("controls")
    summary = report.get("summary")
    if not isinstance(controls, dict) or set(controls) != EXPECTED_BROWSER_CONTROLS:
        raise GateError("browser report does not map the exact browser control set")
    result: dict[str, JsonObject] = {}
    for control_id in sorted(EXPECTED_BROWSER_CONTROLS):
        annotation = controls[control_id]
        if not isinstance(annotation, dict) or annotation.get("status") != "PASS":
            raise GateError(f"browser control did not pass: {control_id}")
        result[control_id] = _pass(
            "real Playwright annotated scenario passed",
            {
                "control_annotation": control_id,
                "execution": dict(annotation),
                "playwright_summary": dict(summary) if isinstance(summary, dict) else {},
                "node_version": report.get("node_version"),
                "browser_response_mocks": False,
            },
        )
    result["VS01-E2E-003"] = _pass(
        "same production frontend journey passed and unavailable backend showed no fallback",
        {
            "source_controls": sorted(EXPECTED_BROWSER_CONTROLS),
            "node_version": report.get("node_version"),
        },
    )
    return result


def _tracked_candidate_clean() -> bool:
    observation = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return observation.returncode == 0 and observation.stdout == ""


def _scan_public_evidence(
    public_values: Sequence[Any],
    outcomes: dict[str, JsonObject],
    *,
    sentinel: str,
) -> None:
    try:
        evidence = scan_public_surface(list(public_values), sentinel=sentinel)
    except PublicSurfaceViolation as exc:
        failure_evidence = {
            "public_evidence_items": len(public_values),
            "violation_detected": True,
        }
        outcomes["VS01-SEC-001"] = _fail(
            "public API/SSE evidence failed the credential/sentinel scan",
            failure_evidence,
        )
        outcomes["VS01-SEC-002"] = _fail(
            "public API/SSE evidence failed the hidden-reasoning/provider/path scan",
            failure_evidence,
        )
        raise GateError("public evidence security controls failed") from exc
    outcomes["VS01-SEC-001"] = _pass(
        "retained API/SSE evidence and the real-browser scan receipt had zero secret leakage",
        {**evidence, "public_evidence_items": len(public_values)},
    )
    outcomes["VS01-SEC-002"] = _pass(
        "retained API/SSE evidence and the real-browser scan receipt excluded hidden "
        "reasoning/provider/path detail",
        {**evidence, "public_evidence_items": len(public_values)},
    )


def _cleanup_isolated_database(
    isolation: PostgreSQLIsolation | None,
    outcomes: dict[str, JsonObject],
    findings: list[JsonObject],
) -> None:
    if isolation is None or not isolation.created:
        return
    evidence = isolation.safe_evidence()
    try:
        isolation.drop()
        if isolation.created:
            raise GateError("PostgreSQL isolation still reports created after drop")
    except Exception as exc:
        outcomes["VS01-REC-013"] = _fail(
            "runner-created PostgreSQL database cleanup did not complete",
            {**evidence, "drop_completed": False},
        )
        findings.append(
            {
                "finding_id": "VS01-X4-CLEANUP-001",
                "severity": "HIGH",
                "contract_requirement": (
                    "runner-created database cleanup remains exact and bounded"
                ),
                "observed_behavior": (f"isolated database cleanup failed ({type(exc).__name__})"),
                "owner": "PARENT_SHARED",
                "blocking_vs01": True,
                "expected_remediation_evidence": (
                    "drop only the database digest recorded in the result using the "
                    "configured admin boundary"
                ),
            }
        )
        return
    outcomes["VS01-REC-013"] = _pass(
        "runner dropped the exact generated PostgreSQL database through its namespace guard",
        {**evidence, "drop_completed": True},
    )


def _run_integrated(
    config: Mapping[str, Any],
    manifest: Mapping[str, Any],
    checks: Sequence[Mapping[str, Any]],
    output_root: Path,
) -> tuple[dict[str, Any], int]:
    outcomes = _self_test_outcomes(manifest, checks)
    findings: list[JsonObject] = _recorded_findings()
    environment: JsonObject = {
        "real_backend": False,
        "real_frontend": False,
        "real_sse": False,
        "real_postgresql_16": False,
        "postgresql_causal_binding": False,
        "managed_backend_restart": False,
        "mock_business_responses": False,
        "candidate_tracked_clean_at_start": _tracked_candidate_clean(),
        "runtime_sse_capture_bound": False,
        "api_sse_public_surface_scan_completed": False,
        "browser_public_surface_scan_completed": False,
        "x_delivery_binding_verified": False,
    }
    sentinel = f"VS01_SENTINEL_{secrets.token_urlsafe(32)}"
    postgres_config = config["postgres"]
    admin_url = os.environ.get(postgres_config["admin_url_env"], "")
    isolation: PostgreSQLIsolation | None = None
    backend: ManagedService | None = None
    frontend: ManagedService | None = None
    frontend_unavailable: ManagedService | None = None
    public_values: list[Any] = []
    database_url: str | None = None
    x_delivery: JsonObject = {}
    execution_root: Path | None = None
    try:
        if environment["candidate_tracked_clean_at_start"] is not True:
            raise GateError("integrated candidate must be clean, including untracked files")
        x_delivery = collect_integrated_x_delivery_metadata(config["x_delivery_sha"])
        if x_delivery.get("x_delivery_binding_verified") is not True:
            raise GateError(
                "Parent acceptance subtree is not bound to the configured pushed CodeX X revision"
            )
        environment["x_delivery_binding_verified"] = True
        execution_root = output_root / f"execution-{secrets.token_hex(16)}"
        execution_root.mkdir(parents=True, exist_ok=False)
        if not admin_url:
            raise GateError(
                f"required PostgreSQL URL environment variable is absent: "
                f"{postgres_config['admin_url_env']}"
            )
        isolation = PostgreSQLIsolation(
            admin_url=admin_url,
            database_prefix=postgres_config["database_prefix"],
            psql_binary=str(postgres_config.get("psql_binary", "psql")),
        )
        pg_evidence = isolation.preflight()
        libpq_database_url = isolation.create()
        database_url = sqlalchemy_async_database_url(libpq_database_url)
        environment["real_postgresql_16"] = True
        migration = run_command(
            postgres_config["migration_command"],
            cwd=REPOSITORY_ROOT,
            env={"DATABASE_URL": database_url},
            timeout_seconds=float(postgres_config.get("migration_timeout_seconds", 180)),
        )
        if migration.returncode != 0:
            raise GateError("isolated PostgreSQL migration command failed")

        backend = _service(config["backend"], "backend")
        backend_env = {
            "DATABASE_URL": database_url,
            "VFAS_VS01_SECRET_SENTINEL": sentinel,
        }
        backend.start(
            inherited_env=backend_env,
            timeout_seconds=float(config.get("service_timeout_seconds", 60)),
        )
        environment["real_backend"] = True
        outcomes["VS01-REC-014"] = _pass(
            "managed product backend passed health readiness", backend.safe_evidence()
        )

        config_a = _backend_config(config, "A", backend.url)
        config_b = _backend_config(config, "B", backend.url)
        transport = RecordingJsonTransport(
            UrllibJsonTransport(
                backend.url,
                timeout_seconds=float(config.get("request_timeout_seconds", 10)),
            ),
            public_values,
        )
        report_a = run_backend_vs01(config_a, transport=transport)
        report_b = run_backend_vs01(config_b, transport=transport)
        _record_backend_report(report_a, outcomes, source="Run A")
        _record_backend_report(report_b, outcomes, source="Run B")
        if not report_a.passed or report_a.checkpoint is None:
            raise GateError("X1 Run A backend gate did not produce a checkpoint")
        if not report_b.passed or report_b.checkpoint is None:
            raise GateError("X1 Run B backend gate did not produce a checkpoint")
        identity_evidence = _check_cross_object_histories(
            transport, report_a.checkpoint, report_b.checkpoint
        )
        outcomes["VS01-ID-001"] = _pass(
            "real A/B Object histories remained disjoint", identity_evidence
        )
        cross_confirm = _check_cross_object_confirm(
            transport, config_a, report_a.checkpoint, report_b.checkpoint
        )
        outcomes["VS01-ID-002"] = _pass(
            "wrong-Object Confirm failed with zero Run mutation", cross_confirm
        )
        concurrent_confirm = _check_concurrent_confirm(
            transport, config_a, report_a.checkpoint.object_id
        )
        outcomes["VS01-BE-005"] = _pass(
            "real concurrent same-key Confirm returned one create and one immutable replay",
            concurrent_confirm,
        )
        outcomes["VS01-BE-009"] = _pass(
            "real new-key reuse of the concurrently consumed draft failed closed",
            concurrent_confirm,
        )
        projection_a = _public_projection(transport, report_a.checkpoint.run_id)
        projection_b = _public_projection(transport, report_b.checkpoint.run_id)
        public_values.extend([projection_a, projection_b])

        database_name_sha256 = isolation.safe_evidence().get("database_name_sha256")
        if not isinstance(database_name_sha256, str) or not re.fullmatch(
            r"[0-9a-f]{64}", database_name_sha256
        ):
            raise GateError("isolated database identity digest is unavailable")
        if not backend.boundary_ids:
            raise GateError("managed backend process boundary is unavailable")
        external_sse_evidence, capture_receipt = _capture_external_sse_evidence(
            config,
            database_name_sha256=database_name_sha256,
            backend_url=backend.url,
            backend_process_boundary_id=backend.boundary_ids[-1],
            run_ids={"A": report_a.checkpoint.run_id, "B": report_b.checkpoint.run_id},
            output_root=execution_root,
        )
        capture_binding = {
            name: capture_receipt[name]
            for name in (
                "capture_session_nonce_sha256",
                "database_name_sha256",
                "backend_process_boundary_id",
                "backend_base_url",
                "capture_driver_sha256",
            )
        }

        sse_outcomes, sse_public, sse_baselines = asyncio.run(
            _run_live_sse_matrix(
                backend.url,
                projection_a,
                projection_b,
                timeout_seconds=float(config.get("sse_timeout_seconds", 180)),
            )
        )
        outcomes.update(sse_outcomes)
        public_values.extend(sse_public)
        supplemental_outcomes, supplemental_public = _evaluate_external_sse_evidence(
            external_sse_evidence,
            expected_binding=capture_binding,
        )
        supplemental_outcomes["VS01-SSE-003"]["evidence"]["runtime_capture_receipt"] = (
            capture_receipt
        )
        outcomes.update(supplemental_outcomes)
        public_values.extend(supplemental_public)
        environment["runtime_sse_capture_bound"] = True
        environment["real_sse"] = True

        causal_postgresql = _prove_postgresql_causal_binding(
            isolation,
            transport,
            report_a.checkpoint,
        )
        environment["postgresql_causal_binding"] = True
        outcomes["VS01-REC-012"] = _pass(
            "PostgreSQL 16 was provisioned and causally bound to the managed Product read path",
            {**pg_evidence, **causal_postgresql},
        )

        backend.restart(
            inherited_env=backend_env,
            timeout_seconds=float(config.get("service_timeout_seconds", 60)),
        )
        restart = RestartEvidence(
            process_boundary_id=backend.boundary_ids[-1],
            api_process_restarted=True,
            persistence_backend="PostgreSQL 16",
            storage_preserved=True,
        )
        restarted_a = verify_restart_checkpoint(
            config_a, report_a.checkpoint, restart, transport=transport
        )
        restarted_b = verify_restart_checkpoint(
            config_b, report_b.checkpoint, restart, transport=transport
        )
        _record_backend_report(restarted_a, outcomes, source="Run A restart")
        _record_backend_report(restarted_b, outcomes, source="Run B restart")
        if not restarted_a.passed or not restarted_b.passed:
            raise GateError("X1 restart verification failed")
        environment["managed_backend_restart"] = True
        restart_evidence = backend.safe_evidence()
        post_restart_projections = {
            "A": _public_projection(transport, report_a.checkpoint.run_id),
            "B": _public_projection(transport, report_b.checkpoint.run_id),
        }
        restart_outcomes, restart_public = asyncio.run(
            _verify_post_restart_sse(
                backend.url,
                sse_baselines,
                post_restart_projections,
                timeout_seconds=float(config.get("sse_timeout_seconds", 180)),
                restart_evidence=restart_evidence,
            )
        )
        outcomes.update(restart_outcomes)
        public_values.extend(restart_public)

        assert_url_unreachable(config["unavailable_backend_url"])
        frontend = _service(config["frontend"], "frontend")
        frontend_unavailable = _service(config["frontend_unavailable"], "frontend-unavailable")
        frontend.start(
            inherited_env={
                "VFAS_VS01_SECRET_SENTINEL": sentinel,
            },
            timeout_seconds=float(config.get("service_timeout_seconds", 60)),
        )
        frontend_unavailable.start(
            inherited_env={
                "VFAS_VS01_SECRET_SENTINEL": sentinel,
            },
            timeout_seconds=float(config.get("service_timeout_seconds", 60)),
        )
        environment["real_frontend"] = True
        browser_alternate = _admit_browser_alternate_run(
            transport,
            config_a,
            report_a.checkpoint.object_id,
        )
        browser_financial = _browser_financial_scenario(
            transport,
            object_id=report_a.checkpoint.object_id,
            run_id=report_a.checkpoint.run_id,
        )
        scenario = _browser_scenario(
            config,
            report_a.checkpoint,
            report_b.checkpoint,
            projection_b,
            browser_alternate,
            browser_financial,
        )
        scenario_path = execution_root / "browser-scenario.json"
        write_json(scenario_path, scenario)
        browser_report = _run_browser(
            config,
            scenario_path,
            execution_root / "browser",
            secret_sentinel=sentinel,
        )
        browser_outcomes = _browser_outcomes(browser_report)
        outcomes.update(browser_outcomes)
        environment["browser_public_surface_scan_completed"] = True
        public_values.append(
            {
                "surface": "real_browser_public_surface_gate_receipt",
                "node_version": browser_report["node_version"],
                "control_statuses": {
                    control_id: browser_report["controls"][control_id]["status"]
                    for control_id in sorted(EXPECTED_BROWSER_CONTROLS)
                },
                "raw_browser_error_text_retained": False,
            }
        )
        _scan_public_evidence(public_values, outcomes, sentinel=sentinel)
        environment["api_sse_public_surface_scan_completed"] = True
        outcomes["VS01-E2E-001"] = _pass(
            "one isolated execution used real backend/PostgreSQL/Run/SSE/frontend",
            {key: environment[key] for key in environment if key.startswith("real_")},
        )
        outcomes["VS01-E2E-004"] = _pass(
            "no mock business response was configured and all reality predicates were observed"
        )
    except Exception as exc:
        findings.append(
            {
                "finding_id": "VS01-X4-RUN-001",
                "severity": "BLOCKING",
                "contract_requirement": "real integrated VS01 must complete all required controls",
                "observed_behavior": (
                    f"integrated orchestration stopped ({type(exc).__name__}): {exc}"
                ),
                "owner": "PARENT_SHARED",
                "blocking_vs01": True,
                "expected_remediation_evidence": (
                    "rerun the same command after resolving the named "
                    "product/environment dependency"
                ),
            }
        )
    finally:
        for service in (frontend_unavailable, frontend, backend):
            if service is not None:
                service.stop()
        _cleanup_isolated_database(isolation, outcomes, findings)
    # E2E-005 is credited only after cleanup has supplied its own required outcome.
    required_ids = {
        control["control_id"]
        for control in manifest["controls"]
        if control["layer"] != "HARNESS_SELF_TEST" and control["control_id"] != "VS01-E2E-005"
    }
    if required_ids <= set(outcomes) and all(
        outcomes[control_id].get("status") == "PASS" for control_id in required_ids
    ):
        outcomes["VS01-E2E-005"] = _pass("every activated control has a PASS result")
    result = build_result(
        manifest,
        outcomes,
        mode="REAL_VS01_EXECUTION",
        harness_checks=checks,
        environment=environment,
        findings=findings,
        delivery=x_delivery,
    )
    return result, 0 if result["vs01_integrated_status"] == "PASS" else 1


def _load_manifest() -> JsonObject:
    current = aggregate_manifest(load_control_fragments())
    if MANIFEST_PATH.is_file():
        stored = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        comparable_current = {**current, "generated_at": stored.get("generated_at")}
        if sha256_json(stored) != sha256_json(comparable_current):
            raise GateError(
                "tracked VS01 manifest is stale; rerun with --refresh-manifest and review the diff"
            )
        return stored
    return current


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode", choices=("self-test", "integrated"), help="harness-only or real VS01 execution"
    )
    parser.add_argument("--config", type=Path, help="required for integrated mode")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=VS01_ROOT / "out" / "latest",
        help="non-authoritative result directory (default: acceptance/phase4/vs01/out/latest)",
    )
    parser.add_argument(
        "--refresh-manifest",
        action="store_true",
        help="regenerate the tracked aggregate from reviewed fragments before running",
    )
    args = parser.parse_args(argv)
    if args.refresh_manifest:
        materialize_manifest()
    try:
        manifest = _load_manifest()
    except Exception as exc:
        print(f"VS01 manifest preflight failed: {exc}", file=sys.stderr)
        return 2
    checks = _harness_checks()
    if args.mode == "self-test":
        result = build_result(
            manifest,
            _self_test_outcomes(manifest, checks),
            mode="HARNESS_SELF_TEST",
            harness_checks=checks,
            findings=_recorded_findings(),
        )
        exit_code = (
            0
            if result["phase4_codex_x"] == "PASS" and result["ready_for_parent_vs01_gate"] is True
            else 1
        )
    else:
        if args.config is None:
            parser.error("integrated mode requires --config")
        try:
            config = load_integrated_config(args.config.resolve())
            result, exit_code = _run_integrated(config, manifest, checks, args.output_dir)
        except Exception as exc:
            result = build_result(
                manifest,
                _self_test_outcomes(manifest, checks),
                mode="REAL_VS01_EXECUTION",
                harness_checks=checks,
                findings=[
                    *_recorded_findings(),
                    {
                        "finding_id": "VS01-X4-CONFIG-001",
                        "severity": "BLOCKING",
                        "contract_requirement": "safe complete integrated runner configuration",
                        "observed_behavior": (
                            f"configuration rejected ({type(exc).__name__}): {exc}"
                        ),
                        "owner": "PARENT_SHARED",
                        "blocking_vs01": True,
                        "expected_remediation_evidence": (
                            "validated config using only real product commands and "
                            "environment-referenced PostgreSQL credentials"
                        ),
                    },
                ],
            )
            exit_code = 1
    json_path, markdown_path = write_result_bundle(args.output_dir, result)
    print(
        json.dumps(
            {
                "HARNESS_STATUS": result["harness_status"],
                "VS01_INTEGRATED_STATUS": result["vs01_integrated_status"],
                "result_json": str(json_path.resolve()),
                "result_markdown": str(markdown_path.resolve()),
            },
            sort_keys=True,
        )
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
