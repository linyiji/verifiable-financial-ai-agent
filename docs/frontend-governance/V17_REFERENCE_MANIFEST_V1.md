# V17 Corrected Reference Manifest V1

Status: `CORRECTED_COMPANION_REFERENCE_MANIFEST`  
Manifest ID: `V17_REFERENCE_MANIFEST_V1`  
Generated at: `2026-09-04T07:21:18Z`  
Scope: documentation and governance only

## Purpose and authority boundary

This companion manifest corrects the accounting defect in the V17 integration package's embedded `MANIFEST_V17.json`. It does not modify that ZIP or embedded manifest, approve an FCR, authorize Phase 4, establish backend availability, or grant any package member baseline or production authority.

The machine-readable record is `V17_REFERENCE_MANIFEST_V1.json`. `V17_REFERENCE_MANIFEST_FILES.sha256` is the exact canonical 65-member content list described below.

## Archive identity and inspection result

| Check | Result |
|---|---|
| Archive | `Verifiable_Financial_Agent_Frontend_V17_Integration_Package_WITH_HANDOFF.zip` |
| Archive SHA-256 | `b90a356d666c30a07362f080fd418a2cf051c9b80483d308eac474dc51d79f31` |
| Archive size | `198339` bytes |
| Common ZIP root | `Verifiable_Financial_Agent_Frontend_V17_Integration_Package_WITH_HANDOFF/` |
| ZIP entries / regular-file members | `65 / 65` |
| Total uncompressed member bytes | `607909` |
| Archive central-directory order | `NON_LEXICOGRAPHIC` |
| Unsafe member paths | `0` |
| Duplicate raw paths | `0` |
| Duplicate normalized paths | `0` |
| Directory entries | `0` |
| Symlink entries | `0` |
| Compiled/cache members | `1` |

Inspection used an isolated, byte-identical temporary copy of the requested archive. No archive code was executed or imported. Every member was read as bytes, its uncompressed length was checked against ZIP metadata, and its SHA-256 was recomputed.

Path normalization validates the original ZIP name before transformation, requires the exact common root above, strips that root exactly once, and then requires a non-empty NFC POSIX-relative path with no absolute prefix, backslash, control character, empty segment, `.` segment, or `..` segment. The resulting rootless path is the manifest key. Each member's one-based central-directory position is preserved in `archive_index`.

## Original manifest defect

The embedded manifest remains defective and is not replaced in place:

- Its `files` array contains 61 records and has no explicit member-count field.
- It omits `MANIFEST_V17.json` and all three `handoff/` members.
- Its `README.md` record declares size `2567` and SHA-256 `017d04be45ff2ac1969c2a358f644cf1239371cdec20b30c8ddc1b445d9015e7`.
- The archive's actual `README.md` is size `3067` and SHA-256 `21785aaef9d8e1882119f875493b0430c9df11a92c0a91b4bca1054d65e75ba8`.
- The other 60 embedded records match their archive members by size and SHA-256.

Therefore `ORIGINAL_MANIFEST_COMPLETENESS=FAIL`. The companion JSON accounts for `65/65`, so `CORRECTED_MANIFEST_COMPLETENESS=PASS`.

## Reference checks

- `references_v8.html`: `d4131743eb30e41e52e1b17bfa27ba485f5f79378a7ac04dcce15c5eb87beda6`. It is byte-identical to `frontend_reference/financial_agent_workspace_v8_dynamic_path.html` and remains reference-only.
- `references_v17.html`: `1cc44c95017b2178e39138b1310e02c55d849dd71af50b63c074686a215ed18d`. It is UX/behavior input only and remains reference-only.
- Package `README.md`: recorded at its actual archive digest above. It is a package reference document and must never overwrite the repository `README.md`.
- `backend_contracts/models.py`: `REFERENCE_ONLY`, with source relationship `TARGET_CONTRACT_INPUT`; it is not backend implementation authority.
- `backend_contracts/__pycache__/models.cpython-313.pyc`: `OUT_OF_SCOPE` / `COMPILED_DEBRIS`; it is fully accounted for but excluded from implementation authority.

## Classification totals

The `authority_class` vocabulary is closed to the following values and is aligned with the approved V17 file-change matrix.

| Authority class | Members | Meaning |
|---|---:|---|
| `TARGET_SCAFFOLD_INPUT` | 27 | Phase 4 scaffold input requiring governed reconciliation; never approval or source authority |
| `REFERENCE_ONLY` | 24 | Documentary, contract, style, or HTML reference only |
| `DEMO_ONLY` | 6 | Demo fixtures, transport, datasource, or presenter behavior; never production authority |
| `GOVERNANCE_ONLY` | 5 | Embedded manifest, coordination prompt, and handoff inputs |
| `PHASE5_DEFERRED` | 2 | Research Memory and Compare scaffold; excluded from Phase 4 |
| `OUT_OF_SCOPE` | 1 | Compiled/cache debris |
| **Total** | **65** | Complete archive accounting |

`content_role`, `phase_class`, and `source_relationship` refine these authority classes; they do not elevate them. Their concrete values and the classification of every member are frozen in the companion JSON.

## Canonical content-manifest algorithm

1. Use all 65 validated rootless archive-relative paths.
2. Sort them lexicographically by that normalized path.
3. For each member, emit the UTF-8 byte sequence `<sha256><two spaces><size_bytes><two spaces><path>\n`.
4. Concatenate all 65 lines, including the final LF.
5. Compute SHA-256 over those exact bytes.

Canonical content-list SHA-256: `d1410ffbec469e3f6708ef07f94f3db5de2b4c992a0ed8d7f571a4e3945a33e9`.

The JSON deliberately has no self-hash field. The external SHA-256 of the exact final `V17_REFERENCE_MANIFEST_V1.json` bytes is `44be67d6854a284055c19919bcaf979097c710b33d3e5f57c5f7a35fe376f394`; this is the value reported as `V17_REFERENCE_MANIFEST_SHA256`.

For archive-order auditability, the JSON also records a separate digest over one-based central-directory index and normalized path: `168164a1bf3c12eb18046edc7f99a1fe9ed1cf762c651635b02fec34fa1cb48c`.

## Frozen precedence and conflict rule

Precedence is, from highest to lowest:

1. V8.1 baseline.
2. Approved frontend governance.
3. A future approved V17 FCR revision.
4. This corrected V17 reference manifest.
5. Package documents and scaffold.
6. HTML UX references.

Whenever package material conflicts with the actual repository or an approved contract, the repository and approved contract govern.

## Preserved scaffold warnings

The companion manifest records the package without correcting or accepting these known scaffold defects:

1. Hardcoded `OBJ-NVDA` fallback.
2. Hardcoded financial values.
3. Local Run-stage state presented as if authoritative.
4. Retry creation of a fresh idempotency key.
5. Raw JSON casts and `JSON.stringify` display paths.
6. Native SSE handling that is blind to named events.
7. Unsupported future mutation types.
8. Demo/Presenter coupling and possible production leakage.
9. False terminal treatment of `release.completed`.

## Gate disposition

```text
V17_REFERENCE_MANIFEST_CORRECTED=YES
REFERENCE_MANIFEST_BLOCKER=CLOSED
BACKEND_CONTRACT_BLOCKER=OPEN
CHANGE_APPROVAL_READY=NO
FRONTEND_V17_IMPLEMENTATION_AUTHORIZED=NO
FRONTEND_V17_CURRENT_GATE=BLOCKED_BY_BACKEND_CONTRACT
```

The existing FCR remains `DRAFT_CHANGE`. No frontend or backend production source, baseline artifact, branch, worktree, or implementation candidate was created or changed by this correction.
