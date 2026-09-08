# Owner-operated Evaluation Gateway

[简体中文](EVALUATOR_GATEWAY.zh-CN.md)

Status: foundation implemented, offline acceptance only. **REAL_GATEWAY_DEPLOYMENT = NOT_DEPLOYED.** No automatic hosting, public issuance, commercial billing or SaaS authentication is supplied. Deploy deliberately before giving evaluators a live bundle.

Current investors and testers should use [direct-provider BYOK](LOCAL_DEPLOYMENT.md): API integrations are built in, but API keys are not embedded. Bring your own keys or receive separately scoped, revocable test keys privately from the Owner. The Docker installer supports gateway mode only, not turnkey BYOK, and its standard image does not package full proof tooling.

## Boundary and configuration

The separate `apps.evaluator_gateway.main:create_app` factory holds Owner BYOK authority. Local evaluator LLM/FMP transports call only this gateway. The existing product retains Scheme, specialist, data normalization, proof, memory and adaptive recovery contracts.

| Registered route | Owner mapping |
| --- | --- |
| teamorouter-sol | TeamoRouter / TEAMOROUTER_MODEL (default gpt-5.6-sol) |
| teamorouter-luna | TeamoRouter / TEAMOROUTER_FALLBACK_MODEL (default gpt-5.6-luna) |
| mimo-direct | MiMo / governed MIMO_CHAT_MODEL (default mimo-v2.5) |

Owner registration comes from existing route configuration, not evaluator-provided URLs/models. Configure all three routes on the gateway. No new provider is added. Only bounded FMP `profile`, `income`, `balance`, `cashflow`, `peers`, `quote`, `historical`, `analyst`, `news` and `transcript` operations are accepted. Parameters, single-symbol identity, pagination and historical span are validated against the current adapter contract. See canonical `PATHS` in [contracts](../../src/evaluator/contracts.py) for exact upstream paths.

Only `GET /v1/session`, `POST /v1/model`, `POST /v1/data` are exposed. Arbitrary provider/model/URL/method/upstream-path fields are rejected. A structured model request may carry bounded messages and output schema, but cannot change registered network/model authority. No tool execution is exposed by the gateway. It is not a generic HTTP proxy.

## Deploy on an Owner-controlled host

Install Python 3.11 and `python -m pip install -e '.[postgres]'`. Use an isolated Owner checkout/process and protected environment or private dotenv, never the evaluator's checkout. Set `VFA_CREDENTIAL_MODE=byok` and the Owner FMP, TeamoRouter and MiMo credentials. Use the existing [BYOK authority contract](LOCAL_DEPLOYMENT.md); do not commit configuration. Gateway state is separate from all research PostgreSQL databases.

Example POSIX deployment skeleton (substitute private provisioned paths):

```bash
umask 077
export VFA_GATEWAY_STORE=/private/owner-state/evaluation.gateway.sqlite
python -m uvicorn apps.evaluator_gateway.main:create_app --factory --host 127.0.0.1 --port 8020 --no-access-log
```

The directory must already exist, be Owner-only, and support SQLite transactions. Protect the database and its journal/backups with filesystem permissions; Windows operators must apply equivalent private ACLs. The app sets POSIX database mode 0600; it does not administer Windows ACLs. Do not put this store in research artifacts or sync it to investor machines. Use one durable database on one host; shared-network-filesystem/distributed/HA operation is not implemented. SQLite atomic reservations serialize competing processes against the same store.

Before live use, place an Owner-managed HTTPS reverse proxy in front of loopback. Configure certificate renewal, request/body/rate/connection limits, no cache, no request/response body capture, and no Authorization/header/query logging at proxy/APM layers. The application caps input at 512 KB; rate-limit unauthenticated traffic at the edge. Do not turn on HTTPX/HTTPCore debug or raw packet tracing: FMP authenticates in query parameters. Built-in gateway startup suppresses these transport logs and emits only owned safe audit metadata. Do not run this as a public-debug server.

Upstream timeouts: one model HTTP attempt with 60-second transport timeout and an 80-second owned dispatch deadline. No hidden retry or fallback in the gateway. The client has a 90-second model deadline; lost gateway authority/uncertain dispatch fails closed without automatic replay. Genuine classified upstream failures retain existing runtime policy eligibility; an owned overall deadline remains nonrecoverable under current policy. Data normalization/retries remain in the product FMP adapter, each new transport operation consuming another reservation.

## Issue privately, revoke by identifier

Owner CLI only; there are no administrative HTTP or product UI routes. Use a real interactive terminal. Example defaults: seven days, 100 model operations, 500 data operations, 30 paid operations/minute:

```bash
python scripts/evaluator_admin.py --store /private/owner-state/evaluation.gateway.sqlite issue --gateway-url https://evaluation.example.org --output /private/delivery/investor-a.vfaeval --days 7 --routes teamorouter-sol teamorouter-luna mimo-direct --financial-data --llm-requests 100 --data-requests 500 --requests-per-minute 30
```

The `.example.org` URL is illustrative, not a deployed service. Enter a strong random passphrase twice (minimum 12 characters). The CLI prints only the non-secret credential ID; it uses exclusive file creation and will not overwrite a prior bundle. Keep the encrypted bundle outside the repository; distribute it privately, with its password out of band. Issuance failure revokes any just-created credential. Issuance does not test or call providers.

```bash
python scripts/evaluator_admin.py --store /private/owner-state/evaluation.gateway.sqlite revoke --credential-id <issued-public-id>
```

Revocation invalidates subsequent readiness/model/data authorization without a client update. An already-reserved in-flight operation is not forcibly cancelled. Lost bundle/password: revoke and issue a new credential; do not recover plaintext from storage. Securely retain store/backups; counters rolled back through a stale backup can re-enable old allowance, so revoke affected credentials during restore.

## Quotas, readiness and audit

Opaque 256-bit random bearer tokens have only SHA-256 verifiers stored with ID, scope, expiry, revoked status, LLM/data counters and fixed-minute accounting. Authorization is never based on evaluator-supplied Run/Task IDs. Each accepted model/data dispatch reserves one operation before upstream work; failed calls and disconnects are not refunded. Rejections reserve zero. Limits are request counts, not guaranteed dollar/spend caps; model output/body caps add bounds. Fixed-minute limits can allow a boundary burst. No per-user invoice, credits, top-up or payments are implemented. Cost is `NOT_OBSERVED`.

Readiness validates current credential status and returns configured allowed routes, data scope, expiry, remaining quotas and gateway version. It makes **zero upstream requests**, reserves **zero paid operations**, and does not certify provider health/capability. Separate edge limits should protect readiness from abuse.

Audit includes gateway correlation ID, credential ID, operation/route and safe outcome/rejection classes. Responses expose owned latency and logical provider/model identity, never upstream cookies/authentication/diagnostic headers, raw errors or reasoning content. No prompts are retained for gateway debugging. Local research artifacts continue their existing output contracts.

## Offline validation and limitations

```bash
python -m pytest -q tests/evaluator
```

Tests use temporary hash-only stores, generated fake tokens, ASGI/HTTPX mocks, an ephemeral loopback HTTP server and fake model/data upstreams. They cover encryption, authorization, quotas, no-cost readiness, session launch, governed same-Run recovery and no-switch credential denial. They do not constitute hosted penetration testing, TLS deployment certification, new paid research acceptance, or full Windows proof parity. `--allow-loopback` exists only for local fake-gateway development; never use it for distributed credentials.

[Security design](../architecture/EVALUATOR_CREDENTIAL_SECURITY.md) · [Evaluator Quickstart](EVALUATOR_QUICKSTART.md).
