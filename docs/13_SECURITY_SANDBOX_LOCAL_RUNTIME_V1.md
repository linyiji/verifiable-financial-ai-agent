# 13 — Security, Sandbox & Local Runtime V1

[简体中文](13_SECURITY_SANDBOX_LOCAL_RUNTIME_V1.zh-CN.md)

## 1. MVP execution target

```text
SERVER_SANDBOX
```

Browser does not get arbitrary local shell / filesystem access.

## 2. Generated Code Sandbox

Default deny:

```text
Network        DENY
Host FS        DENY
Secrets        DENY
Database       DENY
Cloud metadata DENY
```

Allow:

```text
Approved Input READ ONLY
Workspace READ / WRITE
CPU / RAM bounded
Time bounded
Output directory
```

Generated code should receive materialized Evidence snapshots, not provider API keys.

## 3. Tool permissions

Skill defines allowed tools.

Runtime enforces permissions.

Agent cannot expand permissions itself.

## 4. Secrets

Use Secret Manager / environment injection only in trusted adapters.

Never pass secrets into generated code context.

## 5. Workspace lifecycle

```text
CREATE
RUNNING
TESTING
VALIDATED
ARCHIVED
PURGED
```

Durable promoted artifacts copied out before purge.

## 6. Future Local Runtime

Long-term product can become:

```text
Web / Desktop UI
      ↓
Runtime Protocol
 ┌────┴─────┐
Cloud      Local Companion
Runtime    Runtime
```

Local companion may provide:

- local files
- local Python
- private DB
- local MCP
- private model
- enterprise data

## 7. ExecutionTarget abstraction

From day one:

```text
SERVER_SANDBOX
LOCAL_RUNTIME
```

MVP only enables SERVER_SANDBOX.

Do not hard-code business logic to Docker-specific paths.

## 8. Future Desktop

Desktop is a Runtime Client, not a rewrite of the research domain.

Same:

- Run
- Tasks
- events
- Graph
- Capability Registry
- Review
- Result

can be reused.
