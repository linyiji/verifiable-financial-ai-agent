# V17 Reference Manifest Correction Record

Record ID: `V17-RMCR-001`  
Disposition: `COMPANION_MANIFEST_VALIDATED`  
Recorded at: `2026-09-04T07:21:18Z`  
Change class: documentation/governance correction only

## Decision

The reference-manifest blocker is closed by the separately versioned `V17_REFERENCE_MANIFEST_V1.json`, which accounts for and classifies every one of the archive's 65 members. The embedded `MANIFEST_V17.json` remains unchanged and retains status `FAIL_INCOMPLETE_AND_STALE_README_METADATA`.

This record closes only the reference-manifest defect. It does not approve the draft V17 FCR, authorize frontend implementation, start Phase 4 or Phase 5, establish backend contract readiness, or promote package content to baseline, production, or backend authority.

## Evidence

| Item | Verified result |
|---|---|
| Requested ZIP SHA-256 | `b90a356d666c30a07362f080fd418a2cf051c9b80483d308eac474dc51d79f31` |
| Isolated inspection copy | Byte-identical to requested ZIP |
| Actual members | `65` |
| Original embedded records | `61` |
| Original manifest completeness | `FAIL` |
| Corrected companion completeness | `PASS` (`65/65`) |
| Unsafe paths | `0` |
| Duplicate normalized paths | `0` |
| Archive order | `NON_LEXICOGRAPHIC`, recorded by `archive_index` |
| V8 HTML reference | SHA-256 `d4131743eb30e41e52e1b17bfa27ba485f5f79378a7ac04dcce15c5eb87beda6`; byte-identical to approved repository baseline HTML |
| V17 HTML reference | SHA-256 `1cc44c95017b2178e39138b1310e02c55d849dd71af50b63c074686a215ed18d`; UX/behavior reference only |
| Canonical 65-member content-list SHA-256 | `d1410ffbec469e3f6708ef07f94f3db5de2b4c992a0ed8d7f571a4e3945a33e9` |
| Exact companion JSON SHA-256 | `44be67d6854a284055c19919bcaf979097c710b33d3e5f57c5f7a35fe376f394` |

## Corrected defect details

The embedded manifest omitted these four archive members:

1. `MANIFEST_V17.json`
2. `handoff/01_GPT_HANDOFF_V17.md`
3. `handoff/02_GPT_EXECUTION_INSTRUCTION_V17.md`
4. `handoff/03_COPY_PASTE_STARTER_PROMPT.md`

It also contained stale `README.md` metadata:

| Field | Embedded declaration | Actual archive member |
|---|---|---|
| Size | `2567` | `3067` |
| SHA-256 | `017d04be45ff2ac1969c2a358f644cf1239371cdec20b30c8ddc1b445d9015e7` | `21785aaef9d8e1882119f875493b0430c9df11a92c0a91b4bca1054d65e75ba8` |

All other 60 embedded records match their corresponding archive members. The corrected companion includes the four omissions, the actual README metadata, and the embedded manifest itself, yielding complete 65-member accounting.

## Governance controls retained

- The allowed `authority_class` vocabulary is only `REFERENCE_ONLY`, `GOVERNANCE_ONLY`, `DEMO_ONLY`, `PHASE5_DEFERRED`, `OUT_OF_SCOPE`, and `TARGET_SCAFFOLD_INPUT`.
- Class totals remain aligned with the V17 file-change matrix: `24`, `5`, `6`, `2`, `1`, and `27`, respectively.
- `backend_contracts/models.py` is `REFERENCE_ONLY` / `TARGET_CONTRACT_INPUT`, never backend authority.
- The `.pyc` cache member is accounted for as `OUT_OF_SCOPE` / `COMPILED_DEBRIS` and excluded from implementation authority.
- The nine known scaffold warnings remain unresolved inputs, not accepted behavior: `OBJ-NVDA`, hardcoded financials, local Run-stage authority, fresh retry idempotency keys, raw JSON casts/stringification, named-event-blind SSE, unsupported mutation types, Demo/Presenter coupling, and false terminal `release.completed` handling.
- Precedence remains V8.1 baseline, approved frontend governance, future approved V17 FCR revision, corrected companion manifest, package documents/scaffold, then HTML UX references. The actual repository and approved contracts win conflicts.

## Artifact integrity convention

`V17_REFERENCE_MANIFEST_FILES.sha256` contains the canonical sorted member lines and therefore hashes to the JSON's `content_manifest_sha256`. The JSON omits a self-hash to avoid recursion. Its exact external file digest is frozen here and in the companion explanatory document as `V17_REFERENCE_MANIFEST_SHA256`.

## Scope attestation and gate state

Only the following companion governance artifacts were added:

- `docs/frontend-governance/V17_REFERENCE_MANIFEST_V1.json`
- `docs/frontend-governance/V17_REFERENCE_MANIFEST_V1.md`
- `docs/frontend-governance/V17_REFERENCE_MANIFEST_CORRECTION_RECORD.md`
- `docs/frontend-governance/V17_REFERENCE_MANIFEST_FILES.sha256`

The archive, embedded manifest, baseline manifests, existing draft FCR, frontend source, backend source, and pre-existing dirty-worktree content were not modified. No branch, worktree, implementation candidate, or merge was created.

```text
V17_REFERENCE_MANIFEST_CORRECTED=YES
REFERENCE_MANIFEST_BLOCKER=CLOSED
BACKEND_CONTRACT_BLOCKER=OPEN
CHANGE_APPROVAL_READY=NO
FCR_STATUS=DRAFT_CHANGE
FRONTEND_V17_IMPLEMENTATION_AUTHORIZED=NO
FRONTEND_V17_CURRENT_GATE=BLOCKED_BY_BACKEND_CONTRACT
```

Historical preparation documents that record the manifest defect as open were not edited in this focused correction. Their disclosure of the defective embedded manifest remains true; this record is the auditable closure evidence for the separate companion-manifest requirement.
