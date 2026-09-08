# Phase 5B Scheme repair — pre-live only

[简体中文](PHASE5B_SCHEME_REPAIR_RECEIPT.zh-CN.md)

Start and final HEAD: `d414ec084aa03f65b56d6e465a7706dd3e2decef`.
The pre-existing Phase 5B dirty worktree is preserved. No commit, tag or push.

## Root cause and evidence limits

One authorized planning-only diagnostic HTTP attempt reproduced HTTP 400 with
schema/required-field rejection. It created no Research Run. The old incremental
output schema had an open dictionary under a strict structured-output request;
the actual adapter forwards the Pydantic schema unchanged. Local schema inspection
demonstrates the incompatibility. The remote safe flags mention schema and required,
not additionalProperties specifically. Historical generic ValueError handling had
discarded the provider classification. No raw provider error/message is published.

Repair replaces the dictionary with closed typed decision records, preserves safe
failure stage/classification, resolves proposals against exact immutable source
identities, and aligns the frontend decoder and sparse-memory acceptance policy.
It removes fabricated whole-view REUSE and allows bounded Research Lead judgment.
UNKNOWN cannot become reuse. A resolved issue needs exact PERIOD_MISMATCH authority.

The repaired schema was verified using the production HTTP serializer/parser with
MockTransport, not a second paid model call. Remote acceptance of the repaired
schema is therefore not yet observed. This is a local pre-live gate, not live Phase
5B completion or Memory v2 acceptance. The diagnostic script's exclusive HTTP marker
must not be removed or bypassed to repeat a paid call in this task.

## Verification

- 203 focused Python tests passed, plus 4 isolated PostgreSQL exact-base rejection tests.
- 187 frontend checks passed: incremental 23, memory 20, M3 14, R1 provenance 6,
  M4 27, M5 37, M6 35, progress 10, lifecycle 15.
- Typecheck and production build passed.
- 17 browser checks passed on an explicitly labeled local HTTP-mocked draft.
  Actual R1 Report/Review/Execution were read through the production GET surfaces.
- Visually inspected both Scheme screenshots: only the three real decision items,
  no invented reuse section; current Goal, work requirements and confirmation shown.
- Preview-only independent task graph validated without admission or a new DB Run.
- Browser harness disables scheduler startup and blocks all writes except a local,
  nonpersisted prepare response. An admission request was blocked before backend.
  Its initial media-type defect was repaired to match the frozen UTF-8 contract.

Evidence is under `artifacts/phase5b_scheme_repair/`: planning-diagnostic-result.json,
local-preview-draft.json, browser-pre-live.json, preview-firewall.json,
history-guard.json, scheme-decisions-preview.png, scheme-current-work-preview.png.
The accepted browser pass had one local prepare and zero provider calls. Separate
from that harness, the diagnostic above used exactly one real planning HTTP attempt.

All 36 existing Run IDs and R1/v1 fingerprints were unchanged. Latest remains
`RUN-57aed683-75d6-4b47-acc6-a73053ea492e` / View 1
(`RVV-05bec42f-ab9b-55c5-b502-c439b8abe948`). No R2 or Memory v2 was created.

Local gate PASS; next authorized phase is one live incremental R2. STOP here.
