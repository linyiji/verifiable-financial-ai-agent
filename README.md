<img src="docs/product/logo.png" alt="Verifiable Financial Agent orange logo" width="76">

# Verifiable Financial Agent

[简体中文](README.zh-CN.md)

Current Alpha capability scope: Bocha Web Search evidence/discovery support only.
The Owner-authorized FMP pool contains **four distinct keys**; a fifth key is not
required. Provider credentials are private and are never included in this repository.

Autonomous financial research that can execute, verify, recover, remember, and improve.

Local Deployable Alpha · Controlled Alpha Ready

Multi-Agent Research · Verifiable Results · Adaptive Recovery · Research Memory

[Evaluate / Run locally](docs/deployment/EVALUATOR_QUICKSTART.md) · [Product walkthrough](docs/product/PRODUCT_WALKTHROUGH.md)

[能用](#能用--make-it-useful) · [敢用](#敢用--make-it-trustworthy) · [越用越好](#越用越好--make-it-better-with-use)

## 能用 · Make It Useful

Give the Agent a research objective; it organizes and executes the research.

Research Object → Research Goal → AI Research Scheme → Research Lead + Specialist Agents → Dynamic Research Path → Financial Research Result.

Review the Scheme before execution. Follow specialist work, self-correction and replanning in the real interface—not just a final block of generated prose.

**Agent handles uncertainty; code executes certainty.** The Agent interprets the goal, judges evidence, decomposes tasks, analyzes risk and decides when to correct, replan or request bounded recovery. It decides what needs analysis or calculation. Supported deterministic capabilities define how authoritative calculations execute: typed inputs, period/unit checks, versioned calculation records and Financial Review linkage. The generated-capability workflow can build and validate a scoped missing calculation capability; it is not a universal Formula Registry or production-wide capability certification.

## 敢用 · Make It Trustworthy

Inspect the supported assurance chain: Claim → Evidence → Calculation → Financial Review → Proof → Execution Record.

Deterministic calculations, independent financial checks, bounded required proofs and exact execution identities make supported results inspectable. Proofs cover defined computations, not the truth of every statement or suitability of an investment.

Provider / Model Failure → Recovery Decision → Policy Gate → Same-Run Recovery.

Recovery is bounded and auditable. Report ↔ Execution trace works where exact persisted mappings exist; source and contribution coverage remains **partial**. A complete Claim Trace drawer is not available.

Four separate trust layers make the boundary explicit:

- Result verifiability: Claim → Evidence → Calculation → Review.
- Deterministic execution: Typed Inputs → deterministic code → Calculation Record → Review → bounded Proof where supported.
- Execution auditability: Task → Agent → Input → Observable Process → Structured Output → available Report Contribution mapping. Observable records do not expose hidden chain-of-thought.
- Process conformance: Initial Plan + authorized Correction / Replan / Recovery → Actual Execution. The product records initial/actual graph versions, corrections, replan approvals, recovery decisions, policy gates, attempts and Review / Proof / Release transitions.

**The path may change; the rules for changing it may not be bypassed.** Current RISC Zero proofs cover bounded computations. ZK Agent Execution Conformance Proof is a planned next trust layer: commit approved graph/policy transitions, then prove that actions and state transitions match the initial plan plus authorized changes. It does not currently prove the entire Agent path and would not prove private model reasoning.

## 越用越好 · Make It Better With Use

The research-memory loop is implemented today:

Released Research → Research Memory → Incremental Research → Refresh / Revalidate / Prevent → New Released Research → Memory v2 → Base vs Current.

History helps determine what must be updated, independently reverified, or prevented from recurring. A new result does not inherit the previous Run's approval. This is durable research reuse, **not model training or a claim that investment outcomes automatically improve**.

The intelligence flywheel has three stages:

| Stage | Status and role |
| --- | --- |
| Phase 5 — Research Memory / Incremental Research | Implemented. Compact governed prior context changes the next plan through Refresh / Revalidate / Prevent, reducing repeated research; released Memory v2 supports Base vs Current. |
| Phase 6 — Adaptive Runtime → Full Evaluation | Attempts, failure classification, Provider Detector, Recovery Supervisor, Policy Gate, RecoveryBudget and same-Run recovery are implemented, with accepted live-run evidence. Full TaskProfile × ProviderRoute × Model Evaluation → POT → governed Provider / Model / Context / Path recommendations is next; learned routing is not implemented. |
| Phase 7 — Capability Certification | Planned. Versioned reusable capabilities, repeated-success evidence and human/policy approval would govern global deterministic/Agent capability reuse. Current scoped capability validation is not this production certification system. |

For comparable repeated research, the optimization target is lower marginal input tokens, unnecessary output tokens, latency, provider cost, failed attempts and recovery overhead. Research Memory and Incremental Research provide today's base; generalized context compression, progressive retrieval, graph optimization, evidence-driven route selection and certified capability reuse are next layers. No percentage savings are claimed. The goal is to reduce marginal research cost while preserving required Financial Review, Proof Policy, Evidence Coverage, Safety and Release Gates.

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

Provider/model recovery supports bounded dynamic substitution within the policy-authorized model set; preferred and actual models are recorded separately, including MiMo Provider / mimo-v2.5 authority.

An owned failure classification produces a recovery proposal; an independent policy checks exact identity, route authority, capability evidence and remaining budgets before another invocation. Recovery does not regenerate the Scheme, change the knowledge base, or silently create another Run.

Registered routes: `teamorouter-sol`, `teamorouter-luna`, `mimo-direct`. Only configured, permitted candidates can execute. [Architecture and limits](docs/architecture/ADAPTIVE_RUNTIME.md).

## Evaluate / Run Locally

**Investors and testers should currently use BYOK direct-provider evaluation.** MiMo, TeamoRouter and FMP integrations are built in; usable API keys are not included in the public package. Use your own keys or test keys supplied privately by the Owner. Start with [BYOK setup](docs/deployment/ADVANCED_INSTALLATION.md).

The separate gateway-based installer source foundation uses these commands from an unpacked source package. It requires a deployed Owner gateway and `.vfaeval` bundle; it is not a one-command BYOK launcher:

Windows (PowerShell):
```powershell
& .\scripts\install-evaluator.ps1
```

macOS (Terminal):
```bash
bash scripts/install-evaluator.sh
```

For that installer, subsequent startup is `vfa start`. Public installer delivery remains **PUBLICATION_REQUIRED**, and the real Owner gateway is not deployed. This blocks gateway-based zero-config evaluation, not independently configured BYOK. Standard mode retains all proof/release gates; full-proof workflows require the advanced environment.

[Guided installation / troubleshooting](docs/deployment/INSTALL_EVALUATOR.md) · [Advanced / BYOK](docs/deployment/ADVANCED_INSTALLATION.md) · [Evaluator Gateway](docs/deployment/EVALUATOR_GATEWAY.md)

## Architecture & Validation

[System architecture](docs/architecture/SYSTEM_ARCHITECTURE.md) · [Research Memory](docs/architecture/RESEARCH_MEMORY.md) · [Product acceptance](docs/validation/PRODUCT_ACCEPTANCE.md) · [Recovery acceptance](docs/validation/ADAPTIVE_RECOVERY_ACCEPTANCE.md) · [Deployment acceptance](docs/validation/LOCAL_DEPLOYMENT_ACCEPTANCE.md).

## Current Status / Roadmap

**LOCAL DEPLOYABLE = YES · CONTROLLED ALPHA READY = YES**

Controlled Alpha means facilitated evaluation—not validated broad user adoption. This is not public SaaS, enterprise-ready security, Auth/RBAC/SSO, complete provenance coverage or investment advice.

Next: Evaluation → POT → Evidence-driven Provider / Model Selection. Full Evaluation/POT is future work; Research Memory and Incremental Research are already implemented.

[Product status](docs/product/PRODUCT_STATUS.md) · [License decision pending](docs/LEGAL_AND_LICENSE_STATUS.md).

## Recognition

🥉 **Bronze Award — AIx Origin Summit Hong Kong · Flux Track**

An early external validation milestone, confirmed by the Owner. The product's identity and current capability boundaries remain those described above.

[Recognition record](docs/recognition/AIX_ORIGIN_SUMMIT.md).
