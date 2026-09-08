# Phase 3 Planner Provider Router Remediation

[简体中文](PHASE3_PLANNER_PROVIDER_ROUTER_REMEDIATION.zh-CN.md)

## Disposition

Candidate `38f66c603d61097005b3cf961dc93948bfceba83` and tree
`6a520e457dce199454d86ff2968da79cc8f35072` remain immutable historical state
with disposition `PRE_AUTHORITATIVE_BLOCKED_BY_PROVIDER_CAPABILITY`.

This remediation creates a new candidate because the prior implementation
truthfully supported only TeamoRouter. It does not change Phase 3 financial,
review, proof, DTO, or RuntimeEvent contracts, and it introduces no migration.
The expected migration head remains `20260904_0006`.

## Governed provider policy

The internal `PlannerProviderRouter` owns the provider preference policy:

1. `mimo` is the preferred provider.
2. `teamorouter` is the secondary provider.
3. Unknown providers fail closed.
4. Probing stops when the first provider passes its owned planner preflight.
5. The selected provider and exact model are locked before Research Run
   creation. Mid-Run switching is disabled.

Both provider adapters normalize through the same owned structured-output
boundary. Provider-specific response bodies remain inside that boundary. Safe
selection evidence contains provider/model identifiers, policy, reason,
fallback status, health time, and safe failure classifications only.

## Runtime configuration and secret handling

MiMo configuration is supplied only through external runtime variables:
`MIMO_API_KEY`, `MIMO_BASE_URL`, `MIMO_CHAT_MODEL`, and `MIMO_DATA_MODEL`.
The repository contains no credential value. TeamoRouter remains configured by
its existing external variables.

The acceptance runner includes every configured provider credential in both
the local artifact sentinel scan and Langfuse recursive redaction audit. The
FMP credential is bound by authorized alias in acceptance evidence; its value
is never recorded. Provider/model selection evidence is attached to the root
trace and the acceptance summary.

## Authoritative qualification rule

External FMP and planner preflights are required against the clean new
candidate before invoking the runner. The runner independently repeats two
consecutive owned planner probes in governed order, locks the first healthy
provider/model, and uses that same identity for scheme generation, Lead
planning, and Generated Capability construction. Provider loss or identity
drift after selection fails the Run; it never triggers silent failover.
