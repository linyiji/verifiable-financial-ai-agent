# Phase 4 VS01 前端验收

[English](README.md)

本隔离 Playwright 包观察生产前端旅程：

```text
Research Object -> Research Goal -> AI Research Scheme -> Confirm
-> automatic exact Run -> Run Workspace -> Research Path
```

七个计入生产验收的规格使用真实前端、后端 HTTP 与后端 SSE 流量。
它们不安装 Playwright 响应路由、不代填响应、不向私有存储播种、不创建 service worker，也不伪造业务载荷。
Chromium DevTools Protocol 仅用于给一个已观察的精确投影 URL 添加延迟；延迟响应体仍来自真实后端。

可达前端模块发现失败关闭：至少找到一个同源模块，每个选定模块都必须成功获取，其精确字节由测试框架计算 SHA-256。
不接受自报构建哈希作为源码证据。
浏览器账本异步扫描有界公开请求头/体、公开业务响应头及每个有限响应体。
也扫描已知 Object/Run 路由之外的 Fetch/XHR 和 JSON 响应；绑定证据仍限于已审查 API 基地址与已知冻结路由。
仅保留大小和确定性哈希。
有意不无限缓冲活动 `text/event-stream` 响应体；扫描其头，并由实时 SSE 规格断言 Run/游标/事件行为。

## 全新引导与命令

严格使用 Node 24。包设置 `engine-strict=true`，每个可运行入口也检查 Node 主版本。
从本目录的干净检出开始：

```sh
node --version # must print v24.x.x
npm ci
npm run install:chromium
npm run check
VS01_FRONTEND_URL=http://127.0.0.1:4173 \
VS01_BROWSER_SCENARIO_FILE=/absolute/path/to/generated-scenario.json \
VFAS_VS01_SECRET_SENTINEL=<runner-random-secret-sentinel> \
npm run test:real
```

`npm run check` 运行纯契约/场景测试、审计真实规格中的禁止模拟行为、收集（不执行）七个 Playwright 规格，并验证 JSON 注解映射。
`test:real` 严格执行：产品前置条件不可用或场景格式错误时失败而非跳过。
编排器可设置 `VS01_BROWSER_ARTIFACT_DIR`，更改 JSON、HTML、trace、截图和视频产物位置。

## 场景输入

运行器在源码树外写入非秘密 JSON 文件。ID 必须从隔离的 PostgreSQL 后端环境采集，绝不能由显示标签推断：

```json
{
  "schemaVersion": "phase4-vs01-frontend-scenario/v1",
  "object": {
    "objectId": "OBJ-A-...",
    "symbol": "...",
    "companyName": "..."
  },
  "goalText": "...",
  "asOf": "2026-09-05",
  "missingRunId": "RUN-...-ABSENT",
  "missingErrorCode": "NOT_FOUND",
  "alternate": {
    "objectId": "OBJ-A-...",
    "runId": "RUN-A-ALTERNATE-...",
    "taskId": "TASK-A-ALTERNATE-..."
  },
  "foreign": {
    "objectId": "OBJ-B-...",
    "runId": "RUN-B-...",
    "taskId": "TASK-B-...",
    "sentinels": ["a B-only safe display sentinel"]
  },
  "financial": {
    "objectId": "OBJ-C-...",
    "runId": "RUN-C-RELEASED-...",
    "metricId": "METRIC-C-ADVERSARIAL-...",
    "adversarialProperty": "NUMBER_STRING_ROUNDTRIP_CHANGES"
  },
  "backendUnavailableFrontendUrl": "http://127.0.0.1:4174",
  "primaryApiBaseUrl": "http://127.0.0.1:8080/api",
  "unavailableApiBaseUrl": "http://127.0.0.1:18080/api"
}
```

`primaryApiBaseUrl` 与 `unavailableApiBaseUrl` 是已审查的预期公开 API 基地址。
请求账本证明每个观察到的业务请求使用对应精确源地址和路径前缀。
测试框架有意不规定运行时配置端点、绑定标识或前端构建哈希模式。

前端部署可在运行时或编译时绑定 API。
若采用编译时绑定，运行器必须构建并审查两个独立前端产物，在两个前端源地址提供服务。
在提供已构建包时改变 `VITE_*` 不是重新绑定，也不构成证据。
若采用运行时绑定，部署溯源由运行器负责；本框架不强制特定运行时配置端点、产物、顺序或模式。

`financial` 标识 C/主协调方提供的真实已发布产品目标，有意不包含预期数值。
测试从精确公开结果响应捕获 `canonical_value`，并要求该字符串自身满足 `NUMBER_STRING_ROUNDTRIP_CHANGES`（例如 JavaScript `Number` 字符串往返会丢失精度或小数末尾零）。
运行器必须从已审查配置/采集证据选择真实目标；浏览器框架不播种、重写或捏造指标。

