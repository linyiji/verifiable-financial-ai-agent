# V17 Frontend Baseline Custody and Lineage

Status: `PREPARATION_RECORD_COMPLETE`

## Governing result

```text
APPROVED_PARENT_BASELINE = FRONTEND_BASELINE_V8.1
APPROVED_PARENT_SHA = d854c97789c98cca14fee3f4b3d7f00e0d5d137a
APPROVED_PARENT_IMMUTABLE = YES
PROMOTION_CARRIER_SOURCE_EQUIVALENCE = PASS
V17_PACKAGE_IS_APPROVED_BASELINE = NO
FRONTEND_V17_IMPLEMENTATION_AUTHORIZED = NO
FRONTEND_V17_CURRENT_GATE = BLOCKED_BY_BACKEND_CONTRACT
```

## Repository inspection

The required initial inspection was performed before planning.

| Check | Observed value |
|---|---|
| Primary checkout | `/Users/mac/Verifiable_Financial_Agent_System` |
| Branch | `main` |
| HEAD | `ed8af4ba8c51ada227f433582654ced0e16ca3c4` |
| Status | Dirty: untracked frontend, audit, governance, and integration material |
| Approved-source checkout | `/Users/mac/Verifiable_Financial_Agent_System_frontend_v8_fixes` |
| Approved-source checkout status | Dirty: nine modified tracked frontend files |
| Promotion-carrier checkout | `/Users/mac/Verifiable_Financial_Agent_System_frontend_v8_1_baseline` at `e2aef1e…` |
| Promotion-carrier checkout status | Clean |
| Precursor checkout | `/Users/mac/Verifiable_Financial_Agent_System_frontend_v8` at `7eed83d…` |
| Precursor checkout status | Clean |
| Independent-audit checkout | `/Users/mac/Verifiable_Financial_Agent_System_frontend_v8_audit` at `7eed83d…` |
| Independent-audit checkout status | Dirty: untracked audit material |

The current `main`, dirty approved-source checkout, and dirty independent-audit checkout are recorded
as `NON_AUTHORITATIVE_DIRTY_WORKTREE`. They were inspected to understand repository state but were
not used as baseline implementation authority, cleaned, reset, or incorporated into a candidate.
Six additional dirty registered worktrees were unrelated to this frontend preparation and were also
excluded. The complete registered-worktree inventory was captured with `git worktree list`.

## Approved parent identity

| Property | Sealed value | Verification |
|---|---|---|
| Baseline ID | `FRONTEND_BASELINE_V8.1` | Manifest and promotion record agree |
| Approved source SHA | `d854c97789c98cca14fee3f4b3d7f00e0d5d137a` | Object resolves |
| Git tree | `50114fa04c2a0ad81597283f5a487806e2e640cd` | `d854c977^{tree}` |
| `apps/web` subtree | `1fbe35f4f2457f687b5f6045594e656f5b23ec5d` | Identical at source and carrier |
| Frontend source manifest | `d48a33b381ddd719867707d81c2d687ed7d9e8b95a5930d2353c94b0526c230c` | Recomputed over 45 tracked `apps/web/**` files |
| Full tracked manifest | `8eae26088073353efa041daaa011218f1b256a19236f15b1779688fbc1096cd8` | Recomputed over 319 files |
| `package.json` SHA-256 | `5f28c0b7aa865cb38da651f816d89db784e2186028f2e565a4176256a39a00de` | Matches manifest |
| `package-lock.json` SHA-256 | `55cc3eb4d61e8ab53a130c338ef22fd929545214a9d34f7466f5edf1bbb2a5e0` | Matches manifest |
| Build artifact manifest | `5fc76ef3038cc6826c54d072b99466b18d7f61a4528594fbd040f5b7a5a1a943` | Node 24 reproduction identical |

## Promotion-carrier equivalence

The governance carrier `e2aef1edc22631dc988c862c18972f0fd7630625` is a direct child of the
approved source. Its delta adds exactly these six records:

