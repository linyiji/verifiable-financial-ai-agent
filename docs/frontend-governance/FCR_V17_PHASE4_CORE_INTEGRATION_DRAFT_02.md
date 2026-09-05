# Frontend Change Request — V17 Phase 4 Core Integration — DRAFT-02

```yaml
change_id: FRONTEND_V17_PHASE4_CORE_INTEGRATION
record_revision: DRAFT-02
status: DRAFT_CHANGE
title: Frontend V17 Phase 4 Core authoritative backend integration

previous_baseline_id: FRONTEND_BASELINE_V8.1
previous_baseline_sha: d854c97789c98cca14fee3f4b3d7f00e0d5d137a

r1_contract_input_sha256: 36cf733d07b4df1ad4cb1065bdd17eceb6bbc98cf6f77fe0dfb1963185757e08
r1_status: SUPERSEDED_BEFORE_OWNER_APPROVAL
r1_owner_approval: NO

r2_contract_input_revision: 2.0.0
r2_contract_input_sha256: fc184034e448e85190aa4cfd92b89e90b9f258307632920daa8d8cd73c600c19
r2_contract_input_status: READY_FOR_OWNER_APPROVAL
r2_owner_approval: PENDING

phase4_backend_contract_family: phase4-core/v1
phase4_runtime_event_contract: phase4-runtime-event/v1
phase4_backend_final_contract_set_sha256: 0bf6c824d553847fa129a429715aedc36a30601a97421f4447cdd3f6d6a81741
corrected_v17_reference_manifest_sha256: 44be67d6854a284055c19919bcaf979097c710b33d3e5f57c5f7a35fe376f394

candidate_sha: PENDING
candidate_tree_fingerprint: PENDING
candidate_build_sha256: PENDING
implementation_authorized: false
phase4_started: false
audit_result: NOT_RUN
current_gate: CONTRACT_INPUT_OWNER_APPROVAL_PENDING
```

## Revision purpose

DRAFT-02 supersedes DRAFT-01 only as the pending change-record revision for the final R2 consumer
contract input. DRAFT-01 remains immutable historical preparation evidence. DRAFT-02 incorporates
the focused Backend Final Contract Delta and Final Parity corrections; it does not approve or
implement Frontend V17, create a Candidate, claim a build, claim an integration PASS, or start
Phase 4.

The governance cycle is:

```text
owner approval of exact R2 contract input
→ Backend Final Contract Freeze consumes approved R2
→ later Frontend V17 implementation consumes the frozen Backend contract
```

A Frontend implementation Candidate SHA is not a prerequisite for Backend Final Contract Freeze.

## Bound authority

| Authority | Bound identity |
|---|---|
| Approved parent | `FRONTEND_BASELINE_V8.1` at `d854c97789c98cca14fee3f4b3d7f00e0d5d137a` |
| R2 canonical consumer package | `fc184034e448e85190aa4cfd92b89e90b9f258307632920daa8d8cd73c600c19` |
| Phase 4 Backend final contract set | `0bf6c824d553847fa129a429715aedc36a30601a97421f4447cdd3f6d6a81741` |
| Corrected V17 reference manifest | `44be67d6854a284055c19919bcaf979097c710b33d3e5f57c5f7a35fe376f394` |
| Access profile | `phase4-local-single-user-trusted/v1` |
| Artifact policy | `phase4-html-required-pdf-optional/v1` |
| Release policy | `phase4-release-eligibility/v1` |

The exact source-artifact and embedded canonical-payload digests are recorded in
`V17_PHASE4_CONTRACT_INPUT_PACKAGE_R2.json` and its manifest. R1 loses any conflict against the
Final Delta, Final Parity, final UAC/BD dispositions, Access Mode Decision, or governed acceptance
interaction design.

## Bound normalized contract families

The R2 package binds all 13 consumer families:

