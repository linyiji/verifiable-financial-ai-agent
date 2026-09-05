from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.domain.runtime_event import (
    EVENT_CONTRACT_VERSION,
    EVENT_EFFECT_BY_TYPE,
    GRAPH_VERSION_RUNTIME_EVENT_TYPES,
    PAYLOAD_SCHEMA_VERSION,
    SUPPORTED_RUNTIME_EVENT_TYPES,
    TASK_ID_REQUIRED_RUNTIME_EVENT_TYPES,
    UNSUPPORTED_RUNTIME_EVENT_TYPES,
    NormalizedRuntimeEventV1,
    RuntimeEvent,
    RuntimeEventEffect,
    RuntimeEventType,
    normalize_runtime_event_v1,
)

SCHEMA_PATH = Path("contracts/events/runtime_event.schema.json")


def raw_event(
    event_type: RuntimeEventType,
    *,
    payload: dict[str, object],
    task_id: str | None = None,
    sequence: int = 1,
) -> RuntimeEvent:
    return RuntimeEvent(
        event_id=f"EVT-{sequence}",
        run_id="RUN-A",
        task_id=task_id,
        type=event_type,
        timestamp=datetime(2026, 9, 5, tzinfo=UTC),
        sequence=sequence,
        payload=payload,
    )


def test_frozen_inventory_schema_and_effect_table_are_total() -> None:
    schema = json.loads(SCHEMA_PATH.read_text())
    disposition = schema["x-runtime-event-disposition"]
    raw_types = [event_type.value for event_type in RuntimeEventType]
    supported = {event_type.value for event_type in SUPPORTED_RUNTIME_EVENT_TYPES}
    unsupported = {event_type.value for event_type in UNSUPPORTED_RUNTIME_EVENT_TYPES}

    assert len(raw_types) == len(set(raw_types)) == disposition["raw_type_count"] == 55
    assert schema["properties"]["type"]["enum"] == raw_types
    assert supported.isdisjoint(unsupported)
    assert supported | unsupported == set(raw_types)
    assert len(supported) == disposition["supported_v1_count"] == 47
    assert unsupported == set(disposition["unsupported_v1"])
    assert {event_type.value for event_type in GRAPH_VERSION_RUNTIME_EVENT_TYPES} == set(
        disposition["graph_version_required_v1"]
    )
    assert {event_type.value for event_type in TASK_ID_REQUIRED_RUNTIME_EVENT_TYPES} == set(
        disposition["task_id_required_v1"]
    )
    assert set(EVENT_EFFECT_BY_TYPE) == SUPPORTED_RUNTIME_EVENT_TYPES
    assert sum(disposition["effect_counts"].values()) == 47
    for effect, expected_count in disposition["effect_counts"].items():
        actual_count = sum(value.value == effect for value in EVENT_EFFECT_BY_TYPE.values())
        assert actual_count == expected_count

    payload_branches = schema["allOf"][-1]["oneOf"]
    assert {branch["properties"]["type"]["const"] for branch in payload_branches} == supported


def test_public_normalizer_redacts_legacy_retry_and_internal_details() -> None:
    normalized = normalize_runtime_event_v1(
        raw_event(
            RuntimeEventType.TASK_PROGRESS,
            task_id="TASK-A",
            payload={
                "action": "retry_scheduled",
                "attempt": 2,
                "error_code": "TASK_EXECUTION_FAILED",
                "exception": "DO_NOT_EXPOSE",
            },
        )
    )

    assert normalized.event_contract_version == EVENT_CONTRACT_VERSION
    assert normalized.payload_schema_version == PAYLOAD_SCHEMA_VERSION
    assert normalized.payload == {"attempt": 2, "error_code": "TASK_EXECUTION_FAILED"}
    assert normalized.effect is RuntimeEventEffect.PATCH_PROJECTION
    assert normalized.projection_refresh_required is False
    assert normalized.graph_version is None
    assert "action" not in normalized.model_dump_json()
    assert "DO_NOT_EXPOSE" not in normalized.model_dump_json()


