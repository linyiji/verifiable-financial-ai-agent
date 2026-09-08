# 13 — 安全、沙箱与本地运行时 V1

[English](13_SECURITY_SANDBOX_LOCAL_RUNTIME_V1.md)

## 1. MVP 执行目标

```text
SERVER_SANDBOX
```

浏览器不获得任意本地 shell／文件系统访问权。

## 2. 生成代码沙箱

默认拒绝：

```text
Network        DENY
Host FS        DENY
Secrets        DENY
Database       DENY
Cloud metadata DENY
```

允许：

```text
Approved Input READ ONLY
Workspace READ / WRITE
CPU / RAM bounded
Time bounded
Output directory
```

生成代码应接收已物化的 Evidence 快照，而非供应商 API Key。

## 3. 工具权限

Skill 定义允许的工具。

Runtime 强制执行权限。

Agent 不能自行扩大权限。

## 4. 秘密

仅在可信适配器中使用 Secret Manager／环境注入。

绝不将秘密传入生成代码的上下文。

## 5. 工作区生命周期

```text
CREATE
RUNNING
TESTING
VALIDATED
ARCHIVED
PURGED
```

清理前，先将晋升为持久产物的内容复制出去。

## 6. 未来本地运行时

长期产品可以发展为：

```text
Web / Desktop UI
      ↓
Runtime Protocol
 ┌────┴─────┐
Cloud      Local Companion
Runtime    Runtime
```

本地配套程序可以提供：

- 本地文件
- 本地 Python
- 私有数据库
- 本地 MCP
- 私有模型
- 企业数据

## 7. ExecutionTarget 抽象

从第一天就保留：

```text
SERVER_SANDBOX
LOCAL_RUNTIME
```

MVP 仅启用 SERVER_SANDBOX。

不要将业务逻辑硬编码到 Docker 专属路径。

## 8. 未来桌面端

桌面端是 Runtime Client，而非重写研究领域。

相同的：

- Run
- 任务
- 事件
- Graph
- 能力注册表
- 审查（Review）
- 结果

均可复用。
