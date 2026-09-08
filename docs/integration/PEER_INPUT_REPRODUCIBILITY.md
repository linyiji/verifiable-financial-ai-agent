# Peer model-input reproducibility

[简体中文](PEER_INPUT_REPRODUCIBILITY.zh-CN.md)

Repeated assembly of identical persisted Peer authority produced different
model inputs because newly constructed PeerCandidate/PeerSelectionDecision
objects carry clock-based created_at metadata. The model support projection
now omits only these assembly timestamps from candidates, selection_decisions
and selected_comparables. Domain objects and persisted task artifacts keep
their timestamps. Evidence observation dates and all business fields remain.

Focused validation: 29 tests passed, including a new clock-independence and
field-preservation test. Repeated construction from immutable historical R3
also produced identical contexts after repair. Ruff and diff checks pass.

Owner-authorized prospective transport probe: one MiMo Peer request, frozen
at 14,462 bytes, SHA-256 c15d911c9a8b0fbbf51ce1e32d700fce2738d4a81ea06661188d971a64596d3b.
Current system-proxy path returned HTTP/1.1 200 and complete body in 14.872s.
Typed validation passed; a conservative probe-only semantic gate failed.
That gate is heuristic and may reject valid numeric reformattings or counts;
it is not evidence by itself of a production output-contract defect.
No Stage B or retries. Proxy causality remains unproven.

No provider transport policy changes, production Runs, AgentOutputs, or
Memory writes. Historical request preimage was not retained: this experiment
does not claim exact replay of the historical request. Safe metadata lives in
artifacts/model_transport_discriminating_probe; raw prompts/responses do not.
