# 营收增长率 RISC Zero 证明

[English](README.md)

此工作区将 `revenue_growth_v1` 证明为精确的既约有理数：

```text
(current_revenue_minor - prior_revenue_minor) / prior_revenue_minor
```

已审查的语义前置条件为 `prior_revenue_minor > 0`。前期营收为零或负数时，
以稳定的财务校验原因 `REVENUE_GROWTH_PRIOR_REVENUE_MUST_BE_POSITIVE`
按失败关闭原则处理；不会生成增长百分比或证明。

guest 仅提交公式 id、已编译镜像 id、输入承诺、预期输出承诺和规范化有理数结果。
输入承诺绑定 run、计算、公式、能力、实现哈希、有序证据引用、规范化整数输入，
以及预期输出承诺。

## 安全边界

- RISC Zero SDK／构建 crate 固定为 `3.0.6`。
- host 启用 `risc0-zkvm/disable-dev-mode`。
- 构建包装器和运行时 host 只要发现 `RISC0_DEV_MODE` 存在就会拒绝执行。
- `prove` 创建 receipt，但不声称已完成验证。
- `verify` 作为独立进程运行，固定已编译镜像 id，执行 receipt 的密码学验证，
  并将已验证 journal 与独立推导的预期值进行比较。
- Python 适配器直接执行预构建的 host 二进制文件，绝不会通过 shell 调用 Cargo。

## 构建与执行

先安装官方 `rzup` 工具链。然后运行唯一的构建入口：

```sh
./zk/revenue_growth/build-host.sh
```

生成的可执行文件为：

```text
zk/revenue_growth/target/release/revenue-growth-proof-host
```

支持的命令为 `image-id`、`prove --input ... --receipt ...` 和
`verify --input ... --receipt ...`。每条成功执行的命令会向 stdout 输出一个 JSON 对象。
错误发送至 stderr，并以非零状态退出。
