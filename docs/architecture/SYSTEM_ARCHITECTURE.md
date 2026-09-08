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
