# 显式专家可用性路由

[English](SPECIALIST_PROFILE_ROUTES.md)

Owner 批准的 Phase 5B 配置仅将 peer_analysis 和 research_news_analysis 覆盖为 mimo-direct / mimo-v2.5。未列出的配置保留现有供应商对象；Fundamental 不变。这是静态组装，不是排名、全局故障切换或学习式路由。

Settings.specialist_provider_routes 经由既有供应商路由工厂解析，并注入共享 Agent 注册表。任务语义保持供应商无关。未知任务配置 / 路由安全拒绝；多配置 Agent 要求配置一个一致供应商。所有选定凭据进入既有遥测 / 产物禁止值集合。

两个精确 R3 专家能力门禁均在当前传输上一次通过，安全解析的类型化结果保留在本地。Peer：15.689s，4992 输入 / 528 输出 token。Research/News：6.951s，869 / 193 token。不增加数字 token 启发式规则。不重试能力调用，不更改传输策略。

准入前回归检查点：134 项专项测试 PASS，包括隔离 schema 的 PostgreSQL 记忆 / 重执行测试、Agent 身份绑定、路由隔离、严格输出验证及输入确定性。R4 发布和 Phase 5 完成是独立门禁，此检查点不作相关声明。
