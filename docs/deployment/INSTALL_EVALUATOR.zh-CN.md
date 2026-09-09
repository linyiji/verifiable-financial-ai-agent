# 评估者引导安装

[English](INSTALL_EVALUATOR.md)

## 1. 三十秒概览

本安装器支持 `.vfacred` 加密直连凭据，并保留独立的 `.vfaeval` 网关模式。直连模式无需逐个配置 Provider Key 或部署 Owner 网关。Docker 运行时已包含锁定的 RISC Zero 3.0.6 证明 host 与受治理的生成能力沙箱 Broker；开发者仍可使用[原生 BYOK 安装](ADVANCED_INSTALLATION.zh-CN.md)。

私下取得 `VFA-Investor-Access.vfacred`，将其复制为解压仓库的 `credentials/active.vfacred`，再运行以下平台安装命令。安装器准备本地数据库、迁移、后端与前端；直连 readiness 仅验证配置，不发出付费调用。

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

直连凭据固定位置：`<解压仓库>/credentials/active.vfacred`；Windows 为 `<解压仓库>\credentials\active.vfacred`。收到的文件名是 `VFA-Investor-Access.vfacred`，复制时改名即可。安装器保存所选产品目录的非秘密路径，凭据目录仅以只读方式挂载。请保留该解压目录；换版本时从新版本重新执行平台安装器。

固定位置的直连包优先；冲突的显式路径报错。损坏的直连包不会回退。没有直连包时，旧 `.vfaeval` 可继续从 Downloads / Desktop 选择，不递归搜索直连凭据。BYOK 仍为独立原生配置，不与直连包合并。

在隐藏的 `Credential passphrase:` 提示中输入口令。口令不进入命令参数或持久化设置。直连 Provider 密钥只在内存及私有 socket 交接中解密，网关包仍只提供网关授权。详见[凭据范围与安全边界](../../credentials/README.zh-CN.md)。

## 5. 首次启动

安装自动准备数据库、执行迁移、检查权限、启动后端与前端、等待健康检查通过，然后打开 [VFA](http://127.0.0.1:4173)。需要端口 4173 和 8010；发现其他应用占用时返回可操作的错误，而不是停止对方应用。数据库不会发布到宿主机端口。

Readiness 不进行任何付费供应商 / 数据调用，显示的是路由权限，不是供应商健康认证。受限 / 过期 / 已撤销凭据或耗尽的额度不会绕过授权。

**运行时保障：**产品镜像包含已验证的 Linux/amd64 RISC Zero host、锁定的 r0vm 3.0.6 及绑定 Guest Method；Proof 运行不需要网络。生成能力通过私有 Unix socket Broker 进入一次性、禁网、只读根文件系统且受资源限制的子容器。只有 Broker 持有 Docker daemon 权限，API 与子容器均不持有。Proof / Review / Release 门禁保持不变。全新安装不含 Owner 研究历史。

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

Status 报告本地服务状态。Doctor 检查 Docker、已安装版本、数据库、后端、前端、打包 Proof Runtime、受治理 Sandbox Runtime，并执行零费用凭据 readiness。它不会发起 FMP/MiMo/TeamoRouter 付费调用。正常错误显示系统定义的错误码与下一步操作；不打印堆栈或原始服务日志。

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
| PROOF_RUNTIME_NOT_READY / SANDBOX_RUNTIME_NOT_READY | 重新运行 `vfa start`；锁定运行时仍失败时停止并报告错误码。 |

安装器元数据仅包含阶段、版本、镜像及安全凭据文件名。本地数据库密码存于独立受保护运行时文件。CLI 容器需要 Docker 控制权限来管理服务；它是可信安装软件。研究 API 容器不获得 Docker 控制 socket。评估令牌不写入磁盘，而是通过 stdin 和容器内 Unix socket 传递。拥有本地特权的用户可检查内存中的凭据。

## 11. 高级安装

[高级 / BYOK](ADVANCED_INSTALLATION.zh-CN.md) · [Owner 网关](EVALUATOR_GATEWAY.zh-CN.md) · [安装器设计](EVALUATOR_INSTALLER_DESIGN.zh-CN.md)。

平台源码 / 可移植测试不认证 Windows 或 macOS 全新环境 E2E。真实宿主机验证和安装器产物发布仍是独立门禁。

## 独立金融分支与默认对象

独立金融分析并行执行；单项数据不足进入限制记录，不阻断无依赖结论。当前金融扩展采用最多三个并发分支；这不表示所有 Agent Task 都完全并行。每个已校验计算独立持久化。缺少输入的指标记录 INSUFFICIENT_DATA，不产生数值或依赖结论；真正的执行错误仍然失败。Task 可以带结构化限制完成。

默认一般研究的技术分支为 SUPPORTING；Scheme.calculation_requirements 中显式指定的规范能力 ID 为 REQUIRED。既有完整公式集合的 Financial Review / Proof / Release 规则保持不变：任务继续不等于可以发布，缺项仍可能阻止最终 Release。任务详情展示分支状态与可用/所需输入数。当前改动尚未获得新版本实机发布验收，不应宣称 Alpha 2 已发布。

PostgreSQL 迁移后，产品 API 启动会幂等创建空的 NVIDIA / NVDA Research Object，现有同 ticker 对象保持不变。不会初始化任何 Run、Scheme、证据、报告或 Research Memory，也不调用 provider。BYOK / Owner gateway 的凭证和部署边界没有改变。
