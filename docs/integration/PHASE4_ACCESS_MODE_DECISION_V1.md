# Phase 4A Access Mode Decision V1

Status: `OWNER_DECISION_RECORDED — READY_FOR_FINAL_FREEZE`  
Decision ID: `P4-ACCESS-DECISION-001`  
Decision version: `1.0.0`  
Owner decision timestamp: `2026-09-04T07:57:17Z`  
Phase scope: `PHASE4A_CORE_INTEGRATION_ONLY`

This document records the project owner's product/security decision for UAC-006. It freezes the
Phase 4A access semantics needed for implementation; it does not implement authentication, approve
public deployment, close acceptance, or authorize Phase 4 production work.

## 1. Decision record

| Field | Frozen value |
|---|---|
| `decision_id` | `P4-ACCESS-DECISION-001` |
| `decision_version` | `1.0.0` |
| `phase_scope` | `PHASE4A_CORE_INTEGRATION_ONLY` |
| `access_mode_id` | `phase4-local-single-user-trusted/v1` |
| `access_mode_name` | `LOCAL_SINGLE_USER_TRUSTED_V1` |
| `authentication_required` | `NO` |
| `authentication_provider` | `NONE` |
| `tenant_model` | `NONE` |
| `workspace_ownership_model` | `NONE` |
| `user_ownership_model` | `NONE` |
| `effective_access_scope` | `LOCAL_SINGLE_USER` |
| `effective_access_scope_key` | literal `LOCAL_SINGLE_USER` |
| `client_asserted_authority_fields` | `PROHIBITED` |
| `resource_identity_validation` | `MANDATORY` |
| `cross_object_policy` | `PROHIBITED` |
| `cross_run_policy` | `PROHIBITED` |
| `artifact_ref_semantics` | `NON_BEARER_RESOURCE_LOCATOR` |
| `cache_scope` | literal `LOCAL_SINGLE_USER` plus exact Object/Run/resource identity |
| `idempotency_scope` | literal `LOCAL_SINGLE_USER`, method, normalized route, key digest and request hash |
| `error_behavior` | Phase 4A table in §4; normal 401/403 absent and reserved |
| `future_public_auth_status` | `DEFERRED_TO_SEPARATE_GOVERNED_CHANGE` |
| `security_limitations` | trusted/local integration only; exclusions in §6 |
| `owner_decision_timestamp` | `2026-09-04T07:57:17Z` |
| `affected_uac_ids` | direct `UAC-006`; dependent `UAC-005`, `UAC-015`, `UAC-018` |
| `affected_bd_ids` | `BD-001`, `BD-003..009`, `BD-011` |
| `affected_acceptance_families` | `P4-BE-001..030`, Core `P4-ID`, Core `P4-E2E`, `P4-SSE-001..020` |
| `project_owner_decision_applied` | `phase4-local-single-user-trusted/v1` |

`effective_access_scope=LOCAL_SINGLE_USER` is server-internal partition context, not a business
entity. Phase 4A adds no tenant, workspace, user, principal or ACL table solely for this profile.

## 2. Request and resource-identity contract

Phase 4A request JSON never accepts `user_id`, `actor_id`, `tenant_id`, `workspace_id`, or
`principal_id` as access authority. An identically named business/audit fact, if one exists, is not
reinterpreted as authorization identity.

No account/principal authentication layer is active, but exact identity closure is mandatory:

```text
requested Object O
  -> requested Run R where R.research_object_id == O.object_id
     -> each requested/nested T/E/K/C/V/P/X/L/A belongs to exact R
     -> each Object-bearing child belongs to exact O
     -> all indirect references close through the same R/O chain
```

This applies to Run, Task, Evidence, Calculation, Claim, Review/Check, Proof/Verification,
CanonicalExecutionRecord, ReleasedResearchResult and ReportArtifact. A nested ID that exists under
another Object or Run fails closed as 404 `IDENTITY_MISMATCH`. The server never repairs a failed
join with latest, first, ticker, company, title, metric name or Claim text.

## 3. Cache and idempotency scope

Every durable idempotency identity includes:

```text
effective_access_scope_key = "LOCAL_SINGLE_USER"
method
normalized route
idempotency key digest
canonical request hash
```

The scope key is server-supplied and is never accepted from the client. Semantic-resource cache
keys include the same scope key plus exact Object, Run and nested-resource identity. No user or
tenant ID is manufactured to fill either tuple.

## 4. Phase 4A error behavior

Normal requests under this profile do not generate account-authentication 401 `UNAUTHENTICATED`
or authorization 403 `FORBIDDEN`. Both codes remain reserved in `ErrorEnvelopeV1` for a future
governed access profile.

