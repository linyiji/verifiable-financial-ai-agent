# WS-V — Real RISC Zero Revenue Growth Proof

## Phase 3 F2 financial-audit remediation (authoritative current release)

The historical WS-V record below is retained as provenance for the original proof work. It is
superseded for the Phase 3 remediation candidate by the release built from immutable failed
candidate `e02314c552d88fb736473bc587c650539615224a` on
`codex/phase3-remediation-revenue-risc`.

The reviewed formula is now exactly:

```text
(current_revenue - prior_revenue) / prior_revenue
```

It has the explicit precondition `prior_revenue > 0`. Zero and negative prior revenue fail closed
at the native capability, independent reviewer/oracle, proof-input validator, host, and guest
boundaries with `REVENUE_GROWTH_PRIOR_REVENUE_MUST_BE_POSITIVE`. No percentage or proof is
produced for those inputs. Capability version `1.1.0` records the corrected production semantics.

The same release manifest now binds the formula expression, precondition, and validation reason.
Its existing Phase 3 gates were strengthened without expanding the 52-gate namespace: FS-005
checks exact native/reviewer semantics and formula metadata, while P3-ZK-008 checks zero/negative
rejection plus separate prior/current tamper resistance.

### Rebuilt release identity

| Evidence | Remediation value |
| --- | --- |
| Image id | `491e8fb2335a465b112dda11b16b6dcec703e11b1bfa3d21ebaec177c3847e36` |
| Guest ELF SHA-256 | `sha256:454aa141740723afbb5beeeb9f8100947bf05b04853a4c39d4230a4b9d4e76cb` |
| Guest combined binary SHA-256 | `sha256:afbcd20dbe0cbbcfb91a031e0fcc75961ad854d56d9fe832c8c5420e95905f60` |
| Normalized host SHA-256 | `sha256:ad29b18f648661f8cfb144677baeaa9ad931210ed08aab4c4216af444b8fe3df` |
| Source-set SHA-256 | `sha256:f9298b08b95126e4ed225af59463f9368724d9dc2de938a80abb06982fe033cc` |
| Release-manifest SHA-256 | `sha256:be89ab2127d229a77e6fa8acb3e3eaa0592ecd7153d6dc189cca83cd640b3724` |

Two formal builds from different absolute directories produced byte-identical guest ELF, combined
guest binary, normalized host binary, and image id. The new fixed-fixture formal receipt verified
against that image with receipt hash
`sha256:c6685bbfcc6a3ebe8ff99f0c216bdfdacaea2da662cf2d28ebd0d315c1c00d27`
and journal hash
`sha256:eb83a8d00a644980e2be01b3bac411268edbf5d6ce416b6be9519573dd892e2b`.
The local ignored evidence is
`artifacts/risc0/phase3-remediation-f2/revenue-growth.receipt` (256610 bytes, mode `0600`).

Required negative coverage includes zero prior, negative prior, tampered prior, tampered current,
tampered expected result, wrong image, and corrupted receipt. This remediation does not start
Phase 4.

Verification for the remediation release:

- targeted Python financial/RISC/acceptance tests: **57 passed**;
- Rust workspace tests: **5 passed**;
- full Python suite, including real RISC proving and all receipt negatives: **339 passed,
  3 PostgreSQL-only skips**;
- two-build cross-absolute-path reproducibility: **PASS**;
- Ruff, focused Ruff format, Cargo format, compileall, diff whitespace, and strict release/source
  manifest closure: **PASS**.

---

Baseline: `21b797683120b015a400312cd857dc3c118547a3`

Branch: `ws/risc-zero-proof`

Status: **PASS**

Frontend: **NOT TOUCHED**

## Outcome

WS-V implements a real RISC Zero 3.0.6 receipt for `revenue_growth_v1`. The guest computes
revenue growth with signed integer inputs and emits an exact reduced rational; no floating-point
arithmetic is used. A separate verifier invocation cryptographically verifies the receipt against
the compiled image id before comparing its journal to an independently derived canonical
expectation.

Runtime call path:

```text
ProofPolicy / ProofRequest
→ RiscZeroProofAdapter.prove
→ pre-built revenue-growth-proof-host prove
→ revenue-growth-guest in RISC Zero zkVM
→ real receipt artifact (status VALID)
→ RiscZeroProofAdapter.verify
→ separate revenue-growth-proof-host verify process
→ Receipt::verify(compiled image id)
→ journal/commitment comparison
→ ProofResult status VERIFIED
```

The adapter invokes only the pre-built host executable. It contains no Cargo invocation or shell
command construction. Build commands are centralized in `zk/revenue_growth/build-host.sh`.

## Proof bindings

The input commitment binds:

