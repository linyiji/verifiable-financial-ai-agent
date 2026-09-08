# Explicit Specialist availability routes

[简体中文](SPECIALIST_PROFILE_ROUTES.zh-CN.md)

Owner-approved Phase 5B configuration overrides only peer_analysis and
research_news_analysis to mimo-direct / mimo-v2.5. Unlisted profiles retain
the existing provider object; Fundamental is unchanged. This is static
composition, not ranking, global failover or learned routing.

Settings.specialist_provider_routes resolves through the existing provider
route factory and is injected into the shared Agent registry. Task semantics
remain provider-independent. Unknown task profiles/routes fail closed;
multi-profile Agents require one consistent configured provider. All selected
credentials join the existing telemetry/artifact forbidden-value set.

Both exact-R3 Specialist capability gates passed once on current transport,
with safe parsed typed results retained locally. Peer: 15.689s, 4992 input /
528 output tokens. Research/News: 6.951s, 869 / 193 tokens. No extra numeric
token heuristic. No capability retries or transport-policy changes.

Pre-admission regression checkpoint: 134 focused tests PASS, including
isolated-schema PostgreSQL memory/reexecution tests, Agent identity binding,
route isolation, strict output validation, and input determinism. R4 release
and Phase 5 completion are separate gates, not asserted by this checkpoint.
