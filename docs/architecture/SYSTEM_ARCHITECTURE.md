# System architecture

[简体中文](SYSTEM_ARCHITECTURE.zh-CN.md)

React/TypeScript interface → FastAPI product API → application/domain contracts → dependency-aware runtime → financial-data/model/proof adapters → PostgreSQL and verified artifact stores.

- Object + Goal define the question. A persisted Scheme records confirmed research intent.
- Planned Graph and Actual Graph distinguish intended work from observed execution and approved changes.
- Research Lead and specialists produce structured outputs bound to Run/Task/actor and exact artifact references.
- Financial evidence feeds deterministic calculation; independent review and bounded proof gates determine release eligibility.
- Released results become typed Research Memory and a versioned Current Research View.
- Recovery wraps a bounded specialist invocation, not the complete research workflow.

## Authority boundaries

PostgreSQL domain/runtime records and verified artifact references are authoritative. The projection cache is derived, not research truth. Ordinary get_projection computes in memory with no upsert or commit; explicit materialize_projection remains a separate write operation. generated_at is response-generation metadata, not a research fact.

Run identity, confirmed Scheme identity and knowledge-base lineage remain fixed during recovery. A future reexecution has a new Run and an explicit execution predecessor; it does not resurrect a failed Run or overload base_run_id.

No hidden chain-of-thought is exposed. Public execution traces describe declared inputs, observed actions, outputs, checks and policy decisions.

[API composition](../../apps/api/main.py) · [Backend/read seam](../../src/phase4_product/postgresql_backend.py) · [Adaptive Runtime](ADAPTIVE_RUNTIME.md) · [Memory](RESEARCH_MEMORY.md).

## Independent financial branches and default object

Independent financial analyses run concurrently; a data-shortfall limitation does not block findings without that dependency. The financial extension bounds concurrency at three branches; not every Agent Task is fully parallel. Each validated calculation is persisted independently. Missing inputs produce INSUFFICIENT_DATA, no number and no dependent claim; genuine execution errors still fail. A Task may complete with structured limitations.

Technical branches in the general preset are SUPPORTING; canonical capability IDs explicitly listed in Scheme.calculation_requirements are REQUIRED. Existing full-formula Financial Review / Proof / Release controls remain unchanged: task continuation does not authorize release, and missing formulas can still block Release. Task details show branch status and available/required input counts. This change has not yet earned new-version host publication acceptance; Alpha 2 must not be described as published.

After PostgreSQL migration, product API startup idempotently creates an empty NVIDIA / NVDA Research Object, preserving any existing object with that ticker. No Run, Scheme, evidence, report or Research Memory is seeded and no provider is called. BYOK / Owner gateway credential and deployment boundaries are unchanged.
