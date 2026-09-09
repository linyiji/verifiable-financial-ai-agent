# 按输出要求判定执行收尾

[English](EXECUTION_CLOSURE_REPAIR.md) · [Results 验收](RESULTS_SEMANTIC_CLOSURE_ACCEPTANCE.zh-CN.md)

Closure 4 修复历史 NVDA 失败暴露的授权注册遗漏：Risk Agent 支持执行
`risk_follow_up`，但任务级恢复候选策略未包含该 profile，导致模型调用前失败。
现已添加显式、有界授权，并在组合注册时校验。没有增加超时或恢复预算。

基本面叙述在 Sol 及 Luna 能力检查超时后耗尽可用授权路线；其叙述属于支持性
输出，必需的确定性金融输出已存在，因此它不是 Run 终止的直接根因。

`ExecutionClosureState` 区分必需输出、支持性输出、限制和类型化阻断原因。
保留既有定型叙述契约。其他生产任务只有在全部已记录输出都被真实下游祖先
依赖范围内的 optional 或已满足 ANY_OF 契约覆盖时，才可局部隔离失败。
hard required 和严格任务依赖仍阻断。没有可选契约的已批准追踪任务仍为必需，
不能按任务名称统一放宽。未知完整性异常仍然全局失败。

必需输出缺失时，在 Review / Proof 之前停止；可审查的部分结果仍走普通
Review、Proof 策略、Release Gate 和报告流程。类型化原因可通过公开投影读取；
调度器异常不再被错误归因为 assurance。历史任务、Run 和 Proof 均不改写。

历史 Run 缺少必需追踪输出和 Synthesis。完整隔离数据库副本的 SELECT-only
投影正确保持 NOT_RELEASED，原因为 `REQUIRED_RESEARCH_OUTPUT_MISSING`。
10 个计算与 539 条证据不等于发布授权。原库与副本所有表的指纹在判定前后
一致。回放不调用模型、Provider、计算或 Proof。离线合成验收包括支持性失败
后真实 Review/Release、必需失败阻断、有范围约束的 ANY_OF，以及 W2 附限制
发布和未发布契约。

本次仅本地修复，不发布 GitHub、不启动新 live Run。原 live 预算已耗尽，
下一次必须由 Owner 重新明确授权。

## 离线验收（2026-09-09）

定向 closure / recovery / Results 测试 61 项通过；全量后端 1,415 项通过
（一项依赖弃用警告）。前端 133 项通过；TypeScript 与 Vite 通过。
安装镜像构建及 7 项禁网导入通过，6 个运行时源码指纹与镜像一致。
双语本地 Markdown 链接检查 472 个、无断链；7 个配置凭证值扫描无命中。
没有 live / Provider 调用、原数据库写入或 GitHub push。
