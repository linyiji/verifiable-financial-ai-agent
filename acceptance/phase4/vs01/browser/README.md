# Phase 4 VS01 frontend acceptance

This isolated package prepares the X2 browser gate for the frozen VS01 journey:

```text
Research Object -> Research Goal -> AI Research Scheme -> Confirm
-> automatic exact Run -> Run Workspace -> Research Path
```

The production-counting spec observes the real frontend, HTTP responses, and SSE requests. It never
uses `page.route`, response fulfilment, a service worker, a Demo data source, a direct store setter,
or a fabricated business payload. Synthetic values occur only in the Node harness self-tests.

## Commands

From this directory:

```sh
npm ci
npm run check
npm run install:chromium
VS01_FRONTEND_URL=http://127.0.0.1:4173 \
VS01_BROWSER_SCENARIO_FILE=/absolute/path/to/generated-scenario.json \
npm run test:real
```

`npm run check` executes the pure contract-oracle tests, audits the real spec for forbidden mocking,
and proves Playwright can collect the real suite without a running product. `test:real` is intentionally
strict: a missing or malformed scenario is a failure rather than a skip.

## Real scenario input

The Parent/X4 environment setup writes a non-secret JSON file outside the source tree. IDs must be
captured from the isolated PostgreSQL-backed setup, never inferred from labels:

```json
{
  "schemaVersion": "phase4-vs01-frontend-scenario/v1",
  "object": {
    "objectId": "OBJ-...",
    "symbol": "...",
    "companyName": "..."
  },
  "goalText": "...",
  "asOf": "2026-09-05",
  "missingRunId": "RUN-...-ABSENT",
  "foreign": {
    "objectId": "OBJ-B-...",
    "runId": "RUN-B-...",
    "taskId": "TASK-B-...",
    "sentinels": ["a B-only safe display sentinel"]
  },
  "backendUnavailableFrontendUrl": "http://127.0.0.1:4174"
}
```

The second frontend URL must serve the same production build while its configured backend is
unreachable. This is a launch-time composition, not a Playwright network mock. The foreign resources
must be valid, distinct resources created through the real product path.

## Observable selector contract

Controls are located by accessible role/name first. Exact opaque identities require stable,
presentation-neutral DOM hooks so the browser can compare Backend truth with the rendered state:

| Hook | Required observable identity |
|---|---|
| `research-object-option` | `data-object-id` |
| `scheme-preview` | `data-object-id`, `data-goal-id`, `data-scheme-id`, `data-draft-id` |
| `confirm-run` | accessible button name equivalent to Confirm/Start and busy/disabled state |
| `run-workspace` | `data-run-id`, `data-object-id`, `data-goal-id`, `data-scheme-id` |
| `research-path` | exact current `data-run-id` |
| `research-task` | `data-run-id`, `data-task-id` for every projected Task |
| `typed-error` | `data-error-code`, and `data-resource-id` when supplied |
| `identity-quarantine` | `data-reason`, original route/resource identity |

These are acceptance observables, not access to private reducer state. If B does not expose equivalent
accessible text/attributes, Parent must apply the selector semantic proposal during serial integration.

## Frozen authority

- Freeze promotion: `764d76132cfac13d47125e031b280b7894eb249f:docs/integration/FINAL_CONTRACT_FREEZE_PROMOTION.json`
- V17 R2 canonical SHA-256: `fc184034e448e85190aa4cfd92b89e90b9f258307632920daa8d8cd73c600c19`
- Phase 4 contract-set SHA-256: `0bf6c824d553847fa129a429715aedc36a30601a97421f4447cdd3f6d6a81741`
- Primary gates: `P4-E2E-009`, `017..026`, `065..075`, `088`, and `P4-ID-001..005`, `023`, `025..027`.
