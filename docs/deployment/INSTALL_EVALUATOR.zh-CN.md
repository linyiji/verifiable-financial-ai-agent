# 评估者引导安装

[English](INSTALL_EVALUATOR.md)

## 1. 三十秒概览

**当前投资者 / 测试员建议：**采用[直连供应商 BYOK](LOCAL_DEPLOYMENT.zh-CN.md)及[原生环境安装](ADVANCED_INSTALLATION.zh-CN.md)。产品内置 API 集成，不内置 API 密钥。使用自己的密钥，或由 Owner 私下提供独立限定权限、可撤销的测试密钥。本页描述仅支持网关模式的 Docker 安装器基础版，不是开箱即用的 BYOK 安装器。

从 Owner 私下取得安装器源码包和一个加密 `.vfaeval` 凭据包。解压源码包，运行以下平台命令并按提示操作。Docker Desktop 提供本地运行时；无需单独安装数据库或语言工具。安装器创建本地存储、迁移其独立数据库、检查网关权限并启动真实产品。首次安装成功后打开默认浏览器。

**交付状态：**安装器源码基础版；公开安装器 URL 为 **PUBLICATION_REQUIRED**。发布仓库源码不等于发布已验收的安装器专用资产和引导 URL。不要把可变的 develop URL 替换进下载后执行的命令。公开安装器将解析已接受的 GitHub Release，并在执行前验证其 SHA-256 软件包。

**网关状态：**真实 Owner 网关为 **NOT_DEPLOYED**。可以准备软件安装；网关模式的 Owner 付费实时研究仍为 **BLOCKED_BY_GATEWAY_DEPLOYMENT**。这不阻止独立配置 BYOK 测试 Key。有效凭据包必须指向另行部署的网关。

## 2. Windows

在解压后的源码包目录中，用 PowerShell 执行：

```powershell
& .\scripts\install-evaluator.ps1
```

如果缺少 Docker Desktop，安装器会先询问，再使用 Windows Package Manager 安装。完成 Docker 设置提示。如果要求重启，请重启一次后再次执行相同命令。如果 Docker 已安装但未运行，请启动后重试。常规评估路径始终在 PowerShell 内，无需手动配置 WSL 发行版或 Ubuntu。

每用户安装位于 LocalAppData → Verifiable Financial Agent，由当前用户 ACL 保护。如企业 PowerShell 策略阻止脚本，请使用获批的 IT 流程；安装器不会更改机器执行策略。

## 3. macOS

在解压后的源码包目录中，用 Terminal 执行：

```bash
bash scripts/install-evaluator.sh
```

安装器检测 Docker Desktop。若缺失，会提供官方安装指南。完成 Docker 安装后重新运行相同命令。绝不静默执行特权安装。应用状态位于当前用户下的 Library → Application Support → Verifiable Financial Agent。

首次准备镜像会下载依赖，可能耗时数分钟。私有构建详情保留在安装目录的 logs 下。软件包运行时镜像按摘要固定。无需手动安装 Python、Node 或 PostgreSQL。

## 4. 凭据放在哪里

将加密文件放入 Downloads 或 Desktop。只有一个候选时自动选择；有多个时显示文件名供选择。没有候选时，放入 Downloads 后按 Enter，或输入路径。安装器内部，这些目录显示为 `/credentials/downloads` 和 `/credentials/desktop`；手动选文件时须使用其中一个路径。不会自动搜索或挂载其他目录。

在隐藏终端提示处输入口令。口令绝不会成为命令参数、环境变量或保存设置。供应商密钥保留在 Owner 网关上。不要把口令放在凭据包旁边。重新打开会话需要再次解锁凭据包。

## 5. 首次启动