1. `GlobalRunCollectionProjection`
2. `PreparedResearchDraft`
3. `ConfirmRunResponseV1` (replaces flat R1 `ConfirmAndStartResult`)
4. `RunProjection`
5. `NormalizedRuntimeEventV1`
6. `ConnectionState`
7. `FinancialReviewProjection`
8. `ClaimTraceProjection / TraceBundle`
9. `ReportArtifactGroup`
10. `ReleasedFinancialMetric`
11. `ReleasedObjectCoreProjection`
12. `ErrorEnvelope`
13. `Availability`

The normative package freezes each family's consumer schema, field names, types, nullability,
enum mappings, unknown behavior, identity keys, Availability semantics, Backend dependency IDs,
and adapter ownership. The R1→R2 delta report classifies every change and records zero undocumented
breaking changes.

## Focused R2 corrections

- Prepare is `SCHEME_ONLY`; `mode` and `goalTemplateId` are not Backend business fields;
  `plannedGraphAvailability` and `draftHash` are required.
- Confirm returns `ConfirmRunResponseV1 {admission,responseMeta}`. Admission is immutable;
  response replay metadata cannot mutate it.
- Run actual graph/version are nullable before graph creation; lifecycle and all business-resource
  Availability values are Backend-authored.
- Runtime events bind exactly 55 raw names, 47 supported V1 contracts and eight explicit unsupported
  names. Unknown/unsupported input causes zero business mutation, zero cursor advance and snapshot
  recovery.
- Review verdict is exactly `PASS|REVIEW|BLOCK|null`; `PASS_WITH_UNCERTAINTY` is absent and
  `RESOLVED` belongs only to exception history.
- Trace uses a hash-bound anchor manifest, fixed HTML/PDF representations and plural Review/Task/
  Execution anchors with ordered event refs.
- Artifact policy requires HTML and makes PDF optional; each format has independent append-only
  attempts, identity, availability and failure state.
- Financial values remain Backend Decimal strings. The projection carries method, technical-price,
  corporate-action and proof-policy metadata; revenue growth preserves the signed prior denominator
  and every material formula uses its explicit `ROUND_HALF_EVEN` context.
- Released Object Core selects only an eligible RELEASED Run and never falls back to an arbitrary
  latest Run. Phase 5 fields remain absent.
- ErrorEnvelope uses the final 17-code vocabulary and safe code-bound recovery behavior.

## BD and UAC binding

`BD-001..012` are all `CONTRACT_CLOSED`; all twelve implementation-evidence states remain
`PENDING`. Contract closure does not assert route existence, implementation completion, audit PASS,
or Phase 4 acceptance.

`UAC-003..018` are `CONTRACT_CLOSED`. `UAC-001` remains open until every Backend and Financial
Semantics finding is remediated and independent PASS receipts are bound to the approved Phase 3
identity. `UAC-002` remains open until the owner approves this exact R2 hash. No R1 approval is
carried forward.

## Interaction and Scene binding

The current authoritative E2E namespace remains `P4-E2E-001..106`; `015` remains the tombstone.
Interactions `071..076` reserve `P4-E2E-107..112`. They are not activated by this draft. If later
approved unchanged, 107/108 are `PHASE4_CORE_REQUIRED`, while 109..112 are Presenter-only
`DEMO_UX_ONLY` and never enter the real Phase 4 aggregate.

Real Scenes 01–04 are Phase 4 Core affected scope. Real Scenes 05–06 remain excluded and
`PHASE5_ACTIVATED`; their Phase 4 coverage is compatibility/Demo-only and separately reported.

## Approval boundary

```text
CONTRACT_INPUT_APPROVAL_READY=YES
OWNER_APPROVAL_REQUIRED=YES
OWNER_APPROVAL_STATUS=PENDING
SELF_APPROVED=NO
IMPLEMENTATION_AUTHORIZED=NO
FRONTEND_CANDIDATE_CREATED=NO
PHASE4_STARTED=NO
```

Owner approval, if granted later, must cite the exact R2 canonical package SHA. Advancing this
record to `CHANGE_APPROVED`, creating a Candidate, modifying production source, or accepting Phase 4
requires later governed actions and evidence.
