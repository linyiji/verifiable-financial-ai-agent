# Recoverable execution and policy V1 — frozen interface

Status: PARTIAL offline implementation; NOT production certification. Owner authorization is
offline only. Historical runs and legacy recovery guards are unchanged.

## Scope and enablement

New execution requires `recoverable-execution/v1`, an explicit finite Intent budget,
an absolute deadline, complete frozen operation contracts, and an explicitly injected
V1 store/runner. No automatic conversion of legacy records. Missing fields are
`LEGACY_NOT_RESUMABLE`; no invented epoch, authorization, price or budget.
The production legacy composition stays selected until all integration gates pass.
Model proposals default OFF; ordinary task authorization is not DECIDER authority.

V1 supports crash redelivery with a new lease epoch, same-task new attempts,
validated saved-output reuse, authorized business-failure recovery, and authorized
missing-Memory reconciliation. It does not authorize arbitrary branch redo, pause,
context rewriting, automatic evidence gathering, recertification, or new research.

## Shared identities and interfaces (frozen)

`src/domain/execution_contract.py` defines `ExecutionContract`, `ExecutionBudget`,
`LeaseToken`, `CallPurpose`, `ContractDenied`, and canonical `fingerprint`.
An Intent exists before a Run; admission links the Run without resetting its ledger.
Operations bind Intent/Run/Task, Scheme/Object/as-of, graph, required outputs,
dependencies, input/evidence/calculation/parent digests, schema/formula/code/policy,
source identity, exact candidate grants and all absolute budget/deadline limits.
The V1 freeze primitive persists the complete contract atomically; reusing an operation ID
with any different digest is rejected, never interpreted using latest mutable config.

`SQLExecutionLedger(sessions)` stores new records separately from legacy aggregates.
Public async methods: `create_intent(intent_id,budget,deadline)`,
`admit_run(intent_id,run_id)`, `freeze(contract)`, `view(intent_id)`,
`claim(intent_id,operation_id,owner,now,lease_seconds) -> LeaseToken`,
`reserve(token,call_id,purpose,route,now,timeout,estimated_cost=None)`,
`dispatch(token,call_id,now)`, `save_result(token,call_id,payload,now)`,
`settle(token,call_id,now,actual_cost=None)`, `cancel(token,call_id,now)`,
`publish(token,kind,reference,payload,now)`, `checkpoint(token,payload,now)`,
`complete(token,now)`, `fail(token,failure,now)`,
`authorize_recovery(intent_id,operation_id,authorization_id,contract_hash)`,
`advance_release(token,stage,reference,object_id,now,memory_authorized=False)`.
Times are UTC epoch seconds, passed by caller for deterministic fake-clock tests.
Tokens contain Intent, Operation, owner and epoch. Every authoritative write checks
both epoch and unexpired lease in the same database transaction.

## Transactions, calls, recovery

One locked Intent row serializes all budget reservations across its operations;
per-operation Task usage is also shared across operations of the same Task.
Each physical request needs a unique reservation before dispatch (including inner
HTTP retries). CHECK is separate from TASK_EXECUTION but consumes total physical
budget, time and known cost. Numeric cost caps without reliable estimates fail closed.
State sequence: RESERVED → DISPATCHED → RESULT_SAVED → SETTLED. Only RESERVED can
be cancelled/refunded. Takeover turns DISPATCHED into RESULT_UNKNOWN, blocks resend,
and refunds unsent reservations. UNKNOWN is neither success nor zero cost.
There is no claim of external exactly-once delivery without provider idempotency.
Successful exact check consumption reuses one saved record; it never invokes twice.

Intent/Task/Operation budgets and absolute deadlines all constrain reservations.
Restart never renews deadlines. Current profile defaults and 4/3/300 exceptions,
generated outer180s and candidate-vs-substitution distinctions remain unchanged.
Policy descriptor version/override reasons are included in frozen contracts.

Each operation is also a durable delivery record (PENDING, CLAIMED, COMPLETE,
FAILED); claim is not ACK/delete. Expired CLAIMED operations are discoverable.
Business FAILED requires a separate one-shot contract-bound authorization; original
failure and attempt history are retained. Unknown calls block ordinary recovery.
Saved outputs are content-bound and reconciled before resending. Checkpoint v2
includes contract hash, lease, outputs/validation, ledger, checked candidates,
absolute deadlines and compatibility. Fenced publication covers task output,
aggregate, events, checkpoints, report/release/memory authoritative references.
Artifacts must be attempt-isolated and hash validated before publishing references.

## Release, validity and rollback

Release stages: PREPARED → RELEASED → MEMORY_MATERIALIZED → COMPLETED.
Only exact Object/Run/released-result binding can write Memory; absent authority
leaves RELEASED pending. Repeating a stage with identical binding is idempotent;
changing a binding or rolling back is forbidden. These stages do not invent Run enums.
Changed inputs, as-of, formula, schema, policy or graph invalidate affected output
and downstream closure including Review/Proof. No in-place replacement of history.

Rollback disables V1 admission, action endpoints and takeover; keep the additive
records for reading/reconciliation. Do not downgrade schema or delete reservations.
API/UI actions remain disabled until their actual integrated offline gates pass.
No model, provider, Proof or historical Run call is authorized by this contract.

## Implemented composition and remaining boundaries

`RecoverableDependencyRunner` uses the existing DependencyScheduler with persisted
contracts, child/coordinator fencing, saved-output reconciliation, attempt-specific
artifacts and checkpoint v2. Fake-provider tests cover same-Run process redelivery
and API-authorized failed-operation recovery. `memory_recovery_v1` calls the actual
ResearchMemoryRepository; its guard and Memory materialization share one PostgreSQL
transaction. Tests cover rollback, concurrent reconciliation and stale ownership.
The release-stage ledger alone is bookkeeping, not proof of a durable business release.

`LedgerHTTPTransport` is tested through actual FMP and TeamoRouter adapters with mock
HTTP responses, including inner retry and actual fallback-model accounting. Raw HTTP
receipts are not validated task results. PlanningContract represents pre-Run Scheme
and Graph identity without fabricating a Run or changing confirmed intent.

The API router and UI component are opt-in and **not mounted in the default product**.
The proposal mode is OFF, with separate DECIDER authority and bounded fallback.
These are explicitly incomplete production integration points:

- Legacy admission does not yet freeze every V1 Intent/Run contract.
- The existing dynamic-approval transaction is not wired to the new freeze primitive.
- All production planning, data and model transports are not yet universally ledger-wrapped.
- V1 fenced event/aggregate references are not yet bridged into every legacy projection table.
- Persisted deliveries can be reclaimed by the runner, but no production startup scanner is enabled.

Therefore durable primitives passing tests is not end-to-end production recoverability.
Do not enable actions or authorize a Live based on this receipt alone. See the
[offline acceptance](../validation/RECOVERABLE_EXECUTION_AND_POLICY_V1_ACCEPTANCE.md).
C03 preserves semantic fields/records and their ancestor paths, while unrelated
narrative keeps legacy compaction; the bound is 32 KiB per protected field/record.
P01 verifies build-input bytes before installation; manifests are integrity metadata,
not signatures or a newly tested publication image. Native Windows execution remains
NOT_OBSERVED. No historical audit NOT_OBSERVED is silently promoted to PASS.
