# Evaluator gateway foundation acceptance — 2026-09-08

Starting checkpoint: `11837c3f9fc480c651f1c3663faac854bdce574b`, branch `phase4`, clean tracked worktree. This acceptance covers the credential/access foundation, not a deployed service or paid research run.

## Evidence

- **292 offline backend tests passed**, two pre-existing FastAPI/Starlette deprecation warnings. Includes 59 new evaluator tests plus BYOK/route, MiMo, specialist, read-only/API, Memory, incremental, LLM, recovery, data/ingestion/evidence and research-path contracts.
- **32 frontend contract checks passed**: read-only Memory navigation 8/8; Object Workspace V2 24 checks.
- `npm run build`: TypeScript `tsc --noEmit` and Vite production build PASS. Existing >500 KB bundle warning remains; no frontend semantic changes were made.
- Ruff check for new evaluator code/tests/entry points PASS; `git diff --check` PASS.
- Independent read-only model/recovery, data and security reviews completed. Parent alone edited. Findings repaired: single-attempt deadline validity, FMP historical bounds compatibility, secure prompt/logging, terminal authorization evidence, recovery candidate priority, zero-quota readiness wording and truthful owned-deadline classification.

## Offline local evaluator journey

Tests generate an opaque fake credential in a temporary hash-only SQLite store, encrypt it into a temporary bundle, start an ephemeral loopback HTTP gateway with fake upstreams, decrypt/import it through the real session preparation function, and perform actual loopback HTTP readiness. Upstream calls and paid-operation counter changes remain zero. ASGI tests additionally invoke all governed model routes and bounded data transport with fake upstreams. Owner transport is exercised through HTTPX MockTransport with synthetic keys only. CLI help entry points were invoked successfully, without activating a product backend.

Same-Run / same-Task adaptive recovery is tested through the gateway: MiMo read timeout → existing detector/supervisor/policy → permitted Sol → success. Authorization rejection produces failed attempt/terminal evidence with zero provider switch. Production composition is separately tested to preserve existing Sol → Luna → MiMo priority, independent of gateway metadata order.

Credential tests cover wrong/expired/revoked tokens, model and data scope/quota, rate limit, atomic concurrent reservations, no plaintext bearer persistence, arbitrary authority rejection, secret response/log filtering, encryption roundtrip, wrong password, metadata/ciphertext tampering, corrupt/oversized bundles, secure prompt failure, failed-import session clearing, spaces/Unicode paths and Windows-drive syntax. Real UI receives no bearer field; `.env.example` has no token setting and leaves provider keys empty.

## Reproduction

From the repository root with installed development dependencies:

```bash
python -m pytest -q tests/evaluator tests/phase4/backend_product/test_evaluator_routes.py tests/phase4/backend_product/test_mimo_foundation.py tests/phase4/backend_product/test_specialist_routes.py tests/phase4/backend_product/test_readonly_projection.py tests/phase4/backend_product/test_api_contract.py tests/phase4/backend_product/test_memory_api.py tests/phase4/backend_product/test_memory_contracts.py tests/phase4/backend_product/test_memory_source.py tests/phase4/backend_product/test_memory_comparison.py tests/phase4/backend_product/test_incremental.py tests/unit/llm tests/unit/agentic/test_adaptive_recovery.py tests/unit/agentic/test_recovery_policy.py tests/unit/data/test_fmp_adapter.py tests/unit/data/test_live_fmp_integration.py tests/unit/data/test_evidence_ingestion.py tests/unit/application/test_evidence_semantics.py tests/unit/test_phase4_research_path.py
```

Despite its historical filename, `test_live_fmp_integration.py` uses fixtures/mocks; no live FMP request was authorized or made. CI includes the evaluator suite.

## Publication and security boundary

Tracked tree/new files/diff were inspected for provider keys, bearer-token patterns, private keys and accidentally committed live bundles/stores. Matches were existing deliberate dummy redaction fixtures; no real provider keys, real evaluator bearer tokens or live evaluator bundles are included. Ignore rules cover `.vfaeval` and gateway SQLite state. This pattern/source review is not a claim of universal automated secret detection.

Nine-question investor documentation journey PASS: no upstream keys needed; one private encrypted bundle; real product code; server-side keys; macOS and Windows/WSL guidance; no manual API checks; scope/expiry/quota; BYOK preserved.

**REAL_GATEWAY_DEPLOYMENT = NOT_DEPLOYED.** No live model/provider/FMP calls, new production Runs, production database migrations or GitHub push. No Owner/investor live credential was issued. Native Windows and WSL2 host execution were not performed; portable launcher implementation and path contracts are covered, not full native proof parity. macOS Keychain and Windows Credential Manager integrations are NOT_IMPLEMENTED. Full Windows proof evaluation remains recommended through WSL2. No commercial billing was implemented; actual cost remains NOT_OBSERVED.

Foundation PASS permits the next separate task: **FINAL_GITHUB_PUBLICATION**, including final README/secret audit, branch plan and local-deployable release metadata. Deploying the gateway is still an Owner operational prerequisite for live evaluator access.
