<img src="docs/product/logo.png" alt="Verifiable Financial Agent orange logo" width="76">

# Verifiable Financial Agent

Autonomous financial research that can execute, verify, recover, remember, and improve.

Local Deployable Alpha · Controlled Alpha Ready

Multi-Agent Research · Verifiable Results · Adaptive Recovery · Research Memory

[简体中文](README.zh-CN.md) · [Evaluate / Run locally](docs/deployment/EVALUATOR_QUICKSTART.md) · [Product walkthrough](docs/product/PRODUCT_WALKTHROUGH.md)

## 能用 · Make It Useful

Give the Agent a research objective; it organizes and executes the research.

Research Object → Research Goal → AI Research Scheme → Research Lead + Specialist Agents → Dynamic Research Path → Financial Research Result.

Review the Scheme before execution. Follow specialist work, self-correction and replanning in the real interface—not just a final block of generated prose.

## 敢用 · Make It Trustworthy

Inspect the supported assurance chain: Claim → Evidence → Calculation → Financial Review → Proof → Execution Record.

Deterministic calculations, independent financial checks, bounded required proofs and exact execution identities make supported results inspectable. Proofs cover defined computations, not the truth of every statement or suitability of an investment.

Provider / Model Failure → Recovery Decision → Policy Gate → Same-Run Recovery.

Recovery is bounded and auditable. Report ↔ Execution trace works where exact persisted mappings exist; source and contribution coverage remains **partial**. A complete Claim Trace drawer is not available.

## 越用越好 · Make It Better With Use

The research-memory loop is implemented today:

Released Research → Research Memory → Incremental Research → Refresh / Revalidate / Prevent → New Released Research → Memory v2 → Base vs Current.

History helps determine what must be updated, independently reverified, or prevented from recurring. A new result does not inherit the previous Run's approval. This is durable research reuse, **not model training or a claim that investment outcomes automatically improve**.

## Real Product Screenshots

Current local React product, real persisted research, accepted orange logo. No prototype or generated mockups.

### Autonomous research

![Autonomous research](docs/product/screenshots/autonomous-research.png)

### Financial review

![Financial review](docs/product/screenshots/financial-review.png)

### Adaptive recovery

![Adaptive recovery](docs/product/screenshots/adaptive-recovery.png)

### Research memory

![Research memory](docs/product/screenshots/research-memory.png)

### Base vs Current

![Base vs Current](docs/product/screenshots/base-vs-current.png)

[Capture provenance and limitations](docs/product/screenshots/PROVENANCE.md). These are historical accepted results, not a promise that each new provider call succeeds.

## What Works Today

- Research Objects, goals, model-backed Schemes and confirmed Run admission.
- Research Lead and specialist Agents; dynamic task graphs, self-correction and controlled replan.
- Bounded provider/model recovery within the same Run.
- Live financial-data integration, deterministic calculation, financial review and bounded required proof.
- Financial reports and available Report ↔ Execution trace.
- Research Memory v2, Incremental Research and Base vs Current comparison.
- PostgreSQL persistence and a real React/TypeScript interface.

[Capability boundaries](docs/product/PRODUCT_STATUS.md) distinguish available, partial and unimplemented features.

## Adaptive Runtime

An owned failure classification produces a recovery proposal; an independent policy checks exact identity, route authority, capability evidence and remaining budgets before another invocation. Recovery does not regenerate the Scheme, change the knowledge base, or silently create another Run.

Registered routes: `teamorouter-sol`, `teamorouter-luna`, `mimo-direct`. Only configured, permitted candidates can execute. [Architecture and limits](docs/architecture/ADAPTIVE_RUNTIME.md).

## Evaluate / Run Locally

**BYOK—Bring Your Own Key**, or owner-issued temporary provider credentials shared out of band. Commercial billing is not part of Local Deployable Alpha.

Start with the [Evaluator Quickstart](docs/deployment/EVALUATOR_QUICKSTART.md), [local deployment guide](docs/deployment/LOCAL_DEPLOYMENT.md), and [safe configuration template](.env.example).

Python 3.11, Node.js 24, PostgreSQL and financial-data/model credentials are required. The full required-proof path also needs the RISC Zero toolchain; generated-capability validation needs Docker. The repository does not bundle the owner's database, private runtime artifacts or keys. Fresh local runs can incur provider costs.

## Architecture & Validation

[System architecture](docs/architecture/SYSTEM_ARCHITECTURE.md) · [Research Memory](docs/architecture/RESEARCH_MEMORY.md) · [Product acceptance](docs/validation/PRODUCT_ACCEPTANCE.md) · [Recovery acceptance](docs/validation/ADAPTIVE_RECOVERY_ACCEPTANCE.md) · [Deployment acceptance](docs/validation/LOCAL_DEPLOYMENT_ACCEPTANCE.md).

## Current Status / Roadmap

**LOCAL DEPLOYABLE = YES · CONTROLLED ALPHA READY = YES**

Controlled Alpha means facilitated evaluation—not validated broad user adoption. This is not public SaaS, enterprise-ready security, Auth/RBAC/SSO, complete provenance coverage or investment advice.

Next: Evaluation → POT → Evidence-driven Provider / Model Selection. Full Evaluation/POT is future work; Research Memory and Incremental Research are already implemented.

[Product status](docs/product/PRODUCT_STATUS.md) · [License decision pending](docs/LEGAL_AND_LICENSE_STATUS.md).

## Recognition

An early external demonstration milestone: the repository records a Flux · 流境 submission for AIx Origin Summit Hong Kong. Award level and official track spelling are pending authoritative confirmation; no Bronze Award is claimed here.

[Recognition record](docs/recognition/AIX_ORIGIN_SUMMIT.md).
