# Verifiable Financial AI Agent

**Autonomous Research · Verifiable Results · Auditable Execution**

Flux · 流境 — AIx Origin Summit Hong Kong

**Primary Track: C · Verifiable AI Inference Audit / Financial Agent**

[English](./README.md) | [简体中文](./README.zh-CN.md)

📄 [Final Report — Flux Competition Submission](./docs/submission/Verifiable_Financial_AI_Agent_Flux_Final_Report.pdf)

Verifiable Financial AI Agent is a multi-agent financial research system that can autonomously plan and execute research, generate a real financial report, and trace report conclusions back to the exact AI execution records that produced them.

## Project Overview

The product turns a research object and goal into an approved research scheme, an executed multi-agent task graph, persisted specialist outputs, Research Lead synthesis, and a content-addressed HTML report. Report conclusions remain connected to their exact Run, Task, Agent output, execution event, and report contribution.

## Flux Track Fit

This is an AI × Fintech entry for **Flux · 流境, Primary Direction C**: verifiable AI inference audit / financial Agent.

- A real financial research task with AI as a load-bearing execution component
- Autonomous specialist and Research Lead execution
- Structured, persisted, auditable Agent outputs
- Real financial data with deterministic financial calculations
- Bidirectional Report ↔ Execution traceability
- A verification-friendly, locally reproducible competition path

Blockchain is not required for every research step. The system combines AI execution with evidence, deterministic computation, audit records, and bounded proof policy where applicable.

## Why This Matters

Conventional AI research often ends at generated prose. In financial work, a reviewer also needs to know which Agent performed the work, what safe inputs and observable actions were used, what structured output was persisted, and how that output contributed to the report. This project makes that lineage a product feature.

## Product Value

| Layer | Status | Product path |
| --- | --- | --- |
| **能用 · Autonomous Research** | Implemented | Research Object → Goal → AI Research Scheme → Confirm → Auto-start → Research Lead → Specialist Agents → Dynamic Research Path → Synthesis → Report |
| **敢用 · Verifiable & Auditable** | Competition minimum implemented | Report ↔ Agent Output ↔ Execution Record |
| **越用越好 · Evidence-driven Optimization** | **Roadmap / next stage** | Historical Runs → Evaluation → POT → Model Selection Candidate |

The broader assurance design is `Claim → Evidence → Calculation → Review → Proof`; it is distinct from the minimum accepted Demo and is applied only where the current capability and proof policy support it.

## What Works Today

- Create a Research Object and goal, generate an AI research scheme, confirm it, and auto-start a Run.
- Collect and normalize live FMP financial evidence.
- Execute provider-backed specialist Agents and a Research Lead through a dependency-aware runtime.
- Persist structured Agent outputs with exact Run and Task lineage.
- Apply task-local self-correction and Lead-controlled replan when needed.
- Synthesize research into a real, content-addressed HTML report.
- Open a report source contribution, inspect its observable execution, and return to the exact report anchor.
- Stream Run progress to the React/TypeScript interface through SSE.

## Accepted Competition Demo

| Acceptance check | Result |
| --- | --- |
| REAL AI RESEARCH | PASS |
| REAL SPECIALIST OUTPUTS | PASS |
| RESEARCH SYNTHESIS | PASS |
| REPORT GENERATION | PASS |
| HTML ARTIFACT | PASS |
| OPEN REPORT | PASS |
| REPORT SOURCE MAP | PASS |
| REPORT → EXECUTION | PASS |
| EXECUTION → REPORT | PASS |
| SAME RUN IDENTITY | PASS |
| CROSS RUN FALLBACK | 0 |
| FIXTURE FALLBACK | 0 |

| Accepted evidence | Identifier |
| --- | --- |
| Branch | `phase4` |
| Commit | `bc636762f0a89ba2313ab1f9e09df8b0db9f2f6b` |
| Tag | `flux-minimum-demo-2026-09-06` |
| Demo Run | `RUN-57aed683-75d6-4b47-acc6-a73053ea492e` |
| Report | `RESULT-RUN-57aed683-75d6-4b47-acc6-a73053ea492e` |
| Hero anchor | `metric-revenue-growth` |
| Hero actor | `fundamental_analyst` |
| Agent output | `AGOUT-9ab72a67-87e1-523a-a88f-1c4246a26330` |
| Execution event | `EVT-9dc4ef04-5617-4652-9510-61b9905274a0` |

These identifiers are immutable acceptance evidence, not hardcoded production lookup requirements. Runtime navigation resolves the identities of the Run being viewed.

## End-to-End Product Flow

```text
Research Object → Goal → AI Research Scheme → User Confirm → Auto-start
→ Initial Task Graph → Specialist Agents → Dynamic Execution
→ Research Lead Synthesis → HTML Financial Report
↔ Exact Observable Execution Record
```

## Multi-Agent Research

| Role | Responsibility |
| --- | --- |
| Research Lead | Plans the research and owns authoritative synthesis |
| Fundamental Analyst | Analyzes financial statements and operating performance |
| Peer Analyst | Builds and interprets comparable-company context |
| Research & News Analyst | Collects relevant company and market context |
| Valuation Analyst | Produces valuation analysis within available evidence |
| Risk Analyst | Identifies risks, limitations, and follow-up needs |

