# 评估安装器契约

[English](EVALUATOR_INSTALLER_DESIGN.md)

状态：源码 / 离线基础版；公开安装器产物为 **PUBLICATION_REQUIRED**。
真实 Owner 网关为 **NOT_DEPLOYED**。可移植测试或本地镜像构建都不意味着已经发布，
也不意味着完成 Windows/macOS 全新环境验收。

投资者和测试员可使用安装器的加密直连凭据包，或使用[原生 BYOK](LOCAL_DEPLOYMENT.zh-CN.md)。产品内置 API 集成；API 密钥只通过私下渠道提供，绝不内置于仓库或前端。可选 Owner 网关仍是独立模式。

## 公共模块与生命周期

薄平台脚本在获得明确的系统安装同意后准备 Docker，验证发布包 SHA-256，并构建共享镜像。
Python 和 Node 在 Docker 内运行；评估者无需单独安装。
共享的 `installer/cli.py` 实现 install、start、stop、status、doctor、update 和 open。
宿主机封装脚本仅提供挂载、终端输入及操作系统默认浏览器功能。

`installer/state.py` 定义了从 SYSTEM_CHECK 到 READY 的 17 个有序阶段。
中断后再次调用会重复执行幂等检查、存储准备和迁移；保存的阶段是观测记录，不是跳过验证的许可。
PostgreSQL 命名卷及生成的本地密码在停止及重复安装后保留。
Compose 项目按安装路径隔离。不提供重置或数据删除功能。

后端与前端宿主机端口仅绑定回环地址。健康检查通过后才会处理固定的浏览器打开信号。
安装会自动进入首次启动。未获得已接受的 evaluator 授权，启动不能进入 READY。

## 凭据与授权

只发现用户选定位置中的加密凭据包。隐藏终端提示将口令交给既有凭据包解析器。
既有零费用 readiness 验证网关授权；路由权限为 ALLOWED，绝不代表实时供应商认证。
不会进行付费供应商探测或研究准入。

公共 CLI 通过 Docker exec 标准输入，将会话令牌发送到 API 容器私有 tmpfs 中的短生命周期 Unix socket。
API 激活前再次执行 readiness。令牌不进入命令参数、环境变量、Compose JSON、状态文件或磁盘缓存。
重启需要重新解锁。宿主机管理员和 Docker 守护进程可以检查进程内存；不宣称秘密无法提取。

独立的本地数据库密码随机生成，并保存在受保护文件中（POSIX 权限 0600；Windows 安装目录仅当前用户 ACL）。
密码以 Compose secret 挂载。安全状态仅包含阶段 / 版本 / 镜像及文件名元数据。
系统定义的安全错误会隐藏原始子进程输出及异常细节。

## 发布完整性与本地打包

默认解析 GitHub 的最新稳定发布，而不是 develop。按约定，显式版本选择使用不可变的已接受标签；
发布产物必须保持由 Owner 控制。`evaluator-manifest.json` 绑定 schema、version、archive URL 和 SHA-256。
解压 / 执行之前验证哈希。这是 HTTPS 加哈希完整性验证，不是密码学发布签名。
基础镜像清单按摘要固定；Python 依赖仍仅受到包版本约束，不是完全可复现的 lockfile 构建。

未来发布者可用 `python -m installer.package --version TAG --output DIRECTORY`
从干净且已提交的工作树创建本地 ZIP / manifest 产物。此命令不会发布或创建标签。
上传产物、发布脚本及验证公开命令是另行授权的工作。
在此之前，请使用[引导安装页](INSTALL_EVALUATOR.zh-CN.md)的仓库相对命令。
明确提供的源码包属于已审阅源码路径，并不宣称已经验证下载的 Release。

## Proof 与 Sandbox 运行时

产品镜像打包已验证的 Linux/amd64 RISC Zero 3.0.6 host、r0vm 与绑定 Guest Method。
启动前验证 Proof 运行时身份，Proof 执行不需要网络。生成能力通过窄化的私有 Unix socket
协议进入 Broker。只有 Broker 挂载 Docker socket；API 与一次性子容器均不挂载。
Broker 固定子镜像，并拒绝调用方指定特权、网络、PID、挂载及设备控制。
既有证明 / 能力发布门禁，以及研究、血缘、记忆和授权契约均未改变。

## 验收边界

可移植测试覆盖公共状态转换、发布校验、凭据失败映射、服务命令、受保护状态及浏览器打开顺序。
Bash 语法与 Windows 源码契约分别检查。
Windows 原生执行，以及全新 macOS 用户走通真实网关 readiness，仍属于待完成的宿主机验证。
Docker 镜像构建 / 导入检查不是全新环境端到端验收。
