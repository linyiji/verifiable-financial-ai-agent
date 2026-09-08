# 高级 / 开发者安装

[English](ADVANCED_INSTALLATION.md)

现阶段建议投资者和测试员通过本页及 [BYOK 配置](LOCAL_DEPLOYMENT.zh-CN.md)使用直连供应商的 BYOK 模式。产品内置 API 集成，但不内置 API 密钥。请使用自己的密钥，或由 Owner 私下提供独立限定权限、可撤销的测试密钥。Docker [引导安装](INSTALL_EVALUATOR.zh-CN.md)仅支持网关模式，不是开箱即用的 BYOK 安装器；真实网关状态为 NOT_DEPLOYED，标准镜像也未打包完整证明工具链。

使用 Python 3.11、Node.js 24 及兼容 PostgreSQL 16 的存储。需要完整强制证明的研究依赖 Rust/RISC Zero SDK 3.0.6；生成能力验证需要 Docker。请按照[证明工作区](../../zk/revenue_growth/README.zh-CN.md)说明构建已接受的 host，并保留现有证明门禁。不要设置开发 / 伪造证明标志。

## macOS / Linux shell

在源码检出目录中执行：

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev,postgres]'
cp .env.example .env.local
cd apps/web
npm ci
cd ../..
```

自行准备 PostgreSQL 数据库，并在被忽略的 `.env.local` 中设置 DATABASE_URL。BYOK 模式须明确设置 `VFA_CREDENTIAL_MODE=byok`，私下配置自己的 FMP、TeamoRouter 和 MiMo 凭据。参见[完整 BYOK 配置](LOCAL_DEPLOYMENT.zh-CN.md)。原生 evaluator 模式则须保持供应商密钥为空，设置 `VFA_CREDENTIAL_MODE=evaluator`，并取得 Owner 签发的加密凭据包。

```bash
python scripts/postgresql_migrate.py
./zk/revenue_growth/build-host.sh
# BYOK backend, with VFA_CREDENTIAL_MODE=byok:
python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8010
```

仅在网关已部署且设置 VFA_CREDENTIAL_MODE=evaluator 后，才使用以下可选原生网关
命令替代 BYOK 启动命令：

```bash
python scripts/evaluator_start.py --bundle "/path/to/evaluation.vfaeval"
```

另开终端，在 apps/web 中执行：

```bash
npm exec vite -- --host 127.0.0.1 --port 4173 --strictPort
```

## 高级 Windows 原生 / WSL2

Windows 原生环境使用 `py -3.11 -m venv .venv`，激活 `.\.venv\Scripts\Activate.ps1`（或直接调用其中的 python.exe），使用 `Copy-Item .env.example .env.local`，其余 Python/npm 和 PostgreSQL 设置遵循相同步骤。原生会话启动器接受带引号的 Windows 凭据包路径。

建议通过 WSL2 进行完整证明评估。在管理员 PowerShell 中执行 `wsl --install`，按需重启，使用 `wsl --list --verbose` 验证后进入 `wsl`。在发行版内安装上述版本并执行 Linux 命令。Docker Desktop 集成提供 Docker 访问，但证明工具链仍须安装。参见微软的 [WSL 安装参考](https://learn.microsoft.com/en-us/windows/wsl/install)。不宣称原生 Windows 具备完整证明的等价支持。

不附带 Owner 数据库或历史研究。网关 readiness 检查的是权限，不是供应商能力 / 健康度。新研究可能产生供应商费用；失败是真实结果，不能绕过发布门禁。