def test_graph_watermark_is_promoted_and_legacy_metadata_is_removed() -> None:
    normalized = normalize_runtime_event_v1(
        raw_event(
            RuntimeEventType.GRAPH_EDGE_ADDED,
            task_id="TASK-B",
            payload={
                "replan_id": "REPLAN-1",
                "source_task_id": "TASK-A",
                "target_task_id": "TASK-B",
                "graph_version": 3,
                "internal_note": "DO_NOT_EXPOSE",
            },
        )
    )

    assert normalized.graph_version == 3
    assert normalized.payload == {
        "replan_id": "REPLAN-1",
        "source_task_id": "TASK-A",
        "target_task_id": "TASK-B",
    }
    assert normalized.effect is RuntimeEventEffect.REFRESH_PROJECTION
    assert normalized.projection_refresh_required is True


def test_normalized_model_rejects_unsupported_sparse_and_inconsistent_events() -> None:
    base = {
        "event_id": "EVT-1",
        "run_id": "RUN-A",
        "task_id": "TASK-A",
        "timestamp": datetime(2026, 9, 5, tzinfo=UTC),
        "sequence": 1,
        "payload": {"attempt": 1},
        "graph_version": None,
        "effect": RuntimeEventEffect.PATCH_PROJECTION,
        "projection_refresh_required": False,
    }
    with pytest.raises(ValidationError, match="unsupported Phase 4 runtime event"):
        NormalizedRuntimeEventV1(
            **(base | {"type": RuntimeEventType.SCHEME_GENERATION_STARTED, "payload": {}})
        )
    with pytest.raises(ValidationError, match="requires task_id"):
        NormalizedRuntimeEventV1(
            **(base | {"type": RuntimeEventType.TASK_STARTED, "task_id": None})
        )
    with pytest.raises(ValueError, match="missing fields"):
        normalize_runtime_event_v1(
            raw_event(RuntimeEventType.TASK_STARTED, task_id="TASK-A", payload={})
        )
    with pytest.raises(ValidationError, match="graph_version must be non-null"):
        NormalizedRuntimeEventV1(
            **(
                base
                | {
                    "type": RuntimeEventType.RUN_STARTED,
                    "task_id": None,
                    "payload": {},
                }
            )
        )
    with pytest.raises(ValidationError, match="event_id must be a safe public identifier"):
        NormalizedRuntimeEventV1(
            **(base | {"event_id": " EVT-1", "type": RuntimeEventType.TASK_STARTED})
        )


