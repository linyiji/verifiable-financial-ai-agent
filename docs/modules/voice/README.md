# VeFin Voice

[简体中文](README.zh-CN.md)

**VeFin's reusable voice communication module.** It connects user speech, task context, registered knowledge and controlled dialogue to spoken responses, while preserving sources, task state, constraints and delivery records.

**Current availability:** This PR synchronizes actual voice source, required dependencies, offline checks and module navigation. R8 passed a bounded local RTC consultation and human listening review. This publication performs offline checks only; it does not rerun ASR, LLM, TTS or RTC. The research installer does not enable voice, and no standalone voice distribution, hosted API or production authentication is provided.

## What the module does

| Responsibility | Role |
| --- | --- |
| Speech and transport | Receive speech over RTC, obtain an ASR transcript, synthesize an accepted response and track client audio delivery. |
| Dialogue and guidance | Answer supported questions, ask for necessary information and stop when the user or task requires it. |
| External Skill and communication configuration | Load a task method and selected persona/policy; keep style separate from facts, permissions and task state. |
| Knowledge and source handling | Use registered applicable knowledge, retain source references and distinguish known facts, user statements, unknowns and technical failures. |
| Task continuity | Carry accepted facts, corrections, independent prohibitions and pending extraction across turns. Noncritical missing fields can remain pending while an independent answer is delivered. |
| Controlled output | The application accepts field proposals and freezes a reply plan before expression. Response acceptance precedes TTS; generation, publication and client receipt are separate records. |

Typical flow: RTC input → ASR → original VoiceDialogue / KnowledgePort → Skill and task state → understanding proposals → application reply plan → natural expression → acceptance / renderer → TTS → RTC client.

The module's value is a complete, stateful communication loop. Speech recognition and synthesis are adapters within that loop.

## Responsibilities shared with VeFin

| Component | Owns |
| --- | --- |
| Voice module | Listening, conversation organization, necessary guidance, spoken delivery and communication outcomes. |
| Business capability / Port | Authoritative records, verification rules, query results and actual business receipts. |
| Harness / Runtime | Allowed capabilities, authorization, budgets, cancellation, execution identity and persistence boundaries. |
| Skill | Reusable task method and references; it does not grant tool permissions. |
| Persona / policy | Expression style, initiative, depth and verbosity; these do not alter facts or authority. |

A consultation marked `COMPLETED` is not a completed payment, account change or human transfer. Without a real receiver, a human-follow-up request remains `REQUEST_RECORDED_NO_RECEIVER`.

A future business integration can supply a task goal, scoped context, registered knowledge and authorized tool Ports, and receive communication outcomes with state and evidence. This is the intended integration boundary, **not a published callable API contract**. Transaction reconciliation and evidence collection are candidate consumers; those backend integrations were not part of R8.

## Repository placement decision

**Keep the module in the existing VeFin repository with a distinct logical boundary. Do not create a separate repository now.**

- This is a component of VeFin that uses the application's dialogue, knowledge, journal and runtime boundaries.
- Keep one implementation and one acceptance history. Do not duplicate shared state, authority or adapters in a new repository.
- This documentation lives at `docs/modules/voice/`. It is not an empty runtime package or an instruction to move working code.
- The actual tested source is synchronized into the existing application / adapter / API organization in this PR. Package and API boundaries can be extracted when actual consumers and dependencies justify independent releases.
- Reconsider a separate repository when the implementation can be installed and tested independently, its contracts and dependencies are stable, and there is a concrete independent distribution requirement.

Logical modularity is useful now; an independent repository is a later distribution choice. Existing repository licensing remains subject to the [license decision](../../LEGAL_AND_LICENSE_STATUS.md).

## R8 acceptance snapshot

**Evidence basis:** the R8 report, executed-file manifest, current-result receipt and confirmed human feedback were read on the Owner machine. This is a public summary of that local result, not a reproduction from this GitHub checkout. Raw transcripts, recordings, credentials, private profiles and billing records are not published by this update.

| Item | Reported result / boundary |
| --- | --- |
| Tested task | Prudential Hong Kong payment-account public-entry consultation; no customer account query, submission, modification or actual human transfer. |
| Configuration | `0.3.0/v3`; `efficient-partner / goal-led / core / concise`. No persona/policy switching in this RTC run. |
| Final execution | One fresh two-turn session; 9/9 response segments delivered to the RTC client. Three earlier failed sessions remain separate. |
| Task state | User month accepted as `UNKNOWN`, year `null`; consultation `COMPLETED`. Earlier sessions' pending records remain unchanged. |
| Dialogue processing | 2.459 s / 2.509 s within the original 8 s dialogue deadline. These are not end-to-end speech playback times or p95 measurements. |
| End of speech → first client audio | 6.266 s / 4.836 s. |
| Listening review | Owner confirmed clear, complete Cantonese and no obvious clipping, truncation or repeated playback. |
| Strict waveform checks | 5 passed / 4 did not pass; thresholds unchanged. Listening approval does not erase machine failures. |
| Input and scope | Self-authored Kiki-synthesized input, sent through real browser RTC and ASR. Real microphone, telephony and arbitrary dialogue adaptation were not accepted. |
| Remaining limits | Repetition/verbosity, strict waveform differences, historical ASR issues and external-source validity boundaries remain recorded. |
| Release state | Services stopped and sessions / leases / in-flight work closed. Ordinary defaults and `QUALITY_PENDING` unchanged; no production release is implied. |