| Binding | Fixture value |
| --- | --- |
| Run | `RUN-RISC0-NVDA-001` |
| Calculation | `CALC-REVENUE-GROWTH-001` |
| Formula | `revenue_growth_v1` |
| Capability | `revenue_growth` |
| Python implementation hash | `sha256:f583ff894c388b8677bde486760ea14fc702278cfaa2229cb007221f1ba20765` |
| Evidence refs | `EVD-NVDA-REVENUE-FY2024`, `EVD-NVDA-REVENUE-FY2025` |
| Canonical inputs | prior `6092200000000`, current `13049700000000`, `USD`, scale `2` |
| Expected exact result | `69575 / 60922` ratio |
| Input commitment | `sha256:515bde26968e1b25e621866342adf4f9438b0a45c6ce3e01126509ebc127d640` |
| Output commitment | `sha256:a701eaf10065178b019ff90f3ea20a82f43500afe36f6bfb7a71bff117506d20` |

The guest revalidates both commitments. Its public journal contains the formula id, image id,
input commitment, expected output commitment, and canonical rational result.

## Real receipt evidence

Formal run id: `PROOF-RISC0-REAL-NVDA-WS-V`

| Evidence | Value |
| --- | --- |
| Proof status | `VERIFIED` |
| Dev mode | `false` (and `RISC0_DEV_MODE` absent) |
| Image id | `f49335e68f2f12c7f9f144bc587c9bb735e8c6be1edaab2b52a67828c989a354` |
| Guest ELF SHA-256 | `96306a4146330b9379badc124023f5fed43ed9105ef33930c2dba93452f62e96` |
| Host binary SHA-256 | `8f622fd58f3e7493ed35d6fdf048cbbfa84e912dcd4e7ae60bed6e5fe0c206c4` |
| Receipt SHA-256 | `237ef3f61cd7e4e2adef30e260cdc00be5ff16243a4d0ed5aa085cfa8aa5c4ac` |
| Journal SHA-256 | `74cfcdf1143df81ec80d62aa7c8d653f2725012b8c88daaa9fb4353c99d4d57a` |
| Receipt size/mode | `256610` bytes / `0600` |
| Proving duration | `24472 ms` |
| Canonical result | numerator `69575`, denominator `60922`, unit `ratio` |

The local ignored receipt is at:

```text
artifacts/risc0/ws-v/0b8f3d2190710b3add6bb5af22bb76fa0702f47deee11696a6d80046c1a8c193.receipt
```

Receipts and compiled binaries are deliberately not committed.

## Fail-closed properties

- Host crate enables `risc0-zkvm/disable-dev-mode`.
- Adapter, build wrapper, prover command, and verifier command reject `RISC0_DEV_MODE` presence.
- The receipt becomes `VALID` after proving and only becomes `VERIFIED` after a second host process
  calls `Receipt::verify` with the compiled image id.
- The adapter independently checks artifact SHA-256, image/program identity, commitments, and
  canonical output.
- Proof input and receipt artifacts are copied/written under adapter control with mode `0600`.

Negative acceptance tests passed for:

1. tampered canonical revenue with internally valid replacement commitments;
2. tampered expected result/output commitment;
3. wrong expected program image id;
4. corrupted serialized receipt;
5. `RISC0_DEV_MODE` present even when its value is `0`.

## Toolchain

| Component | Version |
| --- | --- |
| Host `rustc` | `1.98.1 (48a229cea 2026-09-01)` |
| Host `cargo` | `1.98.1 (797e8a9bc 2026-08-05)` |
| `rzup` | `0.5.0` |
| `cargo-risczero` | `3.0.6` |
| `r0vm` | `3.0.6` |
| RISC Zero guest Rust | `1.97.0` |
| RISC Zero C++ toolchain | `2024.1.5` |
| `risc0-zkvm` / `risc0-build` | exact `3.0.6` |
| Host architecture | `arm64-apple-darwin` |

The canonical crates.io CDN returned intermittent TLS errors on this machine. Dependencies were
prefetched with checksum validation while the connection recovered. The authoritative image above
was then produced by a clean, canonical crates.io-source offline build with no source replacement.
No mirror is frozen into project config or the controlled build wrapper.

## Verification

- `cargo test --locked --manifest-path zk/revenue_growth/Cargo.toml --workspace`: **3 passed**.
- `pytest -q tests/risc0` with the real host binary: **11 passed**, including one real prove and all
  negative verification cases.
- Full `pytest -q`: **173 passed, 3 skipped**. The skips are existing real PostgreSQL tests whose
  database settings were unavailable in this isolated worktree; no RISC Zero tests were skipped.
- `ruff check src tests`: **PASS**.
- `cargo fmt --manifest-path zk/revenue_growth/Cargo.toml --all --check`: **PASS**.

## Contract change request

No frozen shared contract, Settings, `pyproject.toml`, or global DB schema was changed.
`docs/CONTRACT_CHANGE_REQUEST_WS_V_PROOF_PERSISTENCE.md` requests Coordinator-owned durable
persistence for frozen proof commitments, records, verifications, and artifact references.

## Scope boundary

This proof establishes execution integrity for the committed deterministic program, inputs, and
result. It does not establish that the provider revenue data is objectively true and it does not
prove any LLM narrative or investment conclusion.
