# GitHub publication preparation — no remote changes

[简体中文](GITHUB_PUBLICATION_PREP.zh-CN.md)

Suggested description: Locally deployable adaptive financial research agent with verifiable execution, financial review, research memory, and bounded runtime recovery.

Suggested topics: financial-research, multi-agent, ai-agents, research-memory, adaptive-runtime, fastapi, react, postgresql, verifiable-computation.

Suggested release title: Verifiable Financial Agent — Local Deployable Alpha.

Default branch recommendation: after deliberate review and synchronization, make the accepted product branch the public entry point, either through an Owner-approved main integration or explicit default-branch decision. Do not assume today's default contains the accepted product.

Branch cleanup: inventory and compare remote branch reachability during the separately authorized publication task. Preserve acceptance tags and unmerged work; do not delete by name alone.

Before publishing: review the redacted secret audit and license decision. Recognition is now Owner-confirmed: AIx Origin Summit Hong Kong · Flux Track · Bronze Award; do not describe it as unconfirmed. Do not publish private DB/artifacts, runtime authority files, keys or raw participant data. Provider base URLs/model IDs are configuration, not credentials.

Investor/tester guidance supports the guided Docker installer with a privately supplied encrypted `.vfacred` bundle or [native BYOK](LOCAL_DEPLOYMENT.md). API integrations are built in, not API keys. The optional gateway remains NOT_DEPLOYED; direct encrypted credentials do not depend on it. The release image packages locked RISC Zero 3.0.6 Proof and a governed Sandbox broker.

No push, release, remote tag, metadata edit, default-branch change or remote branch deletion was performed by this preparation task.
