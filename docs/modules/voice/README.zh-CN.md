# VeFin Voice · 语音沟通模块

[English](README.md)

**VeFin 内可复用的语音沟通模块。** 将用户语音、任务上下文、已登记知识和受控对话连接成语音回答，同时保留来源、任务状态、用户限制与交付记录。

**当前可用性：** 本PR同步真实语音源码、必要依赖、离线检查及模块导航。R8本机限定RTC咨询与人工听评已通过；发布分支仅做离线验证，未重新调用ASR/LLM/TTS或RTC。现有研究系统安装器仍不自动启用语音；没有独立语音安装包、托管API或生产认证。

## 模块的作用

| 职责 | 作用 |
| --- | --- |
| 语音与传输 | 经 RTC 接收语音，取得 ASR 转录，将已接受回答合成为语音，并记录客户端实际交付。 |
| 对话与引导 | 回答有依据的问题，追问必要信息，在用户要求或任务条件满足时停止。 |
| 外置 Skill 与沟通配置 | 加载任务方法及选中人格/策略；表达风格与事实、权限、任务状态分别管理。 |
| 知识与来源 | 使用已登记且适用的知识，保存来源引用，区分已知事实、用户陈述、未知与技术失败。 |
| 任务承接 | 跨轮保留已接受信息、更正、独立禁止和待补项；非关键缺项可以待补，独立回答仍可交付。 |
| 受控输出 | 应用接受字段候选并冻结回应计划后，再生成自然表达；内容接受先于 TTS，生成、发布与客户端接收分别记账。 |

典型链路：RTC 输入 → ASR → 原 VoiceDialogue / KnowledgePort → Skill 与任务状态 → 理解候选 → 应用回应计划 → 自然表达 → 接受 / renderer → TTS → RTC 客户端。

模块提供的是有持续状态的完整沟通闭环。语音识别与合成是其中的适配能力。

## 与 VeFin 其他能力的分工

| 组件 | 负责什么 |
| --- | --- |
| 语音模块 | 听取输入、组织对话、必要引导、语音交付和沟通结果。 |
| 业务能力 / Port | 权威业务记录、核验规则、查询结果及实际业务回执。 |
| Harness / Runtime | 可用能力、授权、预算、取消、执行身份及持久化边界。 |
| Skill | 可复用的任务方法和参考材料，不授予工具权限。 |
| 人格 / 策略 | 语气、主动程度、深度与篇幅，不改变事实和权限。 |

咨询状态 `COMPLETED` 不等于付款、账户变更或人工转接已完成。没有真实接收方时，人工跟进仍仅为 `REQUEST_RECORDED_NO_RECEIVER`。

后续业务可以提供任务目标、受限上下文、已登记知识和获准工具 Port，取得带状态与证据的沟通结果。这是预期的集成边界，**不是已经发布的可调用 API 合同**。交易对账和证据补齐是候选使用方，其后台接入不在 R8 验收范围内。

## 放在 VeFin 还是独立仓库

**当前决定：放在现有 VeFin 仓库，保持独立逻辑边界，暂不新建仓库。**

- 这是 VeFin 的一个能力模块，复用应用的对话、知识、journal 和运行边界。
- 保留一份实现和一条验收历史，避免在新仓库重复维护状态、授权和适配器。
- 当前文档入口为 `docs/modules/voice/`；它不是空的运行时包，也不要求为目录形式搬动已经工作的代码。
- 先把真实已验收源码同步进现有 application / adapter / API 组织；有实际使用方和依赖边界后，再评估独立封装与发布。
- 当实现能够独立安装/测试、合同和依赖稳定，且存在明确独立分发需求时，再考虑拆仓。

当前先完成仓库内模块化；独立仓库属于后续分发选择。[仓库许可证决策](../../LEGAL_AND_LICENSE_STATUS.zh-CN.md)保持原状态。

## R8 验收摘要

**证据来源：** 在Owner本机实际读取并核对的R8原始报告、执行清单、当前结果和本场人工听评。本节是本地结果的公开摘要，不是从此 GitHub 快照重新复验的结论。本次不发布原始对话、录音、凭据、私有配置或计费账本。

| 项目 | 报告结果与边界 |
| --- | --- |
| 业务场景 | 保诚香港扣款账户变更的公开入口咨询；无个人账户查询、提交、修改或实际人工转接。 |
| 固定配置 | `0.3.0/v3`；`efficient-partner / goal-led / core / concise`；本场没有人格/策略切换。 |
| 最终执行 | 同一新鲜两轮会话，9/9 段答复交付 RTC 客户端；此前三场失败独立保留。 |
| 任务状态 | 用户月份接受为 `UNKNOWN`、年份 `null`；咨询 `COMPLETED`；旧会话 pending 不改写。 |
| 对话处理 | 2.459 秒 / 2.509 秒，满足原 8 秒对话截止；不是端到端播报时间或 p95。 |
| 语音结束至客户端首音频 | 6.266 秒 / 4.836 秒。 |
| 人工听评 | Owner 确认粤语清楚完整，无明显爆音、截断或重复播放。 |
| 严格波形 | 5 项通过 / 4 项未过，阈值不变；听评不覆盖机器失败。 |
| 输入与范围 | 自编 Kiki 合成输入，经真实浏览器 RTC 和 ASR；不包含真人麦克风、电话或任意对话适应验收。 |
| 保留问题 | 重复/冗长、严格波形差异、历史 ASR 问题与外部来源有效性边界。 |
| 发布状态 | 服务停止，会话、租约和在途任务收口；普通默认及 `QUALITY_PENDING`不变，不表示生产发布。 |