- `docs/frontend-governance/FRONTEND_BASELINE_V8_1_MANIFEST.json`
- `docs/frontend-governance/FRONTEND_BASELINE_V8_1_MANIFEST.md`
- `docs/frontend-governance/FRONTEND_BOOTSTRAP_PROMOTION_RECORD.md`
- `docs/frontend-governance/FRONTEND_INTERACTION_BASELINE_V8_1.md`
- `docs/integration/PHASE4_E2E_ACCEPTANCE_SPEC_V8_1_DELTA.md`
- `docs/integration/PHASE4_E2E_GATE_ACTIVATION_MATRIX_V8_1_DELTA.md`

`git diff d854c977… e2aef1ed… -- apps/web` is empty. Both commits resolve
`apps/web` to `1fbe35f4f2457f687b5f6045594e656f5b23ec5d`; package and lock blobs are also
identical. Therefore the carrier is governance-only and does not replace the approved source SHA.

## V17 package custody

The inspected reference archive is:

`/Users/mac/Downloads/Verifiable_Financial_Agent_Frontend_V17_Integration_Package_WITH_HANDOFF.zip`

SHA-256:
`b90a356d666c30a07362f080fd418a2cf051c9b80483d308eac474dc51d79f31`

It was expanded under an isolated `/tmp/v17-prep.*` directory for read-only inspection. The archive
contains 65 files: 61 entries declared by `MANIFEST_V17.json`, that manifest itself, and three
handoff documents omitted from its file list. This omission is a package-manifest completeness defect;
it does not grant the omitted files authority.

The declared README SHA-256 is also stale: the manifest records
`017d04be45ff2ac1969c2a358f644cf1239371cdec20b30c8ddc1b445d9015e7`, while the actual README in
the WITH_HANDOFF archive is
`21785aaef9d8e1882119f875493b0430c9df11a92c0a91b4bca1054d65e75ba8`. A corrected package/reference
manifest is therefore required before Change approval.

The package is classified only as:

- target UX and behavior reference;
- target product-contract input;
- target file/component map;
- integration scaffold.

It is not an Approved Frontend Baseline, backend-freeze record, implementation candidate, or proof of
real REST/SSE behavior. `references_v8.html` matches the V8 HTML file content hash
`d4131743eb30e41e52e1b17bfa27ba485f5f79378a7ac04dcce15c5eb87beda6`; the
V17 reference hash is `1cc44c95017b2178e39138b1310e02c55d849dd71af50b63c074686a215ed18d`.
Neither HTML file may be pasted wholesale into production React.

Material conflicts in the package scaffold are deliberately not adopted: a hard-coded `OBJ-NVDA`
fallback, hard-coded financial values, local canonical Run stage state, unsupported future mutation
types, raw placeholder HTTP/SSE behavior, and production composition that imports Demo/Presenter
material. Each must be resolved by the governed candidate, not treated as existing implementation.

## Future candidate lineage and custody rules

The future candidate must be created only after the Change Request is approved and the backend
contract freeze closes all Phase 4 blockers. It must:

1. start from a fresh clean worktree or archive at `d854c977…` (with the governance carrier records
   applied or referenced without changing `apps/web` lineage);
2. use a `codex/`-prefixed branch unless the repository owner specifies another name;
3. never copy uncommitted content from any historical frontend checkout;
4. record candidate SHA, Git tree, all tracked/untracked inputs, package-lock hash, Node/npm versions,
   build command, and artifact manifest;
5. bind the exact approved Change Request revision, backend contract version/SHA, V17 reference hash,
   interaction ledger revision, Scene corpus, and test plans;
6. freeze `App.tsx` composition under the Coordinator after shared-contract and worker integration;
7. create a new candidate for any source, lockfile, reference, contract, fixture, or oracle change;
8. undergo focused regressions and an independent Delta Audit before any promotion.

No candidate, branch, worktree, merge, or application edit was created by this preparation.

## Toolchain conclusion

The separate compatibility record proves `NODE24_COMPATIBILITY = PASS`. This allows the future V17
candidate to use the project Node 24 line subject to candidate-specific acceptance. It does not rewrite
the original Node 25 witness and does not predict compatibility of a changed V17 dependency graph.