Tested package hash:
`1a05f043c5b19ff4653b6de50c7d2af608b6e0d0b85c3a3f306fceb29eb16f86`

Quote guard revision: `r8-active-accepted-month-evidence`.

This is the tested method-package hash. PUBLICATION.json separately records per-file hashes and the publication-base Git commit; these identifiers are not interchangeable.

## Synchronized implementation and entry points

|Responsibility|Actual source|
|---|---|
|Dialogue and knowledge|[VoiceDialogue](../../../src/application/voice_dialogue.py), [KnowledgePort](../../../src/application/voice_communication.py), [PublicKnowledge](../../../src/adapters/voice_knowledge.py)|
|Understanding → application acceptance → frozen plan → expression|[voice_skill_plan.py](../../../src/application/voice_skill_plan.py), [voice_skill.py](../../../src/application/voice_skill.py)|
|External Skill and communication style|[Registry](../../../communication/skill-registry.json), [method package](../../../skills/consultation-dialogue/v3/SKILL.md); persona, policy, depth and verbosity are independent|
|Speech adapters|[SpeechService](../../../src/application/speech_service.py), [ASR](../../../src/adapters/candidate_asr.py), [VoiceOutput](../../../src/adapters/voice_output.py), [Kiki streaming](../../../src/adapters/qwen_voice_output.py)|
|RTC and state|[Worker](../../../apps/voice_worker/main.py), [session API](../../../apps/api/voice_sessions.py), [media client](../../../apps/web/src/features/voice/livekit.ts), [state client](../../../apps/web/src/features/voice/client.ts)|
|Runtime boundaries|[Budget](../../../src/adapters/voice_call_budget.py), [factory](../../../src/adapters/voice_candidate_profile.py), [journal](../../../src/infrastructure/database/voice_tables.py)|

[PUBLICATION.json](PUBLICATION.json) maps source hashes and publication changes. Core dialogue, contracts, Skill resources, knowledge and Worker match R8. Integration into newer main, portable private-file references, explicit rejection of missing research bindings, and removal of private historical captures from public tests are publication changes; they do not constitute a new RTC acceptance.

### Verified offline commands

From the source checkout with Python 3.11 and declared dependencies already available:

```bash
python -m pytest tests/voice/test_skill_intent_scope.py tests/voice/test_skill_summary_boundary.py tests/voice/test_qwen_voice_output.py tests/voice/test_candidate_asr.py tests/voice/test_window_budget.py -q
python -c "from apps.api.main import create_app; from src.application.voice_dialogue import VoiceDialogue; from src.adapters.voice_candidate_profile import candidate_node"
node --check scripts/voice_rtc_multiturn.mjs
cd apps/web && npm run typecheck:voice
```

These are mock/static checks, not model or media tests. Optional dependencies are declared under `voice` and `speech` in root `pyproject.toml`. This task reuses the installed environment; fresh-machine installation and independent wheel distribution are unverified.

### Controlled runtime entry points and limitations

Existing entry points remain `apps.api.main:app`, `python -m apps.voice_worker.main`, `scripts/voice_skill_text.py`, and `scripts/voice_rtc_multiturn.mjs`. This PR checks their imports, syntax and boundaries without launching a new consultation. They are not a one-command deployment guide. Voice authentication remains disabled by default and ordinary sessions remain `QUALITY_PENDING`. Existing `/voice-lab` is a manual control page, not the complete R8 product UI.

An operator must supply LiveKit/Redis, explicit local identity and Worker secret, isolated journal, admission/budget/profile/TLS receipts and private credential references. The [public profile template](../../../examples/voice/profile.example.json) is redacted structure only; `VEFIN_VOICE_PRIVATE_CONFIG_DIR` selects the private root. It contains no keys, active authorization, budget or TLS receipt and cannot initiate paid tests. Existing model/VAD assets must be available; this publication downloads none. Research binding, customer accounts, institutional writes and a real human recipient are not connected; missing capabilities fail explicitly.

The four TypeScript files are real transport/client primitives with their dependencies. The unrelated research React application was not copied or mounted into main's investor UI. The existing full-product RTC browser Harness still requires the Owner's isolated environment; private runtime state, recordings and output evidence are not published. CVC deployment is outside this PR.

[Documentation](../../README.md) · [Repository overview](../../../README.md)

### Publication offline results

217 checks passed; 2 legacy research task/chat bridge checks were skipped and are not passes. API/Worker imports, Harness syntax, client TypeScript and 155 relative documentation links passed. Project LLM, ASR, TTS, RTC and competition calls were all zero. Fresh installation, complete product UI build and live acceptance of this publication were not executed.