真实套件执行必须提供 `VFAS_VS01_SECRET_SENTINEL`，且有意不放入场景 JSON。
运行器必须向产品进程注入相同随机值。
DOM、源码、请求、响应、控制台和页面错误扫描按精确值匹配，但证据仅保留发现代码/路径或哈希，绝不保留哨兵值。

## 运行器要求

执行 `npm run test:real` 前，主协调方运行器必须：

- 选择 Node 24，执行干净 `npm ci`，安装锁定的 Playwright Chromium；
- 启动绑定 `primaryApiBaseUrl` 的主前端，连接真实 PostgreSQL 后端；
- 在 `backendUnavailableFrontendUrl` 启动单独审查的不可用前端，绑定实际关闭/不可达的 `unavailableApiBaseUrl`，不使用浏览器拦截；
- 创建不同真实 Object A/B 资源、缺失 Run ID，以及外来 Object-B Run/Task，用于错误资源隔离（外来 Run 可已终态）；
- 通过产品提供独立真实已发布 `financial` Run/指标；配置 ID 必须由门禁侧采集证据支持，传输 `canonical_value` 满足配置词法属性；场景 JSON 绝不放入预期规范值；
- 浏览器执行前立即创建 `alternate`：Object A 的新非终态、足够稳定的 Run/Task，区别于浏览器创建的正常路径 Run A；
- 在产品内提供两个同 Object-A Run 之间的 SPA `run-navigation-item` 链接；
- 向两个前端进程、后端进程和 Playwright 进程注入同一运行器随机值 `VFAS_VS01_SECRET_SENTINEL`；
- 写入上述精确场景字段，并在 Playwright 报告外保留部署/构建审查证据；
- 使用支持 `Network.emulateNetworkConditionsByRule` 和 `appliedNetworkConditionsId` 关联的 Chromium；
- 保持图序列化使用已批准源码编码（`graph_id`、`run_id`、`version`、`tasks`），除非 C/主协调方先审查并绑定不同公开编码。
  框架不会默默假设显式图 `edges` 成员，或 `add_edge`/`remove_edge` 端点成员拼写。

## 七个真实规格与控制证据

每个控制项在 Playwright JSON 中恰好以 `vs01-control` 注解一次：

| 真实规格 | 精确控制项 |
|---|---|
| Object → Goal → Scheme → Confirm → 自动 Run | `VS01-FE-003` 至 `VS01-FE-007`、`VS01-DYN-001` |
| 活动 Run A → 同 Object 备用 Run 切换，加真实延迟 Run A 投影 | `VS01-REC-008`、`VS01-ID-003` |
| 浏览器离线后从最后提交游标恢复 SSE | `VS01-REC-009` |
| 错误资源网络/DOM 隔离 | `VS01-FE-008` |
| 类型化缺失资源重试/关闭 | `VS01-FE-009` |
| 已发布对抗性小数、公开传输到呈现精确相等 | `VS01-FE-012` |
| 后端不可用与公开界面/源码负面测试 | `VS01-FE-010`、`VS01-FE-011` |

切换规格先证明从浏览器创建 Run A 导航到新的同 Object 备用 Run，会结束旧 A 活动流、打开精确备用流，并不在备用工作区留下 A Run/Task 状态。
随后针对真实 A 投影 URL 设置定向 CDP 延迟规则，在真实 A 响应到达前切回备用 Run，等待响应与确定性产品生命周期边界，证明备用 URL、Run、Task ID、原始 Task 状态、进度、父级及依赖均不变。
必需公开 `projection-lifecycle` 状态标识当前请求 epoch、精确已接受修订/序列，以及标记 `STALE_RESPONSE` 的精确已丢弃 Run/epoch/修订/序列。
观察证据持续到丢弃/稳定信号出现；不用经过时长窗口决定验收。
公开属性 `MutationObserver` 证明消费响应时没有瞬间渲染 A 身份或 Task 状态。这是真实集成 `VS01-ID-003` 证据。

离线规格证明精确 Run SSE 从投影游标开始；浏览器离线把公开连接状态变为 `RECOVERING` 或 `BACKOFF`，不改变 Run、不创建 Run、不标记失败；
重连从最后提交游标打开相同 Run，达到 `OPEN` 或非失败 `TERMINAL` 状态。

财务规格通过正常产品 UI 打开真实已发布目标，捕获精确 `GET /research-runs/{run_id}/result` 响应体，定位唯一配置指标，将其规范小数作为字符串传入可见 DOM 等值断言。
该字符串必须能对抗 JavaScript 数字往返。传输到呈现相等是主要 `VS01-FE-012` 证据；已提供源码的正则检查仅为补充纵深防御。

`VS01-FE-008` 有意仅限错误资源网络/DOM 隔离，不宣称覆盖过期响应行为。

## 可观察公开挂钩

优先通过可访问角色/名称定位控制项。不透明身份与原始后端值要求稳定、与呈现无关的 DOM 属性：

