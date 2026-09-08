# 17 — 风险与未决问题 V1

[English](17_RISKS_OPEN_QUESTIONS_V1.md)

以下事项当前**没有冻结答案**，工程不得自行假设成正式产品事实。

## 数据／供应商

- FMP Basic 实际可用 endpoint / rate limit / licensing 范围需以真实账号和协议核验。
- 是否加入 SEC / Yahoo / 其他 Provider 未冻结。
- 多数据源冲突时最终 source priority 需要业务规则。

## LLM

- 最终 Provider / Model / Version 未冻结。
- Specialist Agents 是否都使用不同 Model 未冻结。
- Model routing / POT 先留接口。

## 研究方案

- AI Scheme 的具体生成 prompt / model 需实现后评测。
- 是否允许用户手动编辑 Scope 需要 UX 决策。
- 未来是否保存 Scheme 为模板未冻结。

## Agent

- MVP 是否真的需要独立 Peer Agent / News Agent 可按实现成本调整。
- Agent 数量不得成为目标本身。

## 生成代码

- Phase 1 只需要接口 / simple demo。
- Docker sandbox 的资源限制、image、language policy 待工程验证。
- Generated Capability 自动升级 Certified 不做 MVP。

## ZK

- 最终选择哪一个 deterministic statement 作为 hackathon proof 需开发验证后锁定。
- RISC Zero release version 需要实施时 pin。
- Proof latency 需要实测。

## 前端

- 视觉样式仍可变化。
- 稳定的是页面业务对象与 Runtime Event contract，不是当前 HTML 像素。

## 部署

- PostgreSQL / SQLite local strategy 已定方向，生产云环境未定。
- Desktop / Local Runtime 属未来阶段。

## 合规

- 研究报告免责、数据展示授权、商业数据许可需产品上线前单独审查。
- ZK / Verified 不能在营销文案中被表述成“金融结论绝对正确”。