安装自动准备数据库、执行迁移、检查权限、启动后端与前端、等待健康检查通过，然后打开 [VFA](http://127.0.0.1:4173)。需要端口 4173 和 8010；发现其他应用占用时返回可操作的错误，而不是停止对方应用。数据库不会发布到宿主机端口。

Readiness 不进行任何付费供应商 / 数据调用，显示的是路由权限，不是供应商健康认证。受限 / 过期 / 已撤销凭据或耗尽的额度不会绕过授权。

**标准模式限制：**容器运行真实产品，证明 / 发布策略不变。它未打包经过认证的 RISC Zero host，也不向研究 Agents 暴露 Docker 控制 socket。支持浏览及受支持的有限工作流；需要证明或生成能力验证的任务，不能通过此标准镜像获得合法发布。不会伪造既有证明，也不会关闭门禁。`vfa start --full-proof` 当前返回 `FULL_PROOF_UNAVAILABLE`；已接受的完整证明镜像交付前，受发布门禁约束的完整研究须使用[高级安装](ADVANCED_INSTALLATION.zh-CN.md)。全新安装不含 Owner 研究历史。

## 6. 后续启动

首次安装后另开终端，以加载每用户 PATH：

```text
vfa start
```

按提示解锁凭据包。服务重启，健康检查通过后打开浏览器。使用 `vfa start --no-open` 可不打开浏览器。`vfa open` 会重新打开健康运行的产品。

## 7. 更新

```text
vfa update
```

更新解析包含 evaluator manifest 的最新稳定、已接受 GitHub Release，验证 SHA-256，构建选定运行时，执行迁移并重启。技术评估者可用 `vfa update --version <accepted-release-tag>`；允许显式选择预发布版本。绝不跟随 develop。在安装器产物发布之前，更新返回 `PUBLICATION_REQUIRED`。迁移失败会保留数据并返回错误，不会尝试破坏性回滚。升级前请备份 Docker 研究卷及匹配的产物。

## 8. 停止

```text
vfa stop
```

只停止本次安装的服务。研究存储与卷保留。不提供重置 / 删除数据命令。

## 9. 状态与诊断

```text
vfa status
vfa doctor
```

Status 报告本地服务状态。Doctor 检查 Docker、已安装版本、服务状态，并在解锁凭据包时执行相同的零费用网关 readiness。它不测试 FMP/MiMo/TeamoRouter。正常错误显示系统定义的错误码与下一步操作；不打印堆栈或原始服务日志。

## 10. 故障排查

| 代码 | 下一步操作 |
| --- | --- |
| DOCKER_NOT_INSTALLED / DOCKER_NOT_RUNNING | 安装 / 启动 Docker Desktop 后重试相同命令。 |
| REBOOT_REQUIRED | Windows 重启一次后重新执行原安装器。 |
| PUBLICATION_REQUIRED | 向 Owner 索取已审阅源码包或已发布的安装器 Release。 |
| DOWNLOAD_FAILED / INTEGRITY_FAILED | 检查 GitHub 连通性；校验和失败时联系 Owner，不要执行软件包。 |
| PORT_4173_IN_USE / PORT_8010_IN_USE | 自行关闭占用端口的应用后运行 vfa start。 |
| DATABASE_START_FAILED / MIGRATION_FAILED | 运行 vfa doctor；检查 Docker 存储。数据会保留。 |
| NO_EVALUATOR_CREDENTIAL / INVALID_EVALUATOR_CREDENTIAL | 将签发文件放入 Downloads；检查口令；运行 vfa start。 |
| GATEWAY_NOT_DEPLOYED / GATEWAY_UNREACHABLE | 请 Owner 部署 / 检查网关；可用后运行 vfa start。 |
| CREDENTIAL_EXPIRED / CREDENTIAL_REVOKED / QUOTA_EXHAUSTED | 请 Owner 解决授权问题；运行 vfa start。 |
| HEALTH_TIMEOUT | 运行 vfa doctor。不要关闭财务 / 发布门禁。 |
| FULL_PROOF_UNAVAILABLE | 使用高级完整技术部署。 |

安装器元数据仅包含阶段、版本、镜像及安全凭据文件名。本地数据库密码存于独立受保护运行时文件。CLI 容器需要 Docker 控制权限来管理服务；它是可信安装软件。研究 API 容器不获得 Docker 控制 socket。评估令牌不写入磁盘，而是通过 stdin 和容器内 Unix socket 传递。拥有本地特权的用户可检查内存中的凭据。

## 11. 高级安装

[高级 / BYOK](ADVANCED_INSTALLATION.zh-CN.md) · [Owner 网关](EVALUATOR_GATEWAY.zh-CN.md) · [安装器设计](EVALUATOR_INSTALLER_DESIGN.zh-CN.md)。

平台源码 / 可移植测试不认证 Windows 或 macOS 全新环境 E2E。真实宿主机验证和安装器产物发布仍是独立门禁。
