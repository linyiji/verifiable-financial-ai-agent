# Owner 运维的评估网关

[English](EVALUATOR_GATEWAY.md)

状态：基础版已实现，仅通过离线验收。**REAL_GATEWAY_DEPLOYMENT = NOT_DEPLOYED.** 不提供自动托管、公开签发、商业计费或 SaaS 认证。向评估者提供实时凭据包前，须审慎完成部署。

现阶段建议投资者和测试员使用[直连供应商 BYOK](LOCAL_DEPLOYMENT.zh-CN.md)：内置的是 API 集成，而不是 API 密钥。使用自己的密钥，或由 Owner 私下提供独立限定权限、可撤销的测试密钥。Docker 安装器仅支持网关模式，不是开箱即用的 BYOK，标准镜像未打包完整证明工具链。

## 边界与配置

独立的 `apps.evaluator_gateway.main:create_app` 工厂持有 Owner BYOK 授权。本地 evaluator LLM/FMP 传输只调用此网关。既有产品保留 Scheme、专家、数据规范化、证明、记忆及自适应恢复契约。

| 已注册路由 | Owner 映射 |
| --- | --- |
| teamorouter-sol | TeamoRouter / TEAMOROUTER_MODEL（默认 gpt-5.6-sol） |
| teamorouter-luna | TeamoRouter / TEAMOROUTER_FALLBACK_MODEL（默认 gpt-5.6-luna） |
| mimo-direct | MiMo / 受治理的 MIMO_CHAT_MODEL（默认 mimo-v2.5） |

Owner 注册信息来自既有路由配置，而非评估者提供的 URL / 模型。在网关上配置全部三条路由。不增加新供应商。只接受有界 FMP `profile`、`income`、`balance`、`cashflow`、`peers`、`quote`、`historical`、`analyst`、`news` 和 `transcript` 操作。参数、单一股票代码身份、分页和历史跨度均按当前适配器契约验证。准确的上游路径参见[契约](../../src/evaluator/contracts.py)中的规范 `PATHS`。

仅暴露 `GET /v1/session`、`POST /v1/model`、`POST /v1/data`。拒绝任意 provider/model/URL/method/upstream-path 字段。结构化模型请求可携带有界消息和输出 schema，但不能改变已注册的网络 / 模型授权。不通过网关暴露工具执行。它不是通用 HTTP 代理。

## 在 Owner 控制的主机上部署

安装 Python 3.11 并执行 `python -m pip install -e '.[postgres]'`。使用隔离的 Owner 源码检出 / 进程，以及受保护环境或私有 dotenv，绝不能使用评估者的检出目录。设置 `VFA_CREDENTIAL_MODE=byok` 和 Owner 的 FMP、TeamoRouter、MiMo 凭据。遵循既有 [BYOK 授权契约](LOCAL_DEPLOYMENT.zh-CN.md)；不要提交配置。网关状态独立于所有研究 PostgreSQL 数据库。

POSIX 部署框架示例（替换为已准备的私有路径）：

```bash
umask 077
export VFA_GATEWAY_STORE=/private/owner-state/evaluation.gateway.sqlite
python -m uvicorn apps.evaluator_gateway.main:create_app --factory --host 127.0.0.1 --port 8020 --no-access-log
```

目录须已存在、仅 Owner 可访问并支持 SQLite 事务。用文件系统权限保护数据库及日志 / 备份；Windows 运维者须设置等价的私有 ACL。应用设置 POSIX 数据库权限 0600，不管理 Windows ACL。不要把此存储放入研究产物或同步到投资者机器。单个主机使用一个持久数据库；尚未实现共享网络文件系统 / 分布式 / 高可用运行。SQLite 原子预留使竞争同一存储的进程串行记账。

实时使用前，在回环服务前配置 Owner 管理的 HTTPS 反向代理。配置证书续期、请求 / 正文 / 速率 / 连接限制、禁用缓存、禁止记录请求 / 响应正文，且代理 / APM 层不得记录 Authorization / 头 / 查询参数。应用输入上限为 512 KB；在边缘限制未认证流量。不要开启 HTTPX/HTTPCore 调试或原始抓包：FMP 在查询参数中认证。内置网关启动会抑制这些传输日志，仅输出系统定义的安全审计元数据。不要将其作为公网调试服务器运行。