| 挂钩 | 必需可观察契约 |
|---|---|
| `research-object-option` | `data-object-id` |
| `scheme-preview` | `data-object-id`, `data-goal-id`, `data-scheme-id`, `data-draft-id` |
| `confirm-run` | 可访问的 Confirm/Start 按钮，具有正常禁用/忙碌行为 |
| `run-workspace` | `data-run-id`, `data-object-id`, `data-goal-id`, `data-scheme-id`, `data-run-status`, `data-run-stage`, `data-projection-revision`, `data-projection-sequence` |
| `research-path` | 精确当前 `data-run-id` |
| `research-task` | `data-run-id`、`data-task-id`、权威 `data-task-status`、`data-task-progress`、可空 `data-parent-task-id`（null 时为空）及紧凑 JSON `data-dependency-ids`，保留后端依赖顺序 |
| `runtime-connection` | `role=status`、`aria-live=polite`、`data-run-id`、`data-connection-state`、`data-last-sequence`、`data-stale`；状态包含 `OPEN`、`RECOVERING`、`BACKOFF`、`TERMINAL` |
| `projection-lifecycle` | 可见 `role=status`；`data-run-id`、规范整数 `data-request-epoch`、`data-settled`；已接受元组 `data-consumed-run-id`、`data-consumed-request-epoch`、`data-consumed-projection-revision`、`data-consumed-projection-sequence`；过期元组 `data-last-discarded-run-id`、`data-last-discarded-request-epoch`、`data-last-discarded-projection-revision`、`data-last-discarded-projection-sequence`、`data-last-discard-reason=STALE_RESPONSE` |
| `run-navigation-item` | 真实 SPA 链接，带 `data-run-id` 与 `/runs/{run_id}` href |
| `result-tab` | 可访问的 Results 标签/控件，触发正常已发布结果请求 |
| `released-financial-metric` | `data-run-id`、`data-metric-id`、精确字符串 `data-canonical-value`；包含一个可见 `canonical-financial-value`，其原始文本节点与传输字符串逐字节一致 |
| `typed-error` | `data-error-code`，以及提供时的 `data-resource-id` |
| `identity-quarantine` | `data-reason`，且不呈现任何外来身份或哨兵值 |

这些是公开验收可观察项，不是对 reducer/store 内部的访问。

## 解码器与公开界面负面检查

草稿解码器强制 API §5.2 中精确 Goal/Scheme 字段，包含请求绑定的 `as_of`/偏好、全部七个 Scheme 数组、生成器元数据及未确认可空性。
原子解码器强制全部 21 个顶层字段、精确八字段 Object 和十四字段 Run；Goal/Scheme 身份与时间戳；计划/实际图闭合；
类型化 Task ID、父/依赖闭合、全部 12 个 Task 状态与进度比例；完整生命周期/进度元组；精确 13 字段 PathChange 记录；
可用性包装的 Review/result/artifact/proof/execution 摘要；精确终态/发布闭环。
每个投影响应还必须携带精确 `"p4:<run_id>:<projection_revision>:<projection_sequence>"` ETag。
图身份/版本及 Task 使用已批准源码编码。
规范化类型边是权威 Task `dependencies` 的机械视图；与顶层 Task 投影核对，不发明第二种后端边关系。
冻结契约精确定义结构中的未知字段、不安全公开图成员和不一致可空性均失败关闭。

API §6 将图成员对象简写为 `{}`，V17 §6 冻结语义要求但未指定单独的 snake-case 边编码。
已批准源码 `PlannedTaskGraph` 提供 `graph_id`、`run_id`、`version`、`tasks` 和 Task `dependencies`，没有 `edges` 成员。
因此显式图 `edges` 字段失败关闭，等待 C/主协调方审查。
API §6 展示 `add_node.task_id`；虽命名 `add_edge`/`remove_edge` 操作，却未冻结端点成员拼写。
此类边操作体也失败关闭，直至绑定已审查候选编码。
这是明确的 C/主协调方集成依赖，而非猜测的测试框架模式。

可见 UI 文本、序列化 DOM、可达前端源码、已解码错误信封、控制台错误和页面错误会检查 Qiji、MIMO、TeamoRouter、FMP、Langfuse、bearer/API-key 模式、
隐藏思维链/草稿推理/系统提示词术语、原始提供方载荷、堆栈、SQL 和内部路径。
证据仅保留安全路径、计数、泄漏代码和哈希，不保留可能敏感的原始错误文本。
源码扫描还拒绝前端财务计算权威和 Demo 回退标记。

## 冻结权威

- 冻结正式确认：`764d76132cfac13d47125e031b280b7894eb249f:docs/integration/FINAL_CONTRACT_FREEZE_PROMOTION.json`
- V17 R2 规范 SHA-256：`fc184034e448e85190aa4cfd92b89e90b9f258307632920daa8d8cd73c600c19`
- Phase 4 契约集 SHA-256：`0bf6c824d553847fa129a429715aedc36a30601a97421f4447cdd3f6d6a81741`
- 主要门禁：`P4-E2E-009`、`017..026`、`065..075`、`088` 及 `P4-ID-001..005`、`023`、`025..027`。
