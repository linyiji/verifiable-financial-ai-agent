# Phase 4 VS01 acceptance gate

This directory is acceptance infrastructure only. It does not import or alter product behavior.
The frozen contract authority is verified before tests execute, and result files keep harness
readiness separate from the real integrated VS01 decision.

## Harness preparation

Use Python 3.11, the repository's declared PostgreSQL extra, PostgreSQL 16 client/server tools,
and Node 24. A clean Python/browser harness bootstrap is:

```sh
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev,postgres]'
psql --version  # must identify PostgreSQL 16.x
```

The browser package is lockfile-pinned. Bootstrap it once before invoking the runner:

```sh
cd acceptance/phase4/vs01/browser
npx --yes --package=node@24.8.0 --call "npm ci"
npx --yes --package=node@24.8.0 --call "npm run install:chromium"
cd ../../../..
```

Then, from the repository root:

```sh
PYTHONPATH=. python3.11 acceptance/phase4/vs01/run_vs01.py self-test \
  --output-dir acceptance/phase4/vs01/out/self-test
```

Expected preparation result:

```text
HARNESS_STATUS=READY
VS01_INTEGRATED_STATUS=NOT_RUN
```

Synthetic fixtures are used only inside the Python/Node harness self-tests. They can never satisfy
an integrated control or change `VS01_INTEGRATED_STATUS` to `PASS`.

## Parent integrated execution

After serially integrating A, B, C and this acceptance-only change, copy and review
`integrated-config.example.json`. Use two provider-supported real companies and replace the example
backend, frontend, migration, and C-owned SSE capture commands with the exact commands delivered by
their owners. Run B's documented lockfile install and production build command before this gate when
its serve command expects prebuilt output; X intentionally does not invent a frontend toolchain that
is absent from the frozen contract. Absence of that owner-supplied command is a blocking dependency,
not a reason to substitute a prototype. Supply the PostgreSQL administrative URL only through the
configured environment variable; never place it in JSON or a command argument.

```sh
export VS01_POSTGRES_ADMIN_URL='postgresql://<user>:<password>@<host>:<port>/<admin-db>'
PYTHONPATH=. python3.11 acceptance/phase4/vs01/run_vs01.py integrated \
  --config /absolute/path/to/reviewed-vs01-config.json \
  --output-dir acceptance/phase4/vs01/out/integrated
```

The runner:

1. verifies the revision-qualified contract receipts and all harness self-tests;
2. verifies PostgreSQL server major 16 and creates a random dedicated database;
3. migrates that database, launches and health-checks the real Product backend;
4. creates distinct A/B resources through X1, invokes the tracked C-owned real scenario driver in
   the same database/process/capture session, runs identity/error/SSE controls, then restarts the
   actual backend while preserving that database;
5. launches the two reviewed real frontend commands (one primary and one unavailable-backend
   boundary), admits a fresh nonterminal same-Object alternate Run for switch/recovery evidence,
   then runs the X2 Playwright journey under Node 24;
6. scans retained API response bodies/headers and SSE evidence, while Playwright scans the visible
   UI, serialized DOM, loaded source, network failures and browser errors for forbidden material;
   and
7. writes `PHASE4_VS01_ACCEPTANCE_RESULT.json` and `.md`, then drops only the generated database.

Any absent service, PostgreSQL version mismatch, mock/Demo command, missing required observation,
failed cleanup, dirty candidate (including untracked files), incomplete public-surface scan, or unexecuted required
control prevents integrated PASS. The malformed/unsupported derivatives are generated only from
digest-pinned real frames and are evaluated by the frozen consumer oracle; they are never served as
mock Product responses. Final PASS requires every applicable real capture, not only synthetic
self-tests.

## Runtime-bound real SSE scenario capture

Some recovery and dynamic cases cannot be honestly inferred from one happy-path stream. Parent/C
must provide the tracked driver named by `sse_scenario_capture`; the top-level runner invokes it only
after its isolated PostgreSQL 16 database and managed backend are live. The driver receives only a
gate-owned loopback capture-proxy origin and a fresh output path; it does not receive the direct
backend origin, database URL, existing Run IDs, process identity, or candidate/contract claims. The
proxy records immutable request/response bytes, exact headers, ordering, hashes, completion state,
and gate-issued capture IDs in a private ledger. Redirects and spoofed capture receipts fail closed.

The driver writes a bounded `phase4-vs01-capture-index/v1` document containing only one unique
gate-issued capture ID for each required projection/stream slot. It may use the gate-only
`X-VS01-Capture-Cut-After-Complete-Frames` request header to stop an SSE read at an audited complete
frame boundary. The runner independently resolves every ID against the sealed ledger, rejects
missing, duplicate, unused, direct, partial, or truncated evidence, derives admitted Run identities
from proxied Confirm traffic, and reconstructs the private full evidence document. Driver-authored
response bodies, headers, digests, candidate metadata, and binding claims are never accepted.

The capture index has this exact root and scenario inventory:

```json
{
  "schema_version": "phase4-vs01-capture-index/v1",
  "scenarios": {
    "event_inventory": {"streams": ["CAP-<48 uppercase hex>"]},
    "duplicate": {"before_projection": "CAP-...", "stream": "CAP-..."},
    "ordering_recovery": {"before_projection": "CAP-...", "stream": "CAP-...", "recovered_projection": "CAP-..."},
    "heartbeat": {"before_projection": "CAP-...", "stream": "CAP-..."},
    "terminal_failure": {"stream": "CAP-..."},
    "snapshot_race": {"before_projection": "CAP-...", "stream": "CAP-...", "after_projection": "CAP-..."},
    "sparse_graph_refresh": {"before_projection": "CAP-...", "stream": "CAP-...", "after_projection": "CAP-..."},
    "self_correction": {"before_projection": "CAP-...", "stream": "CAP-...", "after_projection": "CAP-..."},
    "replan_pending": {"before_projection": "CAP-...", "stream": "CAP-...", "after_projection": "CAP-..."},
    "replan_approved": {"before_projection": "CAP-...", "stream": "CAP-...", "after_projection": "CAP-..."}
  }
}
```

The placeholders are explanatory only. `event_inventory` must collectively contain all 47 supported
V1 event types. A label, driver-authored digest, or direct-backend observation earns no control
credit.

## Frontend API binding

The frozen contracts do not prescribe a runtime-config endpoint or frontend build system. The
scenario therefore carries two reviewed public API bases, and Playwright proves the actual
origin/path from its real request/response ledger before crediting the journey. For this gate, the
primary API base is exactly the runner-managed backend origin plus `/api`; the unavailable API base
is exactly the runner-verified closed origin plus `/api`. This closes unrelated-service evidence
without prescribing how the frontend stores or injects that public base. Both served frontends must
load real non-empty source and issue no fixture/Demo fallback responses. The browser computes hashes
over the source bytes it actually retrieves; it does not trust a self-reported build hash.

## Parent-only integration notes

No Parent-only file is changed here. Parent must provide any route/bootstrap/migration/frontend
registration needed by A/B/C and the real launch configuration. X supplies no root script or test
registration patch: the documented bootstrap plus exact runner command directly addresses the
isolated path.

Read `DEPENDENCIES_AND_FINDINGS.json` before integration. The frozen
`run.failed.failure_stage` field and exact 11-value addendum are enforced by X3.

The requested Git ref `phase4/vs01-acceptance` cannot coexist with the existing local/remote
`phase4` ref because Git cannot store one name as both a file and directory. The owner-authorized
collision-safe mapping is `p4-vs01-acceptance` and `origin/p4-vs01-acceptance`; the requested name is
retained in the machine-readable delivery receipt.
