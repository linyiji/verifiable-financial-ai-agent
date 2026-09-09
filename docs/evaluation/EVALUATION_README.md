# External Evaluation Snapshot

[简体中文](EVALUATION_README.zh-CN.md) · [Product Experience Reference](Verifiable_Financial_Agent_Product_Experience_Reference.html) · [Installation](../deployment/INSTALL_EVALUATOR.md)

Verifiable Financial Agent turns a reviewed research goal into an observable multi-agent research path, deterministic financial calculations, independent Financial Review, bounded Proof, a traceable result and reusable Research Memory. The product thesis is: useful research execution, trustworthy evidence and controls, and compounding governed research memory.

This is a Controlled Alpha snapshot. It is not production reliability certification, investment advice, or a claim that every task and upstream provider succeeds.

## Live-tested identity

| Item | Observed value |
| --- | --- |
| Live-tested runtime source | `bcd3525a0e4a194f37775477027d988ed224bb6e` |
| Live-tested source tree | `dabb2f42a17dda2dbc6a1fbf863162b4b89937bf` |
| Runtime image | `sha256:c45e2c1cf6cd2a0095be4b05cb14eaeaca28c0e7b9c952fbf919ff975455a451` |
| Run | `RUN-9d44e5e1-55a7-465d-a23e-991c63f7badf` |
| Durable terminal state | `RELEASED / SUCCESS`, sequence 261 |
| Review | `PASS`, 57/57 retained checks |
| Required Proof | `VERIFIED`, one retained Revenue Growth proof reference |
| Released result | `RESULT-RUN-9d44e5e1-55a7-465d-a23e-991c63f7badf` |
| HTML report | `RPT-HTML-c8f1fcdd81fe80758523` |
| Canonical execution record | `CER-RUN-9d44e5e1-55a7-465d-a23e-991c63f7badf` |
| New Research Memory projection | `NOT_OBSERVED` in the retained safe snapshot |

The runtime was installed against fresh isolated PostgreSQL with no imported Run or Memory. Before admission, `vfa doctor` reported Database, Backend, Frontend, RISC Zero 3.0.6 Proof Runtime, governed Sandbox Runtime and Direct Registry READY. API and Sandbox Broker both matched the exact revision and digest above.

## A / B / C trace

- A — Research report: AVAILABLE; one safe report section, anchor and persisted source-contribution mapping were observed.
- B — Financial review: AVAILABLE; PASS with 57 retained PASS checks and exact ReleasedResult / execution-record binding.
- C — Execution record: AVAILABLE; 493 observable Run records were displayed in the accepted UI capture.
- Complete report contribution and Claim Trace coverage: `NOT_OBSERVED`; current mapping remains partial.

## Actual branches and model execution

- `evidence_collection`, `peer_analysis`, `research_news_analysis`, `valuation_analysis` and `report_synthesis`: COMPLETED.
- `fundamental_analysis` and `risk_analysis`: FAILED and preserved as real limitations; Release did not rewrite them as successes.
- Peer and news succeeded on MiMo `mimo-v2.5`. The generated FCF-margin capability succeeded on TeamoRouter `gpt-5.6-sol`. Valuation recovered from a Sol timeout to an actual `gpt-5.6-terra` execution.
- Synthesis observed Sol `PROVIDER_UNAVAILABLE`, Luna capability-check `READ_TIMEOUT`, Terra capability-check `PROVIDER_UNAVAILABLE`, then authorized MiMo `mimo-v2.5` success. Its budget was 4 provider calls, 3 capability checks and 300 seconds; checks and execution attempts were accounted independently.

## Known research and product limitations

- The UI surfaced five research limitation records. Their complete text was not exported into the retained safe projection, so the exact five strings are `NOT_OBSERVED`; the confirmed fallback Scheme explicitly records that it is conservative and does not infer custom goal-specific methods.
- The two failed specialist branches above constrain the released research. Users must read the displayed limitations and Review evidence rather than infer completeness from `RELEASED`.
- Report source/contribution mapping is partial; a complete Claim Trace drawer and PDF export are not implemented.
- Provider latency, quota and availability are external dependencies. Bounded recovery can still end in a known failure.
- Proof covers specified deterministic calculations, not every narrative claim, hidden model reasoning, or investment suitability.
- The governed Broker supports the bounded generated-capability contract, not arbitrary-code execution.
- macOS/Docker local installation is live-tested. Windows scripts are offline-tested; Windows clean-machine E2E is `NOT_OBSERVED`.
- The optional Owner gateway is not deployed. Direct encrypted credentials and native BYOK are independent of it.

## Install and evaluate

Docker Desktop is required and must be running. Privately receive `VFA-Investor-Access.vfacred`, place it at `<unpacked-product-root>/credentials/active.vfacred`, and run the first-install script from that unpacked root:

```bash
# macOS
bash scripts/install-evaluator.sh
```

```powershell
# Windows PowerShell
& .\scripts\install-evaluator.ps1
```

Then use `vfa start`, `vfa doctor`, and `vfa stop`. Startup is bound to the release manifest's immutable digest and exact revision; it fails closed instead of using an old `vfa-evaluator:source` image.

## Safe current screenshot

![Accepted Closure-9 NVDA Live](../product/screenshots/closure9-live-accepted.png)

This unretouched 1440 × 900 image is from the Run above. Older screenshots are separately identified in [screenshot provenance](../product/screenshots/PROVENANCE.md) and are not represented as the same execution.

Next exact action: `PHASE6A_POLICY_AND_RECOVERY_AUDIT` — not started.