Specialist outputs are persisted with exact Run/Task lineage and consumed by Research Synthesis. Supporting execution services and deterministic capabilities are not described as Agents.

## Dynamic Research Path

```text
Initial Graph → Execution → Evidence or correction issue
→ Self-Correction first → Lead-controlled Replan where needed → Actual Graph
```

The runtime follows **Initial Plan First**, task-local **Self-Correction first**, and **Lead-controlled Replan**. Graph v1 records the initial plan; Graph v2 records an approved changed path when a Run actually needs one. Not every Run replans.

## Report ↔ Execution Trace

A conventional AI generates a report.

Verifiable Financial AI Agent lets the report point back to the exact AI execution that produced it.

```text
Financial Report
    ↓
Revenue Growth
    ↓
View Research Source
    ↓
Fundamental Analyst
    ↓
Exact Task
    ↓
Input → Observable Process → Structured Output
    ↓
Report Contribution
    ↓
Back to Report
```

**Observable Process only.** The execution detail exposes safe inputs, observable actions, structured output, identifiers, and the report contribution. It does **not** expose hidden chain-of-thought, raw prompts, provider payloads, or secrets.

## Technical Architecture

```text
React + TypeScript UI
        │ REST + SSE
        ▼
FastAPI product API
        │
PostgreSQL-backed runtime worker and dependency scheduler
        ├── Research Lead + Specialist Agents ── configured model provider
        ├── Evidence collection ──────────────── FMP
        ├── Deterministic financial capabilities
        ├── Review / proof policy ────────────── RISC Zero where bounded
        └── Content-addressed Agent and report artifacts
```

The API application lifespan starts the PostgreSQL-backed runtime worker; the competition composition does not require a separate scheduler process.

## Verifiability Design

The accepted minimum demonstrates `Report ↔ Agent Output ↔ Execution Record` on one exact Run. Each contribution can resolve its `run_id`, `task_id`, actor, `agent_output_id`, execution event/action, structured output, and report anchor.

The wider repository also models evidence gating, deterministic calculations, review, release, and proof policy. RISC Zero support proves bounded deterministic computation—such as the supported Revenue Growth workflow—not the objective truth of external data or every AI conclusion.

## Technology Stack

| Area | Current implementation |
| --- | --- |
| Backend | Python `>=3.11,<3.12`, FastAPI, Pydantic, SQLAlchemy, Alembic |
| Frontend | Node.js `>=24,<25`, React, TypeScript, Vite |
| Persistence | PostgreSQL; content-addressed local artifacts |
| Financial data | Financial Modeling Prep (FMP) |
| Model path | TeamoRouter / configured model provider; Mimo planner route supported by configuration |
| Runtime | Dependency scheduler, event-driven execution, checkpoints, SSE |
| Financial compute | Deterministic Python capability runtime |
| Verification | Review/release policy and bounded RISC Zero proof workflow |
| Observability | Optional Langfuse integration with redaction controls |

## Quickstart

Prerequisites: Python 3.11, Node.js 24, PostgreSQL, Docker for generated-capability validation, and the RISC Zero toolchain for the bounded proof workflow.

1. Install backend and frontend dependencies.

   ```bash
   python3.11 -m venv .venv
   source .venv/bin/activate
   python -m pip install -e '.[dev,postgres]'
   cd apps/web
   npm ci
   cd ../..
   ```

2. Create local configuration and supply your own PostgreSQL, FMP, and model-provider credentials.

   ```bash
   cp .env.example .env.local
   ```

3. Provision the PostgreSQL database named in `DATABASE_URL`, then migrate it and build the proof host.

   ```bash
   PYTHONPATH=. python scripts/postgresql_migrate.py
   ./zk/revenue_growth/build-host.sh
   ```

4. Start the backend. The runtime worker starts with the application.

   ```bash
   PYTHONPATH=. uvicorn apps.api.main:app --host 127.0.0.1 --port 8010
   ```

5. In another shell, start the frontend.

   ```bash
   cd apps/web
   npm exec vite -- --host 127.0.0.1 --port 4173
   ```

6. Open `http://127.0.0.1:4173`, create a Research Run, generate and confirm its scheme, and allow the Run to reach `RELEASED`.
7. Open the result, select **Revenue Growth → 查看研究来源**, inspect the exact execution detail, then select **返回报告** to return to the same Revenue Growth anchor.

Port 4173 targets the local API on port 8010 by default. `VITE_API_BASE_URL` can select another API origin.

## Configuration

Copy [`.env.example`](./.env.example) to the ignored `.env.local`. Configure names only; never commit real values.

