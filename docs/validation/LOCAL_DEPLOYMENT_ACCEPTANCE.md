# Local deployment acceptance boundary

LOCAL DEPLOYABLE ALPHA = accepted existing local PostgreSQL + real API + React product. CONTROLLED ALPHA READY = facilitated evaluation readiness, not production SaaS.

For this repository preparation:
- Installation requirements, migration entry point, API/frontend commands, health route and CORS origins were checked against source.
- Evaluator MiMo Settings and explicit private-file authority are tested without network; no developer-private default file is required.
- Focused backend tests, frontend checks, typecheck and build are run locally with no provider/data calls.
- Current preparation results: 98 backend cases passed, 8 read-only Memory checks and 24 Object V2 checks passed; Node 24.20.0 typecheck/build passed. The same 98 backend cases also passed with the workflow's in-memory SQLite environment. Existing warnings: two library deprecations and the frontend bundle-size advisory.
- A fresh database migration, clean-machine proof-tool installation and end-to-end paid evaluator Run were **not executed** in this task. The quickstart is source-verified, not newly certified on every OS.

A fresh clone contains neither historical production data nor the exact artifact store; screenshots are evidence, not fixtures to serve as live output. Complete new-run release may require Docker, real proof host and paid provider/data entitlements.

[Quickstart](../deployment/EVALUATOR_QUICKSTART.md) · [Deployment details](../deployment/LOCAL_DEPLOYMENT.md).