def test_frontend_decoder_guard_and_fingerprint_fail_closed_without_payload_leak() -> None:
    module_url = (Path.cwd() / "apps/web/src/runtime/RuntimeTransport.ts").as_uri()
    schema_url = SCHEMA_PATH.resolve().as_uri()
    script = f"""
      import assert from "node:assert/strict";
      import {{ createHash }} from "node:crypto";
      import {{ readFile }} from "node:fs/promises";
      const runtime = await import({json.dumps(module_url)});
      const schema = JSON.parse(await readFile(new URL({json.dumps(schema_url)}), "utf8"));
      const disposition = schema["x-runtime-event-disposition"];
      assert.equal(runtime.RUNTIME_EVENT_TYPES_V1.length, 55);
      assert.equal(runtime.SUPPORTED_RUNTIME_EVENT_TYPES_V1.length, 47);
      assert.equal(runtime.UNSUPPORTED_RUNTIME_EVENT_TYPES_V1.length, 8);
      assert.deepEqual(
        [...runtime.GRAPH_VERSION_RUNTIME_EVENT_TYPES_V1].sort(),
        [...disposition.graph_version_required_v1].sort()
      );
      assert.deepEqual(
        [...runtime.TASK_ID_REQUIRED_RUNTIME_EVENT_TYPES_V1].sort(),
        [...disposition.task_id_required_v1].sort()
      );

      const wire = {{
        event_contract_version: "phase4-runtime-event/v1",
        event_id: "EVT-1",
        run_id: "RUN-A",
        task_id: "TASK-A",
        type: "task.progress",
        timestamp: "2026-09-05T00:00:00Z",
        sequence: 1,
        payload_schema_version: 1,
        payload: {{
          progress: 0.5,
          progress_scale: "RATIO_0_1",
          message_code: "TOP_SECRET_SENTINEL"
        }},
        graph_version: null,
        effect: "PATCH_PROJECTION",
        projection_refresh_required: false
      }};
      const guard = new runtime.RuntimeEventIngestionGuard({{
        runId: "RUN-A",
        initialSequence: 0,
        authoritativeTaskIds: ["TASK-A", "TASK-B"]
      }});
      const applied = guard.ingest(wire, {{ id: "1", event: "task.progress" }});
      assert.equal(applied.kind, "APPLIED");
      assert.deepEqual(applied.event.payload, {{
        progress: 0.5,
        progressScale: "RATIO_0_1",
        messageCode: "TOP_SECRET_SENTINEL"
      }});
      const fingerprint = runtime.runtimeEventFingerprintV1(applied.event);
      assert.match(fingerprint, /^sha256:[0-9a-f]{{64}}$/);
      const canonicalize = (value) => {{
        if (value === null || typeof value !== "object") return JSON.stringify(value);
        if (Array.isArray(value)) return `[${{value.map(canonicalize).join(",")}}]`;
        return `{{${{Object.keys(value).sort().map(
          (key) => `${{JSON.stringify(key)}}:${{canonicalize(value[key])}}`
        ).join(",")}}}}`;
      }};
      const nodeCryptoFingerprint = `sha256:${{createHash("sha256")
        .update(canonicalize(applied.event))
        .digest("hex")}}`;
      assert.equal(fingerprint, nodeCryptoFingerprint);
      assert.equal(
        fingerprint,
        "sha256:098d7e738db751c1c3b01275cbbf2f5ae230f20b72f6d98a3a39041a21ee3232"
      );
      assert.equal(fingerprint.includes("TOP_SECRET_SENTINEL"), false);
      assert.equal(guard.ingest(wire, {{ id: "1", event: "task.progress" }}).kind, "DUPLICATE");
      assert.equal(guard.lastSequence, 1);

      const expectReason = (operation, reason) => {{
        assert.throws(operation, (error) =>
          error instanceof runtime.RuntimeIngestionError && error.reason === reason
        );
      }};
      expectReason(
        () => guard.ingest({{ ...wire, payload_schema_version: 2 }}),
        "UNSUPPORTED_EVENT"
      );
      expectReason(() => guard.ingest({{ ...wire, run_id: "RUN-B" }}), "WRONG_RUN");
      expectReason(
        () => guard.ingest({{ ...wire, sequence: 3, event_id: "EVT-3" }}),
        "SEQUENCE_GAP"
      );
      expectReason(() => guard.ingest({{
        ...wire,
        event_id: "EVT-2",
        sequence: 2,
        type: "graph.edge_added",
        task_id: "TASK-B",
        payload: {{
          replan_id: "REPLAN-1",
          source_task_id: "TASK-A",
          target_task_id: "TASK-FOREIGN"
        }},
        graph_version: 2,
        effect: "REFRESH_PROJECTION",
        projection_refresh_required: true
      }}, {{ id: "2", event: "graph.edge_added" }}), "WRONG_TASK");
      expectReason(() => guard.ingest({{
        ...wire,
        event_id: "EVT-2-EVIDENCE",
        sequence: 2,
        type: "evidence.accepted",
        task_id: null,
        payload: {{
          evidence_id: "EVD-1",
          field: "revenue",
          producer_task_id: "TASK-FOREIGN"
        }},
        effect: "OBSERVATION_ONLY"
      }}, {{ id: "2", event: "evidence.accepted" }}), "WRONG_TASK");
      assert.equal(guard.lastSequence, 1);

      const projectionGuard = new runtime.RuntimeEventIngestionGuard({{
        runId: "RUN-A",
        initialSequence: 0,
        authoritativeTaskIds: ["TASK-A"]
      }});
      let projectionError;
      try {{
        projectionGuard.ingest(
          wire,
          {{ id: "1", event: "task.progress" }},
          () => {{ throw new Error("RAW_REDUCER_SECRET_SENTINEL"); }}
        );
      }} catch (error) {{
        projectionError = error;
      }}
      assert.equal(projectionError.reason, "PROJECTION_REJECTED");
      assert.equal(String(projectionError).includes("RAW_REDUCER_SECRET_SENTINEL"), false);
      assert.equal(JSON.stringify(projectionError.identity).includes("TOP_SECRET_SENTINEL"), false);
      assert.deepEqual(Object.keys(projectionError.identity).sort(), [
        "eventId", "runId", "sequence", "taskId", "type"
      ]);
      assert.equal(projectionGuard.lastSequence, 0);
      assert.equal(
        projectionGuard.ingest(wire, {{ id: "1", event: "task.progress" }}).kind,
        "APPLIED"
      );
      assert.equal(projectionGuard.lastSequence, 1);
    """
    completed = subprocess.run(
        [
            "node",
            "--no-warnings",
            "--experimental-strip-types",
            "--input-type=module",
            "-e",
            script,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_sse_transport_emits_frozen_error_backoff_cursor_and_terminal_states() -> None:
    runtime_source_url = (Path.cwd() / "apps/web/src/runtime/RuntimeTransport.ts").as_uri()
    sse_source_url = (Path.cwd() / "apps/web/src/runtime/SSERuntimeTransport.ts").as_uri()
    script = """
      import assert from "node:assert/strict";
      import { readFile } from "node:fs/promises";
      import { stripTypeScriptTypes } from "node:module";

      const runtimeSource = await readFile(new URL(__RUNTIME_SOURCE_URL__), "utf8");
      const runtimeJavaScript = stripTypeScriptTypes(runtimeSource, { mode: "transform" });
      const runtimeModuleUrl = `data:text/javascript;base64,${Buffer.from(
        runtimeJavaScript
      ).toString("base64")}`;
      let sseSource = await readFile(new URL(__SSE_SOURCE_URL__), "utf8");
      sseSource = sseSource.replace(
        'from "./RuntimeTransport";',
        `from "${runtimeModuleUrl}";`
      );
      const sseJavaScript = stripTypeScriptTypes(sseSource, { mode: "transform" });
      const sseModuleUrl = `data:text/javascript;base64,${Buffer.from(
        sseJavaScript
      ).toString("base64")}`;
      const sse = await import(sseModuleUrl);

      const envelope = (code, retryable, recovery) => ({
        schema_version: "phase4-error/v1",
        error: {
          code,
          message: "Safe transport message",
          retryable,
          recovery,
          request_id: null,
          resource: null,
          details: {}
        }
      });
      const subscriptionOptions = (onStateChange, overrides = {}) => ({
        initialSequence: 0,
        authoritativeTaskIds: [],
        onStateChange,
        ...overrides
      });

      let requestHeaders;
      const cursorStates = [];
      const cursorErrors = [];
      const cursorTransport = new sse.SSERuntimeTransport({
        fetchImplementation: async (_input, init) => {
          requestHeaders = new Headers(init.headers);
          return new Response(
            JSON.stringify(envelope("INVALID_CURSOR", false, "SNAPSHOT_RELOAD")),
            { status: 400, headers: { "content-type": "application/json" } }
          );
        }
      });
      await cursorTransport.subscribe(
        "RUN-A",
        () => assert.fail("cursor rejection emitted an event"),
        (error) => cursorErrors.push(error),
        subscriptionOptions((state) => cursorStates.push(state))
      ).closed;
      assert.deepEqual(cursorStates.map((state) => state.kind), ["CONNECTING", "RECOVERING"]);
      assert.equal(cursorStates.at(-1).reason, "CURSOR_REJECTED");
      assert.equal(cursorStates.at(-1).lastSequence, 0);
      assert.equal(cursorErrors[0].code, "INVALID_CURSOR");
      assert.equal(requestHeaders.get("accept"), "text/event-stream");
      assert.equal(requestHeaders.get("last-event-id"), "0");

      const backoffStates = [];
      const backoffErrors = [];
      const now = Date.parse("2026-09-05T00:00:00Z");
      const backoffTransport = new sse.SSERuntimeTransport({
        now: () => now,
        fetchImplementation: async () => {
          throw new Error("RAW_NETWORK_SECRET_SENTINEL");
        }
      });
      await backoffTransport.subscribe(
        "RUN-A",
        () => assert.fail("network failure emitted an event"),
        (error) => backoffErrors.push(error),
        subscriptionOptions((state) => backoffStates.push(state), { attempt: 2 })
      ).closed;
      assert.deepEqual(backoffStates.map((state) => state.kind), ["CONNECTING", "BACKOFF"]);
      assert.equal(backoffStates.at(-1).attempt, 3);
      assert.equal(backoffStates.at(-1).retryAt, "2026-09-05T00:00:02.000Z");
      assert.equal(backoffStates.at(-1).error.error.code, "TRANSIENT_BACKEND_ERROR");
      assert.equal(JSON.stringify(backoffStates).includes("RAW_NETWORK_SECRET_SENTINEL"), false);
      assert.equal(backoffErrors[0].code, "TRANSIENT_BACKEND_ERROR");
      assert.equal(sse.runtimeBackoffDelayMillisecondsV1(1), 1000);
      assert.equal(sse.runtimeBackoffDelayMillisecondsV1(2), 2000);
      assert.equal(sse.runtimeBackoffDelayMillisecondsV1(99), 30000);

      const invalidStates = [];
      const invalidErrors = [];
      const invalidTransport = new sse.SSERuntimeTransport({
        fetchImplementation: async () => new Response(JSON.stringify({
          ...envelope("NOT_A_FROZEN_CODE", false, "NONE"),
          leaked: "UNSAFE_ENVELOPE_SENTINEL"
        }), { status: 500, headers: { "content-type": "application/json" } })
      });
      await invalidTransport.subscribe(
        "RUN-A",
        () => assert.fail("invalid error envelope emitted an event"),
        (error) => invalidErrors.push(error),
        subscriptionOptions((state) => invalidStates.push(state))
      ).closed;
      assert.equal(invalidStates.at(-1).kind, "FAILED");
      assert.equal(invalidStates.at(-1).error.error.code, "INTERNAL_ERROR");
      assert.equal(JSON.stringify(invalidStates).includes("UNSAFE_ENVELOPE_SENTINEL"), false);
      assert.equal(invalidErrors[0].code, "INTERNAL_ERROR");

      const terminalCursorStates = [];
      const terminalCursorEvents = [];
      const terminalCursorErrors = [];
      const terminalCursorCallbacks = [];
      let terminalCursorHeader;
      const terminalCursorTransport = new sse.SSERuntimeTransport({
        fetchImplementation: async (_input, init) => {
          terminalCursorHeader = new Headers(init.headers).get("last-event-id");
          return new Response("", {
            status: 200,
            headers: {
              "content-type": "text/event-stream; charset=utf-8",
              "X-Phase4-Contract-Version": "phase4-core/v1",
              "X-Phase4-Event-Contract-Version": "phase4-runtime-event/v1",
              "X-Run-Terminal": "true",
              "X-Terminal-Sequence": "4"
            }
          });
        }
      });
      await terminalCursorTransport.subscribe(
        "RUN-A",
        (event) => terminalCursorEvents.push(event),
        (error) => terminalCursorErrors.push(error),
        subscriptionOptions(
          (state) => terminalCursorStates.push(state),
          {
            initialSequence: 4,
            onTerminalAtCursor: (sequence) => terminalCursorCallbacks.push(sequence)
          }
        )
      ).closed;
      assert.equal(terminalCursorHeader, "4");
      assert.deepEqual(terminalCursorStates.map((state) => state.kind), ["CONNECTING"]);
      assert.deepEqual(terminalCursorCallbacks, [4]);
      assert.equal(terminalCursorEvents.length, 0);
      assert.equal(terminalCursorErrors.length, 0);

      const terminalWire = {
        event_contract_version: "phase4-runtime-event/v1",
        event_id: "EVT-1",
        run_id: "RUN-A",
        task_id: null,
        type: "run.completed",
        timestamp: "2026-09-05T00:00:00Z",
        sequence: 1,
        payload_schema_version: 1,
        payload: { status: "RELEASED" },
        graph_version: null,
        effect: "TERMINAL",
        projection_refresh_required: true
      };
      const terminalFrame = `id: 1\nevent: run.completed\ndata: ${JSON.stringify(
        terminalWire
      )}\n\n: heartbeat\n\n`;
      const terminalStates = [];
      const terminalEvents = [];
      const terminalErrors = [];
      const terminalTransport = new sse.SSERuntimeTransport({
        fetchImplementation: async () => new Response(terminalFrame, {
          status: 200,
          headers: {
            "content-type": "text/event-stream",
            "X-Phase4-Contract-Version": "phase4-core/v1",
            "X-Phase4-Event-Contract-Version": "phase4-runtime-event/v1"
          }
        })
      });
      await terminalTransport.subscribe(
        "RUN-A",
        (event) => terminalEvents.push(event),
        (error) => terminalErrors.push(error),
        subscriptionOptions((state) => terminalStates.push(state))
      ).closed;
      assert.deepEqual(terminalStates.map((state) => state.kind), [
        "CONNECTING", "OPEN", "TERMINAL"
      ]);
      assert.equal(terminalStates.at(-1).outcome, "SUCCESS");
      assert.equal(terminalEvents.length, 1);
      assert.equal(terminalErrors.length, 0);

      const projectionStates = [];
      const projectionErrors = [];
      const projectionTransport = new sse.SSERuntimeTransport({
        fetchImplementation: async () => new Response(terminalFrame, {
          status: 200,
          headers: {
            "content-type": "text/event-stream",
            "X-Phase4-Contract-Version": "phase4-core/v1",
            "X-Phase4-Event-Contract-Version": "phase4-runtime-event/v1"
          }
        })
      });
      await projectionTransport.subscribe(
        "RUN-A",
        () => { throw new Error("RAW_REDUCER_SECRET_SENTINEL"); },
        (error) => projectionErrors.push(error),
        subscriptionOptions((state) => projectionStates.push(state))
      ).closed;
      assert.deepEqual(projectionStates.map((state) => state.kind), [
        "CONNECTING", "OPEN", "RECOVERING"
      ]);
      assert.equal(projectionStates.at(-1).reason, "PROJECTION_MISMATCH");
      assert.equal(projectionStates.at(-1).lastSequence, 0);
      assert.equal(projectionErrors[0].reason, "PROJECTION_REJECTED");
      assert.equal(
        JSON.stringify(projectionStates).includes("RAW_REDUCER_SECRET_SENTINEL"),
        false
      );
    """
    script = script.replace("__RUNTIME_SOURCE_URL__", json.dumps(runtime_source_url))
    script = script.replace("__SSE_SOURCE_URL__", json.dumps(sse_source_url))
    completed = subprocess.run(
        [
            "node",
            "--no-warnings",
            "--experimental-strip-types",
            "--input-type=module",
            "-e",
            script,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
