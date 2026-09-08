# Phase 5B Scheme 修复 — 仅实时执行前

[English](PHASE5B_SCHEME_REPAIR_RECEIPT.md)

起始与最终 HEAD：`d414ec084aa03f65b56d6e465a7706dd3e2decef`。
保留既有 Phase 5B 脏工作树。未提交、打标签或推送。

## 根因与证据限制

一次获授权的仅规划诊断 HTTP 尝试复现了 HTTP 400 的 schema / 必填字段拒绝。未创建 Research Run。旧增量输出 schema 在严格结构化输出请求中包含开放字典；实际适配器原样转发 Pydantic schema。本地 schema 检查证明了不兼容性。远端安全标志提到 schema 和 required，并未具体指出 additionalProperties。历史通用 ValueError 处理丢弃了供应商分类。不公布原始供应商错误 / 消息。

修复以封闭类型化决策记录替换字典，保留安全失败阶段 / 分类，对照精确不可变源身份解析提案，并对齐前端解码器和稀疏记忆验收策略。移除虚构的整视图 REUSE，并允许有界 Research Lead 判断。UNKNOWN 不能变成复用。已解决问题需要精确 PERIOD_MISMATCH 授权依据。

修复后的 schema 使用生产 HTTP 序列化器 / 解析器及 MockTransport 验证，未进行第二次付费模型调用。因此尚未观测到远端接受修复后 schema。这是本地实时执行前门禁，不代表实时 Phase 5B 完成或 Memory v2 验收。在本任务中，不得删除或绕过诊断脚本的排他 HTTP 标记来重复付费调用。

## 验证

- 203 项专项 Python 测试通过，另有 4 项隔离 PostgreSQL 精确基线拒绝测试通过。
- 187 项前端检查通过：incremental 23、memory 20、M3 14、R1 provenance 6、M4 27、M5 37、M6 35、progress 10、lifecycle 15。
- 类型检查及生产构建通过。
- 17 项浏览器检查在明确标记的本地 HTTP mock 草案上通过。实际 R1 Report/Review/Execution 经生产 GET 界面读取。
- 目视检查两张 Scheme 截图：仅包含三个真实决策项，无虚构复用区；显示当前 Goal、工作要求和确认。
- 仅预览的独立任务图验证通过，未准入或创建新数据库 Run。
- 浏览器测试框架禁用调度器启动，并阻止除本地不持久化 prepare 响应外的所有写入。准入请求在进入后端前被阻止。其最初的媒体类型缺陷已修复，以匹配冻结的 UTF-8 契约。

证据位于 `artifacts/phase5b_scheme_repair/`：planning-diagnostic-result.json、local-preview-draft.json、browser-pre-live.json、preview-firewall.json、history-guard.json、scheme-decisions-preview.png、scheme-current-work-preview.png。获接受的浏览器验收有一次本地 prepare 和零次供应商调用。独立于该框架，上述诊断恰好使用一次真实规划 HTTP 尝试。

全部 36 个既有 Run ID 及 R1/v1 指纹不变。最新仍为 `RUN-57aed683-75d6-4b47-acc6-a73053ea492e` / View 1（`RVV-05bec42f-ab9b-55c5-b502-c439b8abe948`）。未创建 R2 或 Memory v2。

本地门禁 PASS；下一获授权阶段为一次实时增量 R2。在此 STOP。
