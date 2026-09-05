# Frontend V17 Phase 4 Contract Input — R1 to R2 Delta

Status: `COMPLETE — READY_FOR_OWNER_APPROVAL`  
R1 canonical package: `36cf733d07b4df1ad4cb1065bdd17eceb6bbc98cf6f77fe0dfb1963185757e08`  
R1 disposition: `SUPERSEDED_BEFORE_OWNER_APPROVAL`  
R2 revision: `2.0.0`

## Classification rule

This report is the exhaustive semantic delta from R1 to R2. The machine-readable package's
per-contract `field_classification` is normative. Each named field or field group has one primary
classification: `UNCHANGED`, `ADDED`, `REMOVED`, `RENAMED`, `MOVED`, `ENUM_TIGHTENED`,
`NULLABILITY_CHANGED`, `OWNERSHIP_CHANGED`, or `SEMANTICALLY_REPLACED`. A composite classified
`UNCHANGED` includes its descendants except descendants explicitly listed in another category.
An enum member addition/removal is classified once under `ENUM_TIGHTENED` or `ADDED`, as stated.
There is no undocumented breaking change.

Authority abbreviations below are: Final Delta = `PHASE4_BACKEND_FINAL_CONTRACT_DELTA.md`; Final
Parity = `PHASE4_BACKEND_FRONTEND_FINAL_PARITY_MATRIX.md`; Final UAC/BD = the corresponding final
disposition artifacts. Their exact hashes are bound in the R2 package and manifest.

## Exhaustive semantic delta