| Purpose | Environment variable names |
| --- | --- |
| Database and storage | `DATABASE_URL`, `ARTIFACT_ROOT`, `WORKSPACE_ROOT` |
| Frontend API | `VITE_API_BASE_URL` |
| FMP | `FMP_API_KEY` or contiguous `FMP_API_KEY_1`…`FMP_API_KEY_N`, `FMP_BASE_URL` |
| TeamoRouter | `TEAMOROUTER_API_KEY`, `TEAMOROUTER_BASE_URL`, `TEAMOROUTER_MODEL`, `TEAMOROUTER_FALLBACK_MODEL` |
| Mimo planner route | `MIMO_API_KEY`, `MIMO_BASE_URL`, `MIMO_DATA_MODEL`, `MIMO_CHAT_MODEL` |
| Provider policy | `PLANNER_PREFERRED_PROVIDER`, `PLANNER_FALLBACK_PROVIDERS`, `LLM_PROVIDER` |
| Optional observability | `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL` |

## API / FMP Integration

The FastAPI product surface creates and confirms Runs, exposes current Run state and artifacts, and streams execution events over SSE. The FMP adapter includes credential selection, provider mapping, financial-statement collection, normalization, evidence handling, focused tests, controlled fixtures, and a read-only live NVDA smoke path. Most tests are deterministic and do not require live FMP access.

## Testing & Acceptance

The accepted GitHub-update gates all passed:

| Gate | Command | Result |
| --- | --- | --- |
| FMP focused | `.venv/bin/python -m pytest -q -p no:cacheprovider tests/unit/data/test_fmp_adapter.py tests/unit/data/test_live_fmp_integration.py tests/integration/live_fmp/test_nvda_evidence_calculation_flow.py tests/unit/data/test_peer_data_semantics.py tests/unit/application/test_evidence_semantics.py tests/integration/test_peer_selection_pipeline.py` | PASS |
| Agent focused | `.venv/bin/python -m pytest -q -p no:cacheprovider tests/integration/test_research_agent_runtime.py tests/unit/agentic/test_research_agent_outputs.py` | PASS |
| Report trace | `.venv/bin/python -m pytest -q -p no:cacheprovider tests/unit/adapters/test_finrobot_professional_reporting.py tests/phase4/backend_product/test_artifacts.py tests/phase4/backend_product/test_api_contract.py` | PASS |
| Typecheck | `cd apps/web && node_modules/.bin/tsc --noEmit -p tsconfig.json` | PASS |
| Production build | `cd apps/web && npm run build` | PASS |
| FMP live smoke | `.venv/bin/python tests/integration/live_fmp/run_nvda_vertical_slice.py` | PASS |

The live smoke requires configured FMP credentials; deterministic focused tests do not.

## Security / Compliance

- No real customer funds or unmasked personal financial data are required.
- External financial-data and model providers remain operational dependencies.
- This is research-support software, not a licensed securities service or investment guarantee.
- AI outputs can contain errors and uncertainty; traceability does not guarantee a conclusion.
- Secrets, raw provider payloads, prompts, and hidden chain-of-thought are excluded from report execution detail.
- Cryptographic proof, where used, proves bounded computation rather than the objective truth of external financial data.

## Reproducibility

Checkout the accepted tag to reproduce the code baseline:

```bash
git checkout flux-minimum-demo-2026-09-06
```

Use your own PostgreSQL, FMP, and model-provider configuration, then follow Quickstart. The accepted identifiers above document one real Demo execution; new Runs produce new identities and never depend on a cross-Run or fixture fallback in the competition path.

## Final Report

The complete competition narrative, architecture, acceptance evidence, and product framing are available in the [Flux Competition Final Report](./docs/submission/Verifiable_Financial_AI_Agent_Flux_Final_Report.pdf). See the short [submission manifest](./docs/submission/README.md) for immutable submission coordinates.

## Originality / Open Source Reuse

The system uses open-source and third-party infrastructure while keeping competition product work and integration boundaries explicit. See [Originality and Reuse](./docs/18_ORIGINALITY_AND_REUSE.md) for the authoritative disclosure; historical attribution documents remain intact.

## Current Limitations

- FMP data coverage and endpoint entitlements depend on the configured account.
- Model-provider availability and output quality remain external dependencies.
- Not every Run needs or performs a replan.
- The accepted minimum proves report-to-execution lineage; broader review and proof surfaces remain capability- and policy-dependent.
- The system supports financial research and audit, not autonomous custody, trading, or guaranteed investment decisions.
- Historical-run evaluation, POT, and automated model selection are not current production auto-evolution features.

## Roadmap

| Stage | Scope |
| --- | --- |
| **Current** | Verifiable Autonomous Research |
| **Next** | Research Object Memory |
| **Then** | POT / Evaluation / Model Selection |
| **Later** | Capability Certification / Global Reuse |

Only the Current stage is represented as implemented competition functionality.

## Documentation

The README is the current product entry point. The existing [`docs/`](./docs/) package preserves architecture/design history and frozen decision records rather than current landing-page status.

- [Read First](./docs/00_READ_FIRST.md)
- [Architecture Decisions](./docs/03_ARCHITECTURE_DECISIONS_V1.md)
- [Backend Architecture](./docs/02_BACKEND_ARCHITECTURE_V1.md)
- [Originality and Reuse](./docs/18_ORIGINALITY_AND_REUSE.md)
- [Phase 4 documentation](./docs/phase4/)
- [Final Report submission](./docs/submission/README.md)
