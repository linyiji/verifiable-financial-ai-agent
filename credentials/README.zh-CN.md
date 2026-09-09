# 投资者私有凭证

[English](README.md)

从 Owner 私下获得 `VFA-Investor-Access.vfacred`，复制并重命名为
`<解压仓库>/credentials/active.vfacred`；Windows 路径为
`<解压仓库>\credentials\active.vfacred`。两个文件都不要上传。

完成文档中的平台安装后，运行 `vfa start`，在终端的
`Credential passphrase:` 提示下输入口令，输入不回显。不要将口令写进命令参数、
环境文件或聊天。`vfa doctor` 只表示已配置，不代表真实 Provider 已成功调用。
`vfa stop` 停止该安装的服务并保留研究数据库。

安装器分别记录解压产品目录与私有安装 / 数据库目录。保留选定的产品目录；
切换版本时从新版本目录重新运行平台安装器。只将固定的 `credentials` 目录
以只读方式挂载用于发现凭证。

固定 `active.vfacred` 优先选择 DIRECT_REGISTRY；若显式指定其他凭证，则拒绝
模式冲突。损坏的直连包不会回退到网关或默认密钥。没有直连包时，保留原有
`.vfaeval` 网关发现方式。原生 BYOK 是独立配置，不与直连包合并。
可通过 `--bundle` 显式指定 `.vfacred`；启动不会递归扫描直连凭证文件。

直连包仅包含四个 FMP Key 及既有有界池策略、Bocha Web Search、MiMo
`mimo-v2.5`、TeamoRouter 的 `gpt-5.6-sol` / `gpt-5.6-luna` /
`gpt-5.6-terra`。配置状态是 CONFIGURED，不自动等于 LIVE_PROVEN。

采用 AES-256-GCM、随机 salt / nonce 与固定 scrypt 参数。解密后的凭证仅存在
于进程内存和本地私有 socket 交接，不落地为 Provider `.env` / JSON / 临时文件，
也不进入 Docker 参数或环境配置。本机特权用户可以检查进程内存，不能宣称不可提取。

2026-09-09 本地验收已验证直连包启动、精确镜像身份、打包 Linux RISC Zero
运行时、受治理 Sandbox Broker，以及一次隔离 NVDA Live。这是有限的本地 Alpha
证据，不保证上游 Provider 可用性、Windows 全新机器验收或生产级安全。

Owner 在仓库已配置的 Python 环境内签发：
`python -m src.evaluator.direct_bundle --registry /private/path/provider-registry.local.json --output credentials/active.vfacred`
命令隐藏输入两次，验证加解密往返后才写入密文，拒绝覆盖已有包。明文 staging
仍由 Owner 私有保管，不属于投资者安装内容。
