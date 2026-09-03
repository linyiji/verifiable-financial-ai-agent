# 12 — Open-source Integration & Reuse V1

Verified / reviewed on 2026-09-03.

## 1. FinRobot

Repository:

https://github.com/AI4Finance-Foundation/FinRobot

Current project usage:

> Embedded Financial Runtime / Capability Source.

Do not use its fixed equity pipeline as our main Orchestrator.

Recommended integration:

```text
Agent
→ Skill
→ Capability Registry
→ FinRobot Adapter
→ FinRobot source function
```

Current baseline already discussed for pinning:

`d221910096de87579b02f8f0674652bf1a175f51`

Preferred layout:

```text
third_party/
└── FinRobot/   # pinned submodule
```

Reuse candidates:

- financial_data_processor
- FMP connector logic
- peer aggregation
- growth / margins
- technical indicators
- charts
- HTML / PDF renderers

Replace / wrap carefully:

- direct LLM section generator
- fixed pipeline orchestration
- simplified valuation logic
- report-time data refetch patterns

### Python version

FinRobot `setup.py` currently declares Python `>=3.10,<3.12`, so Python 3.11 is the safest shared MVP runtime.

### License / NOTICE warning

Current repository README / NOTICE identify the project as Apache-2.0 and include trademark / NOTICE obligations. A `setup.py` metadata field still says MIT.

Treat this as a repository metadata inconsistency.

Before any redistribution / commercial release:

1. inspect the checked-out `LICENSE`
2. preserve `NOTICE`
3. follow current trademark policy
4. do not use “FinRobot” as our product name
5. document exact reused source/version

For the hackathon, keep attribution and the pinned baseline.

---

## 2. Langfuse

Docs:

https://langfuse.com/docs/observability/sdk/overview

Repository:

https://github.com/langfuse/langfuse

Current official SDK line is OpenTelemetry-based.

Role:

> Runtime observability.

Implementation:

```text
TraceAdapter
├── LangfuseTraceAdapter
└── NoopTraceAdapter
```

Trace errors must not break application execution.

Instrument:

- run
- planning
- agent
- skill
- tool
- calculation
- correction
- replan
- review
- proof
- render

Langfuse is not Canonical Execution Record.

---

## 3. Microsoft RD-Agent

Repository:

https://github.com/microsoft/RD-Agent

Role:

> Architecture Reference Only for MVP.

Official project is designed for R&D-style research/development and primarily uses Docker for code execution in many scenarios.

Borrow:

```text
Research
→ Develop
→ Experiment
→ Feedback
→ Iterate
```

Our mapping:

```text
Capability Gap
→ Requirement
→ Code Builder
→ Sandbox
→ Tests
→ Financial Validation
→ Feedback / Fix
→ TASK_APPROVED
```

Do not import RD-Agent as the main Runtime unless a later implementation review proves it materially reduces work without compromising our architecture.

---

## 4. RISC Zero

Repository:

https://github.com/risc0/risc0

Docs:

https://dev.risczero.com/

Role:

> ZK execution proof provider.

RISC Zero proves correct execution of a known program in zkVM and yields a verifiable receipt.

MVP:

- one small deterministic proof
- do not prove full LLM
- verify receipt before Release

Suggested boundary:

```text
Python ProofPolicy
→ RiscZeroAdapter
→ Rust host / guest
→ Receipt
→ Verifier
```

Pin a released version, not the development `main` branch.

---

## 5. MCP Python SDK

Official docs:

https://py.sdk.modelcontextprotocol.io/

Official repository:

https://github.com/modelcontextprotocol/python-sdk

Current stable Python SDK docs describe Tools, Resources, Prompts and standard transports.

Role:

> Optional standardized Tool / Resource protocol.

MVP:

- Native internal financial capabilities stay Native
- MCP backend interface exists
- no forced MCP wrapping of every Python function

Future:

- Local files
- Desktop runtime
- SEC
- Bloomberg / enterprise data
- external tools
- third-party agents

---

## 6. FMP

Role:

> MVP default financial data provider.

Data must still pass our Evidence Layer.

Store provider metadata and snapshot refs.

Commercial / display licensing must be checked separately before production distribution.

---

## 7. Originality boundary

Third-party:

- FinRobot source capabilities
- Langfuse observability
- RISC Zero proof infrastructure
- RD-Agent design reference
- MCP protocol / SDK

Our product implementation:

- Object-centric state
- Goal → AI Scheme
- Research Lead Planner
- Planned / Actual graph
- Dynamic Runtime
- Self-Correction
- Controlled Replanning
- Financial evidence hard gate
- Calculation Record
- Capability Registry
- Generated financial capability lifecycle
- Canonical Execution Record
- Review / Proof / Release composition
- B/C dual review projection
- Object writeback
- comparison
- POT evaluation design