| Condition | Phase 4A result |
|---|---|
| requested resource missing | HTTP 404 `NOT_FOUND` |
| nested resource exists outside requested O/R | HTTP 404 `IDENTITY_MISMATCH` with no foreign-owner disclosure |
| retained resource cannot be supplied | HTTP 409 `UNAVAILABLE` |
| no generation attempt/record exists | HTTP 409 `NOT_GENERATED` |
| release boundary is unmet | HTTP 409 `NOT_RELEASED` |
| numeric cursor exceeds exact Run tail | HTTP 409 `CURSOR_AHEAD` |
| contract negotiation is incompatible | HTTP 409 `SCHEMA_INCOMPATIBLE` |
| persisted identity/hash/cardinality closure is corrupt | HTTP 500 `INTEGRITY_FAILURE` |
| retryable temporary backend problem | HTTP 503 `TRANSIENT_BACKEND_ERROR` |

Every response uses the frozen `ErrorEnvelopeV1` fields and safe disclosure rules. A response may
repeat a caller-supplied nested ID as resource context but never reveals which foreign Object/Run
owns it.

## 5. Artifact access

`authorized_ref` remains the relative same-origin locator
`/api/research-runs/{run_id}/artifacts/{artifact_id}/content`. It is not a credential or bearer
token. Each GET revalidates the exact Run, its Object, the Run-scoped artifact, its Canonical and
Released Result bindings, representation `AVAILABLE` state, content type, byte size and SHA-256
before committing success bytes.

No public response, redirect, log or error exposes a filesystem path, `artifact://` locator,
storage secret or signed storage credential. Cross-Run/Object substitution is 404
`IDENTITY_MISMATCH`; corruption is 500 `INTEGRITY_FAILURE`; both return zero protected artifact
bytes.

## 6. Security limitations

`LOCAL_SINGLE_USER_TRUSTED_V1` is appropriate only for the governed Phase 4A trusted/local
integration profile. It is not approval for:

- public unauthenticated deployment;
- multi-user or multi-tenant deployment;
- a shared untrusted network;
- production Internet exposure.

Any such use requires a separate governed access-control profile with explicit authentication,
ownership, denial-disclosure, cache and migration semantics. `PHASE4B_AUTHENTICATION` remains
`DEFERRED_TO_SEPARATE_GOVERNED_CHANGE`.

## 7. Affected contract and acceptance surfaces

| Namespace | Affected IDs/contracts |
|---|---|
| UAC | direct `UAC-006`; dependent `UAC-005`, `UAC-015`, `UAC-018` |
| V17 BD | `BD-001`, `BD-003..009`, `BD-011` |
| V17 normalized contracts | every Phase 4A public contract; direct Confirm, RunProjection, TraceBundle, ReportArtifactGroup and ErrorEnvelope behavior |
| P4-BE | `P4-BE-001..030` access-profile context; identity emphasis `004`, `025..027`, `030` |
| P4-ID | Core `P4-ID-001..020`, `023..028` |
| P4-E2E | Core `001..014`, `016..061` Core variants, `063..096`, `098`, `101..102`, `105..106` |
| P4-SSE | `P4-SSE-001..020` access-profile context; cursor isolation emphasis `003`, `018` |
| Scenes | `SCENE-01..04`; `SCENE-05..06` remain inactive |

## 8. Decision effect and evidence boundary

```text
UAC_006=RESOLVED_PROVISIONALLY
contract_semantics_state=READY_FOR_FINAL_FREEZE
implementation_evidence_state=PENDING
PROJECT_OWNER_DECISION_APPLIED=phase4-local-single-user-trusted/v1
```

The decision makes V17 credential handling semantically `NONE` for this local profile. V17 must
not invent principal/user/tenant fields and must continue to fail closed on identity mismatch,
schema incompatibility, unavailable data, integrity failure and cross-object/Run references. This
does not authorize V17 implementation.

Acceptance evidence remains pending for exact identity closure, cache/idempotency partitioning,
artifact byte validation and all mapped negative cases. The decision is therefore semantically
ready for final freeze but not `FINAL_CLOSED`, `ACCEPTANCE_PROVEN`, or an implementation PASS.

```text
PHASE4_ACCESS_MODE_DECISION_READY=YES
ACCESS_MODE_ID=phase4-local-single-user-trusted/v1
UAC_006=RESOLVED_PROVISIONALLY
UAC_PROVISIONAL_DECISIONS_COMPLETE=18/18
UAC_SEMANTIC_DECISION_REQUIRED=0
UAC_FINAL_CLOSED=0
CONTRACT_SEMANTICS_PENDING=0
IMPLEMENTATION_EVIDENCE_PENDING=16
CURRENT_STATE_WAITING_FOR_IMPLEMENTATION_EVIDENCE=5
WAITING_FOR_APPROVED_PHASE3_PARENT=YES
WAITING_FOR_V17_CONTRACT_INPUT=YES
PHASE4_BACKEND_CONTRACT_FREEZE_READY=NO
PHASE4_PRODUCTION_IMPLEMENTATION_AUTHORIZED=NO
CONTRACT_FREEZE_IMPLEMENTATION_EVIDENCE_DEADLOCK=RESOLVED
```