| Contract | R1 field / semantic | R2 field / semantic | Primary class | Reason | Authoritative source | Compatibility | Frontend impact |
|---|---|---|---|---|---|---|---|
| GlobalRunCollectionProjection | `progress` lacked frozen task counts | add `completedTasks`, `totalTasks` | `ADDED` | Final progress tuple is method/counts/fraction/percent | Final Parity §3; Final UAC-008 | additive | Decoder and adapter must retain Backend counts. |
| GlobalRunCollectionProjection | `graphVersion` required | `integer>=1\|null` before actual graph exists | `NULLABILITY_CHANGED` | A pre-actual-graph Run has no graph version | Final Parity §3 | breaking | UI must render pre-graph state without fabricating zero/current. |
| GlobalRunCollectionProjection | percent was not exclusively scoped | `percent=fraction*100`, adapter-owned nonbusiness value | `OWNERSHIP_CHANGED` | Backend owns fraction; adapter may derive only presentation percent | Final Parity §3; UAC-008 | breaking authority correction | Remove any page/business progress calculation. |
| GlobalRunCollectionProjection | all other named fields | unchanged | `UNCHANGED` | No further parity delta | Final Parity §3 | compatible | Mechanical rename/readonly behavior only. |
| PreparedResearchDraft | `mode`, `goalTemplateId` treated as consumer business fields | removed from normalized DTO | `REMOVED` | Core accepts implicit FULL and expanded Goal text; templates are authoring UI only | Final Delta; Final Parity §4 | breaking | Keep labels/form state outside Backend business authority. |
| PreparedResearchDraft | no explicit pre-confirm graph state/hash | add `plannedGraphAvailability`, `draftHash` | `ADDED` | Prepare is immutable hashed `SCHEME_ONLY` and contains no Tasks/graph | Final Parity §4; BD-007 | additive-required | Decode exact availability/hash; do not fabricate plan Tasks. |
| PreparedResearchDraft | all other named fields | unchanged | `UNCHANGED` | No further parity delta | Final Parity §4 | compatible | Existing exact identity and expiry handling remain. |
| ConfirmRunResponseV1 | flat `ConfirmAndStartResult` | outer `ConfirmRunResponseV1 {admission,responseMeta}` | `SEMANTICALLY_REPLACED` | Separate immutable business admission from per-response transport metadata | Final Parity §5; UAC-005 | breaking | Replace flat decoder and state storage. |
| ConfirmRunResponseV1 | flat business fields | move under `admission.*` | `MOVED` | Admission is immutable and replay-stable | Final Parity §5 | breaking | Read canonical outcome only from `admission`. |
| ConfirmRunResponseV1 | flat `idempotencyReplayed` | move to `responseMeta.idempotencyReplayed` | `MOVED` | Replay is transport metadata | Final Parity §5 | breaking | Never merge replay metadata into admission. |
| ConfirmRunResponseV1 | scalar `autoStart` | `admission.autoStart.{required,admitted}` | `SEMANTICALLY_REPLACED` | Scheduler admission must state both required and admitted | Final Delta; UAC-007 | breaking | No second Start call; successful V1 values are both true. |
| ConfirmRunResponseV1 | no immutable admission identity/draft closure | add admission schema/admission ID/draft ID/version/hash/admitted time and response schema/request ID | `ADDED` | Durable exactly-once admission and response-loss recovery | Final Parity §5; BD-008 | additive-required | Persist/use exact identities; retry exact key/body only. |
| RunProjection | `actualGraph`, `graphVersion` required | nullable only before actual graph creation | `NULLABILITY_CHANGED` | Pre-creation projection is valid | Final Parity §6 | breaking | Render explicit pre-graph state. |
| RunProjection | path-change graph before/after too strict | nullable by source lifecycle | `NULLABILITY_CHANGED` | Correction may have no durable graph mutation | Final Parity §6; BD-012 | breaking | Never invent graph versions. |
| RunProjection | incomplete progress/path projection | add task counts and path-change `decision` | `ADDED` | Final atomic projection is lossless | Final Parity §6 | additive-required | Decode Backend values. |
| RunProjection | broad path-change vocabulary | `changeKind` exactly `SELF_CORRECTION\|ADD_TASK\|CHANGE_DEPENDENCY` | `ENUM_TIGHTENED` | Only three frozen mutation types | Final Parity §6; BD-012 | breaking | Unknown kind fails closed and refreshes. |
| RunProjection | page/event reconstruction could be read as authority | exact one-source Backend `PathChangeProjectionV1`; lifecycle owns status/stage/progress/terminal/outcome/failure | `SEMANTICALLY_REPLACED` | Atomic projection is canonical | Final Parity §6; UAC-008/009 | breaking authority correction | One reducer/store; no page-local canonical Run state. |
| RunProjection | all other named fields | unchanged | `UNCHANGED` | No further parity delta | Final Parity §6 | compatible | Preserve exact identity/watermark checks. |
| NormalizedRuntimeEventV1 | generic `schemaVersion` | `eventContractVersion=phase4-runtime-event/v1` | `RENAMED` | Public event protocol uses a dedicated version field | Final Parity §7; VersionProtocolV1 | breaking | Decoder checks exact event contract token. |
| NormalizedRuntimeEventV1 | no payload version/required graph member | add `payloadSchemaVersion=1`; always-present nullable `graphVersion` | `ADDED` | Payload and graph semantics are explicitly versioned | Final Parity §7 | additive-required | Validate before reduction. |
| NormalizedRuntimeEventV1 | provisional event domain | exact 55 raw names; 47 supported; 8 explicit unsupported | `ENUM_TIGHTENED` | Every raw Backend value has one disposition | Final Parity §7; enum-map payload | breaking | Unsupported/unknown means zero mutation/cursor advance and snapshot recovery. |
| NormalizedRuntimeEventV1 | effect ownership ambiguous | Backend-supplied or mechanical frozen-table `effect`/refresh flag | `OWNERSHIP_CHANGED` | Effects are contract plumbing, not page inference | Final Parity §7 | breaking authority correction | Do not create frontend business event names. |
| NormalizedRuntimeEventV1 | all other named fields | unchanged | `UNCHANGED` | No further parity delta | Final Parity §7 | compatible | Exact duplicate remains no-op; gaps recover. |
| ConnectionState | seven fetch-stream variants and cursor semantics | unchanged | `UNCHANGED` | Final parity retained the frozen architecture | Final Parity §8; CursorProtocolV1 | compatible | Never map transport state to Run lifecycle. |
| FinancialReviewProjection | `PASS_WITH_UNCERTAINTY` available | verdict exactly `PASS\|REVIEW\|BLOCK\|null`; remove old member | `ENUM_TIGHTENED` | Backend final vocabulary has three verdicts; `RESOLVED` is exception history | Final Parity §9; UAC-013 | breaking | Unknown/old verdict fails closed; never infer PASS. |
| FinancialReviewProjection | Review presence fields stricter/implicit | `reviewId`, `verdict`, `reviewer` nullable when Review absent; Availability explicit | `NULLABILITY_CHANGED` | Review is release-independent and may not exist | Final Parity §9 | breaking | Render absence from Availability. |
| FinancialReviewProjection | thin Review refs | add `inputSnapshotHash`, `reviewedJudgmentRefs`, stable Check schema, subjects, expected/actual/detail, exception/correction history and timestamps | `ADDED` | A/B/C and remediation history need durable exact joins | Final Parity §9; BD-011 | additive-required | Decode/display supplied checks; no log reconstruction. |
| FinancialReviewProjection | Backend `status` consumer label | frontend `verdict` | `RENAMED` | Frozen adapter rename avoids collision with resource state | Final Parity §9 | mechanical | Rename only. |
| FinancialReviewProjection | uncertainty/history could be encoded in verdict | explicit Backend check/exception/correction facts | `SEMANTICALLY_REPLACED` | Verdict and history are orthogonal | Final UAC-013 | breaking | Do not synthesize exception closure. |
| FinancialReviewProjection | all other named fields | unchanged | `UNCHANGED` | No further parity delta | Final Parity §9 | compatible | Preserve same-Run ordered refs. |
| ClaimTraceProjection / TraceBundle | single report artifact/anchor and singular Review/Task/Execution anchors | fixed HTML/PDF representation entries plus plural `reviewAnchors[]`, `taskAnchors[]`, `executionAnchors[]` | `SEMANTICALLY_REPLACED` | Anchors are representation-scoped and relations can be plural | Final Parity §10; UAC-014 | breaking | Replace singular navigation model; preserve ordered event refs. |
| ClaimTraceProjection / TraceBundle | old singular/artifact fields | remove `report.artifactIds`, `report.anchor`, and singular anchors | `REMOVED` | Superseded by exact representation-scoped structures | Final Parity §10 | breaking | No DOM/text/first/latest fallback. |
| ClaimTraceProjection / TraceBundle | missing manifest and exact metric/calculation join fields | add `anchorManifestId`, `anchorManifestSha256`, `metricId`, `calculationId`, representation and plural-anchor fields | `ADDED` | Hash-bound same-Run trace closure | Final Parity §10; BD-006 | additive-required | Verify exact identities/availability; no cross-format borrowing. |
| ClaimTraceProjection / TraceBundle | representation identity assumed present | artifact/anchor IDs nullable only for that unavailable representation | `NULLABILITY_CHANGED` | HTML and PDF availability are independent | Final Parity §10 | breaking | Unavailable slot cannot borrow another slot. |
| ClaimTraceProjection / TraceBundle | open format set | exactly `HTML\|PDF` | `ENUM_TIGHTENED` | Artifact policy fixes the two slots | Final Parity §10 | breaking | Unknown format withholds trace. |
| ClaimTraceProjection / TraceBundle | inferred primary Task permitted by cardinality | only explicit durable Backend primary relation may populate `primaryTaskId` | `OWNERSHIP_CHANGED` | Singleton is not primacy | Final UAC-012/014 | breaking authority correction | Never select first/only Task as primary. |
| ClaimTraceProjection / TraceBundle | all other named fields | unchanged | `UNCHANGED` | No further parity delta | Final Parity §10 | compatible | Preserve source order and exact refs. |
| ReportArtifactGroup | policy/manifest/attempt detail absent | add release/artifact policy versions, manifest ID/hash, required flag and generation attempt ID/count | `ADDED` | Slots and retries require durable independent identity | Final Parity §11; UAC-016 | additive-required | Decode fixed slot metadata. |
| ReportArtifactGroup | both formats could appear equally required | exact `[HTML,PDF]`; HTML required, PDF optional, fixed content types | `ENUM_TIGHTENED` | Frozen `phase4-html-required-pdf-optional/v1` | Final Parity §11; artifact-policy payload | breaking | Release may succeed with policy-skipped PDF. |
| ReportArtifactGroup | loose field presence | exact state table controls IDs/failure/attempt/hash/size/renderer/time/ref | `NULLABILITY_CHANGED` | Availability and retained-success states are explicit | Final Parity §11 | breaking | Do not infer from missing values. |
| ReportArtifactGroup | artifact reference could be treated as credential | `authorizedRef` is Backend-projected non-bearer same-origin locator | `OWNERSHIP_CHANGED` | Each byte GET reauthorizes/revalidates integrity | Final UAC-015 | breaking authority correction | Never expose internal/filesystem/artifact locators. |
| ReportArtifactGroup | skipped PDF failure semantics unclear | `NOT_GENERATED/PDF_NOT_GENERATED_BY_POLICY/false`, `safeFailureCode=null` | `SEMANTICALLY_REPLACED` | Policy skip is not render failure | artifact-policy payload | breaking | Show optional unavailable state, not error/retry. |
| ReportArtifactGroup | all other named fields | unchanged | `UNCHANGED` | No further parity delta | Final Parity §11 | compatible | Preserve exact Object/Run/report closure. |
| ReleasedFinancialMetric | proof lacked explicit policy; method/technical/corporate remediation fields absent | add `proof.policyId`, `methodMetadata`, `technicalPriceBasis`, `corporateActionStatus`, `corporateActionGuardRefs` | `ADDED` | Lossless final financial projection and Phase 3 remediation carriage | Final Parity §12; financial-projection payload | additive-required | Carry strings/metadata exactly; no consumer-schema redesign needed. |
| ReleasedFinancialMetric | provisional Proof mapping | total Backend Proof semantics; `VALID` is generated-unverified, never verified | `ENUM_TIGHTENED` | Proof and release authority remain Backend-owned | Final UAC-017 | breaking | Fail closed on unknown proof state. |
| ReleasedFinancialMetric | proof object without current policy semantics | policy-bound Proof object | `SEMANTICALLY_REPLACED` | Release closure binds exact proof policy | release-policy payload | breaking | No proof inference. |
| ReleasedFinancialMetric | possible frontend method/display arithmetic | all display/method/technical/corporate fields Backend-owned | `OWNERSHIP_CHANGED` | Frontend financial authority must be zero | Final Parity §12; BD-005 | breaking authority correction | No numeric conversion, rounding, unit or method reconstruction. |
| ReleasedFinancialMetric | formula context not fully bound | signed-prior revenue growth; explicit local `ROUND_HALF_EVEN` contexts (28 fundamental and MACD subtraction; 50 technical averaging/EMA) | `SEMANTICALLY_REPLACED` | Incorporates final financial remediation methodology | financial-projection payload | breaking semantics | Display Backend strings only. |
| ReleasedFinancialMetric | all other named fields | unchanged | `UNCHANGED` | No further parity delta | Final Parity §12 | compatible | Decimal wire values remain strings. |
| ReleasedObjectCoreProjection | missing release-projection/history metadata | add `projectionRevision`, `generatedAt`, and history `runs`/`runCount` on the bound surface | `ADDED` | Final released-state projection requires stable metadata | Final Parity §13 | additive-required | Decode Backend history only. |
| ReleasedObjectCoreProjection | release tuple could be partially populated | latest/source/result/canonical/releasedAt/report tuple is all-null or complete by Availability | `NULLABILITY_CHANGED` | Partial release closure is integrity failure | Final Parity §13 | breaking | Withhold invalid partial slices. |
| ReleasedObjectCoreProjection | arbitrary latest Run fallback possible | only eligible RELEASED Run; deterministic `(releasedAt DESC, runId DESC bytewise)` | `SEMANTICALLY_REPLACED` | Release policy selects the eligible set only | Final UAC-017; release-policy payload | breaking | Never substitute newest nonreleased Run. |
| ReleasedObjectCoreProjection | all other named fields | unchanged | `UNCHANGED` | No further parity delta | Final Parity §13 | compatible | Phase 5 fields stay absent. |
| ErrorEnvelope | 14-code provisional set | exact 17-code list; add `UNAUTHENTICATED`, `REQUEST_VALIDATION_ERROR`, `INTERNAL_ERROR` | `ADDED` | Final UAC-018 vocabulary | Final Parity §2 | additive-required | Handle only frozen code table. |
| ErrorEnvelope | error/recovery vocabulary not final | exact 17 codes and code-bound recovery tuples | `ENUM_TIGHTENED` | Recovery is Backend policy | Final Parity §2; UAC-018 | breaking | Unknown fails closed; pages do not reinterpret. |
| ErrorEnvelope | recovery for cursor/not-released/unsupported/integrity cases differed | exact frozen `SNAPSHOT_RELOAD` behavior | `SEMANTICALLY_REPLACED` | Align all consumers with Cursor/Error protocols | Final Parity §2 | breaking | Execute named recovery only. |
| ErrorEnvelope | all other named fields | unchanged | `UNCHANGED` | No further parity delta | Final Parity §2 | compatible | Safe allowlisted details only; no raw body. |
| Availability | `status`, `reasonCode`, `retryable` and six states | unchanged | `UNCHANGED` | Final parity retained the R1 Availability contract | Final Parity §1 | compatible | Backend authors all business-resource availability. |

## Closure

```text
R1_STATUS=SUPERSEDED_BEFORE_OWNER_APPROVAL
R1_OWNER_APPROVAL=NO
CONTRACTS_CLASSIFIED=13/13
UNMAPPED_FIELD_GROUPS=0
UNDOCUMENTED_BREAKING_CHANGES=0
FRONTEND_CONTRACT_CONFLICTS=0
```