本地受验包 hash：
`1a05f043c5b19ff4653b6de50c7d2af608b6e0d0b85c3a3f306fceb29eb16f86`

引用守卫 revision：`r8-active-accepted-month-evidence`。

该hash是受验方法包hash；源码逐文件SHA-256及本PR基点见PUBLICATION.json，Git commit SHA在PR中单列，三者不能混用。

## 本次已同步范围与使用入口

|职责|实际源码|
|---|---|
|原对话与知识|[`VoiceDialogue`](../../../src/application/voice_dialogue.py)、[`KnowledgePort`](../../../src/application/voice_communication.py)、[`PublicKnowledge`](../../../src/adapters/voice_knowledge.py)|
|理解→应用接受→冻结计划→表达|[`voice_skill_plan.py`](../../../src/application/voice_skill_plan.py)、[`voice_skill.py`](../../../src/application/voice_skill.py)|
|Skill和风格|[`communication/`](../../../communication/skill-registry.json)、[`consultation-dialogue`](../../../skills/consultation-dialogue/v3/SKILL.md)；三人格、三策略、深度与篇幅独立|
|ASR与统一音频|[`SpeechService`](../../../src/application/speech_service.py)、[`candidate_asr.py`](../../../src/adapters/candidate_asr.py)、[`VoiceOutput`](../../../src/adapters/voice_output.py)、[`Kiki`](../../../src/adapters/qwen_voice_output.py)|
|RTC与状态|[`Worker`](../../../apps/voice_worker/main.py)、[`会话API`](../../../apps/api/voice_sessions.py)、[`客户端传输`](../../../apps/web/src/features/voice/livekit.ts)、[`状态客户端`](../../../apps/web/src/features/voice/client.ts)|
|运行约束|[`预算`](../../../src/adapters/voice_call_budget.py)、[`配置factory`](../../../src/adapters/voice_candidate_profile.py)、[`journal`](../../../src/infrastructure/database/voice_tables.py)|

完整文件对应、受验hash及发布差异见[发布清单](PUBLICATION.json)。核心对话/合同/Skill/知识/Worker与R8一致；API主程序集成到更新main、凭据引用可移植化、可选研究绑定显式拒绝、公共测试剔除私有历史捕获，这些是发布适配，不能继承为一次新RTC验收。

### 已验证的离线入口

在源码根目录、Python 3.11及声明的依赖已安装环境中：

```bash
python -m pytest tests/voice/test_skill_intent_scope.py tests/voice/test_skill_summary_boundary.py tests/voice/test_qwen_voice_output.py tests/voice/test_candidate_asr.py tests/voice/test_window_budget.py -q
python -c "from apps.api.main import create_app; from src.application.voice_dialogue import VoiceDialogue; from src.adapters.voice_candidate_profile import candidate_node"
node --check scripts/voice_rtc_multiturn.mjs
cd apps/web && npm run typecheck:voice
```

这些入口使用mock或静态检查，不发项目模型/RTC请求，不启动语音服务。可选依赖声明在根`pyproject.toml`的`voice`与`speech` extras；本次复用既有环境验证，未重新安装，未证明全新机器安装或独立wheel分发。

### 受控运行入口及限制

原入口仍为`apps.api.main:app`、`python -m apps.voice_worker.main`、`scripts/voice_skill_text.py`和`scripts/voice_rtc_multiturn.mjs`；这几个真实调用入口本PR只检查导入、语法和前置合同，**没有执行新咨询**，不得当作一键可运行教程。API默认关闭语音授权，普通会话保持`QUALITY_PENDING`。原`/voice-lab`是已有手动控制页，不是R8完整产品UI。

运行需操作者另行提供LiveKit/Redis、显式本地身份与Worker secret、隔离journal、有效测试权限/预算/profile/TLS回执，以及外部凭据引用。公开[配置模板](../../../examples/voice/profile.example.json)仅是脱敏结构；PRIVATE_CONFIG目录可经`VEFIN_VOICE_PRIVATE_CONFIG_DIR`指定。它不包含私钥、有效预算、有效TLS或授权，不能直接执行付费测试。外部模型、VAD/ASR资产需预先具备，本次不下载。研究绑定/客户账户/机构写入/真实人工接收未接入；不会用假回执补成功。

浏览器四个TypeScript文件是实际客户端原语及必要依赖；本次未搬运整个研究React界面，也未把这些组件接进main的投资者UI。原RTC Harness的浏览器全产品页面仍需Owner隔离环境，GitHub快照不包含私有启动状态、录音或output目录。CVC赛事部署未随本PR发布。

[文档导航](../../README.zh-CN.md) · [仓库概览](../../../README.zh-CN.md)

### 本次发布离线结果

217项通过、2项跳过；跳过的是未同步的旧研究任务/聊天产品桥接，不能记为通过。API/Worker导入、Harness语法、客户端TypeScript及155个相对文档链接检查通过。项目LLM、ASR、TTS、RTC和赛事调用均为0。全新安装、完整产品界面构建及发布版本RTC复验未执行。
