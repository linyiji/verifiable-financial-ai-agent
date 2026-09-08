# WS-A — 数据与证据

[English](WS_A_DATA_EVIDENCE.md)

负责范围：

- `src/data/**`
- `src/adapters/fmp/**`
- 证据专项测试

先阅读架构决策与数据模型。

实现：

- 数据提供方接口
- 测试夹具提供方
- FMP 适配器边界
- 新鲜度检查
- 校验
- 规范化
- 冲突检测
- AcceptedEvidenceBundle
- EvidenceRecord 持久化

禁止：

- 实现 Agent 规划
- 实现调度器
- 计算正式财务指标
- 将提供方原始 JSON 直接传给 Agent

测试：

- 有效证据
- 字段缺失
- 期间不匹配
- 单位规范化
- 被拒绝的证据
- 确定性测试夹具重放

编写 `WORKSTREAM_REPORT_DATA.md`。
