# 高级本地部署 — BYOK

[English](LOCAL_DEPLOYMENT.md)

入口：[评估快速入门](EVALUATOR_QUICKSTART.zh-CN.md)。除非另有说明，命令均在仓库根目录执行。

本页说明供开发者使用的原生直连供应商 BYOK。投资者也可使用引导安装器及 Owner 私下提供的加密 `.vfacred` 包。仓库、前端与安装器均不内置 API 密钥。原生 BYOK 需把 `.env.example` 复制为 `.env.local`，设置 `VFA_CREDENTIAL_MODE=byok`、DATABASE_URL，并私下填写 FMP_API_KEY、TEAMOROUTER_API_KEY 和 MIMO_API_KEY。Python 依赖使用 `python -m pip install -e '.[dev,postgres]'`，前端在 `apps/web` 执行 `npm ci`。可选 Owner 网关仍未部署，但加密直连凭据与原生 BYOK 不依赖它。

## 环境契约

| 依赖 | 当前契约 |
| --- | --- |
| Python | 3.11；pyproject 要求 >=3.11,<3.12 |
| Node | 本地前端检查使用 24；通过已提交的 lockfile 执行 npm ci |
| PostgreSQL | 真实产品后端；已接受的本地服务器为 16；迁移前须准备好 |
| FMP | 实时财务证据所必需；须具备对应端点权限 |
| TeamoRouter | 默认主路由 / 综合分析路由及受治理的替代路由 |
| MiMo | 默认 Peer/Research News 配置及首选 Scheme 规划器 |
| RISC Zero | SDK 3.0.6；强制营收增长证明需要构建真实 host |
| Docker | 任务需要时用于生成能力沙箱 / 验证 |
| Langfuse | 可选；未配置凭据时跟踪为空操作 |

源码契约：[settings](../../src/infrastructure/config/settings.py)、[API 组装](../../apps/api/main.py)、[路由组装](../../src/adapters/llm/routes.py)、[恢复组装](../../src/agentic/recovery_composition.py)。

## 配置与授权

Settings 先读取根目录 `.env`，再读取 `.env.local`；进程环境变量优先。`.env.example` 仅作为安全模板使用。默认 SQLite 不是 PostgreSQL 真实产品部署，须明确设置 DATABASE_URL。

受治理的路由 ID：

- teamorouter-sol → TEAMOROUTER_MODEL（默认 gpt-5.6-sol）。
- teamorouter-luna → TEAMOROUTER_FALLBACK_MODEL（默认 gpt-5.6-luna）。
- mimo-direct → MIMO_CHAT_MODEL（既有直连模型 mimo-v2.5 / mimo-v2.5-pro）。

这些是仓库路由配置，不代表供应商在所有情况下均可用。不宣传其他供应商。INCREMENTAL_PROVIDER_ROUTE 和 SPECIALIST_PROVIDER_ROUTES 用于选择已注册路由。基础 URL 变量用于配置适配器；MiMo 直连授权特意限制为 HTTPS api.xiaomimimo.com/v1，并拒绝 URL 中的凭据 / 查询参数 / 片段。它不是任意代理路由。

MiMo 直连授权默认使用注入的 BYOK Settings。可选 MIMO_AUTHORITY_FILE 指向包含 MIMO_API_KEY、MIMO_BASE_URL、MIMO_CHAT_MODEL 的私有文件。明确配置的文件若缺失或不完整，会以拒绝方式安全失败，而非静默回退到其他凭据。不需要开发者主目录路径。

FMP 支持主密钥或配置好的连续编号密钥池。供应商密钥应保留在服务端。前端变量绝不能包含秘密。Vite 在 apps/web 中运行，不读取仓库根目录 dotenv 文件：默认 API 已为 :8010；如需覆盖，在启动 / 构建前于前端 shell 中导出 VITE_API_BASE_URL。

## 命令与端口

```bash
# Provision the evaluator database separately, then apply the repository chain:
PYTHONPATH=. python scripts/postgresql_migrate.py
# Build real proof host after installing its toolchain:
./zk/revenue_growth/build-host.sh
# Writable product; starts the runtime worker:
PYTHONPATH=. uvicorn apps.api.main:app --host 127.0.0.1 --port 8010
# In a second terminal, from apps/web:
npm exec vite -- --host 127.0.0.1 --port 4173 --strictPort
```

后端健康检查 GET /health 返回 status ok。健康检查仅表示启动 / 存活，不证明远端服务或完整付费 Run 可用。前端使用 127.0.0.1:4173；当前 CORS 允许 127.0.0.1 上的 4173/4174。未设计访问控制之前，不要将此 Alpha 暴露到公网。

持久状态分布在 PostgreSQL、ARTIFACT_ROOT 和 WORKSPACE_ROOT。须将对应产物与数据库一同保留；只复制数据库可能导致精确产物链接不可用。备份及密钥分发仍由评估者 / 运维者负责。

## 常见失败

- 数据库连接 / 迁移失败：检查已准备的数据库、用户权限、URL 转义后的密码、asyncpg 安装及当前虚拟环境。
- MiMo 授权不可用 / 不完整：在根配置或明确指定且可读的私有文件中提供密钥；旧的 Owner 本地路径不可移植。
- 供应商认证 / 不支持的模型：检查权限和路由 ID。不要编造替代供应商名称。
- FMP 端点缺失 / 禁止访问：检查财务数据订阅与密钥池配置。
- CORS / fetch 失败：使用准确的回环主机名 / 端口，而不是被静默重新分配的 Vite 端口。
- 证明 host 缺失或无效：使用已提交的封装脚本构建；不要设置 RISC0_DEV_MODE 或 RISC0_SKIP_BUILD。强制证明失败会阻止发布。
- Research Object/Memory 为空：新克隆不包含生产种子数据；须创建研究并获得真实发布。
- 没有受治理的恢复候选：缺失 / 未知能力证据不自动构成许可。全新状态下的恢复行为可能不同于已接受的历史示例。
- 写操作返回 403：严格只读验收入口有意禁止运行研究；只有经授权的本地执行才应使用可写启动器。

## 验证边界

原生 BYOK 仍适用于开发者。面向投资者的 Docker 引导安装器使用单独的加密直连凭据包，并打包 Proof 与受治理 Sandbox 运行时；不会把密钥放进仓库、前端或子沙箱。参见[本地部署验收](../validation/LOCAL_DEPLOYMENT_ACCEPTANCE.zh-CN.md)。
