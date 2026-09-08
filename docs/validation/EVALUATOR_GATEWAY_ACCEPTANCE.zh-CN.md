# 评估者网关基础验收 — 2026-09-08

[English](EVALUATOR_GATEWAY_ACCEPTANCE.md)

> 当前指引澄清 — 2026-09-08：此历史 PASS 是离线代码／契约验收，不代表网关已部署，也不代表外部用户已成功完成真实研究流程。网关仍为 NOT_DEPLOYED。当前建议投资者和测试员采用直接 API 的 BYOK，在本地配置自己的 Key，或由 Owner 单独私下提供的测试 Key。以下历史评估者流程及下一步措辞作为当时任务记录保留，不是当前交付建议。

起始检查点：`11837c3f9fc480c651f1c3663faac854bdce574b`，分支 `phase4`，已跟踪工作区干净。本验收覆盖凭据／访问基础，不代表已部署服务或付费研究运行。

## 证据

- **292 项离线后端测试通过**，存在两项已有的 FastAPI/Starlette 弃用警告。包含 59 项新增评估者测试，以及 BYOK／路由、MiMo、专业 Agent、只读／API、Memory、增量研究、LLM、恢复、数据／摄取／证据和研究路径契约。
- **32 项前端契约检查通过**：只读 Memory 导航 8/8；Object Workspace V2 共 24 项检查。
- `npm run build`：TypeScript `tsc --noEmit` 与 Vite 生产构建 PASS。已有的 >500 KB 包大小警告仍存在；未修改前端语义。
- 新评估者代码／测试／入口的 Ruff 检查 PASS；`git diff --check` PASS。
- 已完成独立的只读模型／恢复、数据及安全审查。仅主代理执行编辑。已修复发现的问题：单次尝试截止时间有效性、FMP 历史边界兼容性、安全提示／日志、终态授权证据、恢复候选优先级、零配额 readiness 措辞，以及如实区分系统定义的截止时间错误。

## 离线本地评估者流程

测试在临时的仅存哈希的 SQLite 存储中生成不透明的假凭据，将其加密为临时凭据包，启动带假上游的临时回环 HTTP 网关，经真实会话准备函数解密／导入，并实际执行回环 HTTP readiness。上游调用与付费操作计数变化始终为零。ASGI 测试还使用假上游调用了所有受控模型路由及有界数据传输。Owner 传输通过 HTTPX MockTransport 测试，只使用合成密钥。CLI 帮助入口成功执行，未激活产品后端。

通过网关测试了同一 Run／同一 Task 的自适应恢复：MiMo 读取超时 → 现有检测器／监督器／策略 → 获准 Sol → 成功。授权拒绝产生失败尝试／终态证据，供应商切换次数为零。另行测试了生产组装，确保无论网关元数据顺序如何，均保留现有 Sol → Luna → MiMo 优先级。

凭据测试覆盖错误／到期／撤销令牌、模型和数据权限范围／配额、限流、原子并发预留、不持久化明文 bearer、拒绝任意权限、安全响应／日志过滤、加密往返、错误密码、元数据／密文篡改、损坏／过大凭据包、安全提示失败、导入失败后清除会话、空格／Unicode 路径与 Windows 驱动器语法。真实 UI 没有 bearer 字段；`.env.example` 没有令牌设置，供应商密钥保持为空。

## 复现

安装开发依赖后，在仓库根目录运行：

```bash
python -m pytest -q tests/evaluator tests/phase4/backend_product/test_evaluator_routes.py tests/phase4/backend_product/test_mimo_foundation.py tests/phase4/backend_product/test_specialist_routes.py tests/phase4/backend_product/test_readonly_projection.py tests/phase4/backend_product/test_api_contract.py tests/phase4/backend_product/test_memory_api.py tests/phase4/backend_product/test_memory_contracts.py tests/phase4/backend_product/test_memory_source.py tests/phase4/backend_product/test_memory_comparison.py tests/phase4/backend_product/test_incremental.py tests/unit/llm tests/unit/agentic/test_adaptive_recovery.py tests/unit/agentic/test_recovery_policy.py tests/unit/data/test_fmp_adapter.py tests/unit/data/test_live_fmp_integration.py tests/unit/data/test_evidence_ingestion.py tests/unit/application/test_evidence_semantics.py tests/unit/test_phase4_research_path.py
```

尽管保留了历史文件名，`test_live_fmp_integration.py` 使用的是 fixture／mock；没有授权或执行真实 FMP 请求。CI 包含评估者测试套件。

## 发布与安全边界

已检查跟踪树／新文件／差异中的供应商密钥、bearer 令牌模式、私钥，以及误提交的真实凭据包／存储。匹配项是已有、刻意设计的虚假脱敏测试 fixture；未包含真实供应商密钥、真实评估者 bearer 令牌或真实评估者凭据包。忽略规则覆盖 `.vfaeval` 与网关 SQLite 状态。这种模式／源码审查不等于对所有秘密的自动检测保证。

投资者文档九问流程 PASS：无需上游密钥；一个私有加密凭据包；真实产品代码；服务器端密钥；macOS 和 Windows/WSL 指引；无需手动 API 检查；权限范围／到期／配额；保留 BYOK。

**REAL_GATEWAY_DEPLOYMENT = NOT_DEPLOYED.** 未进行真实模型／供应商／FMP 调用、新建生产 Run、生产数据库迁移或 GitHub 推送。未签发 Owner／投资者真实凭据。未执行原生 Windows 和 WSL2 主机测试；覆盖的是可移植启动器实现与路径契约，而非原生完整证明能力一致性。macOS Keychain 和 Windows Credential Manager 集成为 NOT_IMPLEMENTED。完整 Windows 证明评估仍建议通过 WSL2。未实现商业计费；实际成本仍为 NOT_OBSERVED。

基础 PASS 允许开展下一项独立任务：**FINAL_GITHUB_PUBLICATION**，包括最终 README／秘密审计、分支计划及本地可部署版本元数据。部署网关仍是获得真实评估者访问能力的 Owner 运维前置条件。
