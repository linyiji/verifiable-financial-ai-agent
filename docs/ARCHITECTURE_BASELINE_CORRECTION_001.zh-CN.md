# ARCHITECTURE_BASELINE_CORRECTION_001

[English](ARCHITECTURE_BASELINE_CORRECTION_001.md)

状态：**AUTHORITATIVE**<br>
授权者：用户<br>
日期：2026-09-03

## 被取代的中间指令

- 使用 Python 3.14 作为主运行时的指令作废，本项目不得采用。

## 当前权威基线

- 主后端运行时：Python `>=3.11,<3.12`
- Web／前端运行时：Node.js `>=24,<25`

## 原因

架构文档与 FinRobot 兼容范围均与 Python 3.11 一致。项目优先复用现有财务逻辑，
而不是引入 Python 3.14 兼容工作。

## 复用策略

替换任何已有实现前，均须审计并归类：

1. `DIRECT_REUSE`
2. `ADAPTER_REUSE`
3. `PORT_REQUIRED`
4. `REPLACE_REQUIRED`

必需的工程顺序是 `REUSE → WRAP → ADAPT → TEST`，而不是被目标目录布局驱动的重写。

FinRobot 仍是适配器边界之后的第三方能力来源。