上游超时：一次模型 HTTP 尝试，传输超时 60 秒，系统定义的分派总截止时间 80 秒。网关没有隐藏重试或回退。客户端模型截止时间为 90 秒；网关授权丢失 / 分派状态不确定时安全拒绝，不自动重放。已正确分类的真实上游失败保留现有运行时策略资格；系统定义的整体超时在当前策略下仍不可恢复。数据规范化 / 重试仍在产品 FMP 适配器内，每次新传输操作均消耗一次额外预留。

## 私下签发，按标识符撤销

仅 Owner CLI；没有管理 HTTP 或产品 UI 路由。使用真实交互终端。示例默认值：七天、100 次模型操作、500 次数据操作、每分钟 30 次付费操作：

```bash
python scripts/evaluator_admin.py --store /private/owner-state/evaluation.gateway.sqlite issue --gateway-url https://evaluation.example.org --output /private/delivery/investor-a.vfaeval --days 7 --routes teamorouter-sol teamorouter-luna mimo-direct --financial-data --llm-requests 100 --data-requests 500 --requests-per-minute 30
```

`.example.org` URL 仅作示例，不是已部署服务。两次输入高强度随机口令（至少 12 个字符）。CLI 仅打印非秘密凭据 ID；使用排他文件创建，不覆盖先前凭据包。加密凭据包须保留在仓库外并私下分发，密码通过其他渠道传递。签发失败会撤销刚创建的凭据。签发不测试或调用供应商。

```bash
python scripts/evaluator_admin.py --store /private/owner-state/evaluation.gateway.sqlite revoke --credential-id <issued-public-id>
```

撤销后，无需客户端更新，后续 readiness/model/data 授权即失效。已预留且正在执行的操作不会被强制取消。凭据包 / 密码丢失时，撤销并重新签发；不要从存储恢复明文。安全保留存储及备份；旧备份回滚计数器可能重新启用旧额度，因此恢复时须撤销受影响凭据。

## 配额、readiness 与审计

不透明的 256 位随机 bearer 令牌仅保存 SHA-256 验证值，以及 ID、权限范围、有效期、撤销状态、LLM / 数据计数器和固定分钟记账。授权绝不依据评估者提供的 Run/Task ID。每次已接受的模型 / 数据分派在上游工作前预留一次操作；失败调用和断连不退还。拒绝不消耗预留。限制是请求次数，不保证美元 / 费用上限；模型输出 / 正文上限提供额外约束。固定分钟限制可能允许时间边界突发。未实现逐用户账单、积分、充值或支付。费用为 `NOT_OBSERVED`。

Readiness 验证当前凭据状态，返回已配置的允许路由、数据范围、有效期、剩余额度及网关版本。它发出**零次上游请求**，预留**零次付费操作**，不认证供应商健康 / 能力。须使用独立边缘限制保护 readiness，避免滥用。

审计包括网关关联 ID、凭据 ID、操作 / 路由及安全结果 / 拒绝分类。响应暴露系统测得延迟和逻辑供应商 / 模型身份，绝不暴露上游 cookie / 认证 / 诊断头、原始错误或推理内容。不保留提示词用于网关调试。本地研究产物继续遵循既有输出契约。

## 离线验证与限制

```bash
python -m pytest -q tests/evaluator
```

测试使用临时仅哈希存储、生成的假令牌、ASGI/HTTPX mock、临时回环 HTTP 服务器及假模型 / 数据上游。覆盖加密、授权、额度、零费用 readiness、会话启动、受治理的同 Run 恢复和禁止切换的凭据拒绝。不构成托管渗透测试、TLS 部署认证、新付费研究验收或完整 Windows 证明等价性。`--allow-loopback` 仅用于本地假网关开发；绝不能用于分发凭据。

[安全设计](../architecture/EVALUATOR_CREDENTIAL_SECURITY.zh-CN.md) · [评估快速入门](EVALUATOR_QUICKSTART.zh-CN.md)。
