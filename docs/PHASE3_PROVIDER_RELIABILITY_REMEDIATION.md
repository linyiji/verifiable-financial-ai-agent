# Phase 3 workload-aware provider reliability remediation

## Preserved evidence

- Candidate `66edc5110b6ab7d81578cef80190497a2f11e5b2` / tree
  `5cc1fd63d97fcb07c233b1dba73bd4d1cd16b77f` is preserved as
  `PRE_AUTHORITATIVE_PROVIDER_STABILITY_FAILED`.
- `RUN-3bf17fec-efae-4945-8084-432e69a45bc5` remains a
  `NON_AUTHORITATIVE_PROVIDER_INTERRUPTED_ATTEMPT`. It is never resumed and its partial
  evidence is not reused.

## Root cause

The MiMo Generated Capability qualification request did not encounter a conventional read
timeout. HTTPX read timeout is an inactivity timeout. The upstream response continued to
deliver bytes, so each byte reset the inactivity window and the response body read remained
live for more than 960 seconds. There was no independent outer wall-clock deadline around
the body read and provider retry path. The qualification watchdog ultimately terminated the
probe.

The owned client uses HTTPX directly and HTTPX performs no automatic retries in this
configuration. The unbounded duration was therefore not an SDK retry leak; it was a missing
wall-clock constraint around a continuously active read.

## Owned execution budget

`ProviderExecutionPolicyV1` now controls every real structured provider call with explicit
connect, read, write, and pool limits plus a maximum attempt count, bounded backoff,
per-attempt wall-clock deadline, and overall wall-clock deadline. The outer deadline wraps
the complete attempt/backoff chain. Cancellation propagates into the active HTTPX request,
and an owned client context is closed during cancellation. No detached background task is
created.

Default production values are:

- connect: 10 seconds
- read inactivity: 60 seconds when the existing acceptance client requests 60 seconds
- write: 30 seconds
- pool: 10 seconds
- attempts: at most 2 governed model-route attempts
- backoff: at most 1 second
- per attempt: 90 seconds
- overall provider call: 180 seconds

Generated Capability application retries share that same absolute 180-second generation
deadline. Expiration cancels the active builder call and prevents another builder request.

## Workload-aware binding

Policy `MIMO_PRIMARY_TEAMOROUTER_SECONDARY_V2` evaluates the following workloads
independently through their owned production interfaces:

- `SCHEME_PLANNER`
- `LEAD_PLANNER`
- `GENERATED_CAPABILITY`

MiMo is probed first for each workload. TeamoRouter is probed for that workload only when
MiMo fails. Two consecutive valid responses are required. `RunProviderBindingV1` contains
exactly one provider/model binding for every workload, is finalized before Research Run
creation, and is immutable. Each bound provider rejects use for another workload.

Automatic mid-Run failover remains disabled. A bound-provider failure fails the Run. The
internal `ControlledProviderFailoverRecordV1` only reserves safe provenance fields for a
future explicit attempt-boundary policy; it does not activate failover and adds no public
RuntimeEvent.

## Safe failure and telemetry boundary

Owned failures normalize authentication, quota/rate, retryable HTTP, provider unavailable,
connect timeout, read timeout, overall deadline, remote protocol, invalid response, and
semantic/schema failures. Safe metadata is limited to provider, model, workload, attempt,
elapsed duration, retryability, selection provenance, build identity, and result status.
Credentials, authorization headers, prompts, response bodies, generated source, generated
tests, and hidden reasoning are excluded.

This remediation changes no Phase 4 public API, frontend R2 contract, RuntimeEvent enum,
financial projection/review semantics, trace contract, artifact contract, or database
migration.
