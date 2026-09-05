# Frontend V8.1 — Node 24 Compatibility Reproduction

Status: `COMPATIBILITY_REPRODUCTION_COMPLETE`

```text
NODE24_COMPATIBILITY = PASS
APPROVED_BASELINE_MUTATED = NO
FRONTEND_V17_IMPLEMENTATION_AUTHORIZED = NO
```

## Purpose and authority

This record reconciles the toolchain used to seal `FRONTEND_BASELINE_V8.1` with the root project's
declared Node range. It is compatibility evidence only. It neither changes the approved baseline nor
authorizes a V17 candidate.

| Coordinate | Value |
|---|---|
| Approved source | `d854c97789c98cca14fee3f4b3d7f00e0d5d137a` |
| Approved Git tree | `50114fa04c2a0ad81597283f5a487806e2e640cd` |
| Approved `apps/web/**` manifest | `d48a33b381ddd719867707d81c2d687ed7d9e8b95a5930d2353c94b0526c230c` (45 files) |
| Approved full tracked manifest | `8eae26088073353efa041daaa011218f1b256a19236f15b1779688fbc1096cd8` (319 files) |
| Approved witness toolchain | Node `v25.9.0`; npm `11.12.1` |
| Project engine declaration | Node `>=24 <25` |
| Compatibility toolchain | Node `v24.18.0`; npm `11.6.2`; macOS arm64 |
| Reproduction source | Fresh `git archive` of the approved source in `/tmp/frontend-v8-c1.GPQmHm` |

No repository-scoped `AGENTS.md`, `.nvmrc`, `.node-version`, `.tool-versions`, or npm
`packageManager` pin was present. The fresh archive, rather than a registered historical worktree,
was used because some historical worktrees are dirty.

## Reproduction results

Commands ran from the archived `apps/web` directory without source edits.

| Command | Result | Evidence |
|---|---|---|
| `npm ci` | `PASS` | Exit 0; 69 packages; lockfile unchanged |
| `npm run typecheck` | `PASS` | Exit 0 |
| `npm run test:runtime` | `PASS` | Exit 0; six Scenes identity-closed; dynamic 7→8; `RUN-026` 6→7; durable reopen and AVGO fail-closed checks passed |
| `npm run build` | `PASS` | Exit 0; 55 modules transformed |

## Identity comparison

The compatibility build exactly reproduced the sealed build artifact manifest:

`5fc76ef3038cc6826c54d072b99466b18d7f61a4528594fbd040f5b7a5a1a943`

| Built artifact | Node 24 SHA-256 | Approved SHA-256 | Result |
|---|---|---|---|
| `assets/index-lXgVwkVu.js` | `4477c03bbbba1fb3d952a62084e812dce4317c847d9d7a08dccafcd74b335adb` | same | `IDENTICAL` |
| `assets/index-uNV2grdZ.css` | `fe49cb94a8427786b12a3a88bb6b35b8fce3e54f00ebf5dd61ad1c040cae63d8` | same | `IDENTICAL` |
| `index.html` | `861e941316a486d356d809d4ff23cc8b1a36ea4e2cd8c4056a9958ab4b320974` | same | `IDENTICAL` |

`apps/web/package-lock.json` remained SHA-256
`55cc3eb4d61e8ab53a130c338ef22fd929545214a9d34f7466f5edf1bbb2a5e0` after `npm ci`.

## Toolchain decision

The future V17 candidate may use the project-target Node 24 line, subject to its own approved Change
Request, clean candidate freeze, candidate-specific dependency lock, and complete acceptance run.
This result does not claim that a future V17 dependency graph is compatible; it proves only that the
approved V8.1 source and lock reproduce under the current project target.

Two historical metadata mismatches are recorded without changing V8.1:

1. The original Node `v25.9.0` witness lies outside the root `>=24 <25` engine declaration.
2. The baseline manifests call the app package `verifiable-financial-agent-frontend-v8`; the actual
   package is `verifiable-financial-agent-web@0.1.0`.

Both are successor-governance metadata issues, not source or artifact identity failures.

## Gate conclusion

```text
NODE24_COMPATIBILITY = PASS
NODE24_SOURCE_MANIFEST_MATCH = PASS
NODE24_LOCKFILE_IDENTITY = PASS
NODE24_RUNTIME_TEST = PASS
NODE24_BUILD_ARTIFACT_IDENTITY = PASS
V17_CANDIDATE_TOOLCHAIN_ACCEPTANCE = NOT_RUN
```
