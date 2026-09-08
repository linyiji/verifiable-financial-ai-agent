# WS-U2 — Generated Capability Sandbox

## Scope

Implemented the Phase 3 generated-code preflight and production sandbox boundary.
No shared domain contracts, enums, settings, dependency declarations, database
configuration, or frontend files were changed.

## Security model

- `GeneratedCodeASTPreflight` is a default-deny fast rejection layer. It permits
  only `decimal`, `math`, `statistics`, `datetime`, `typing`, and `dataclasses`.
- Dynamic imports, file I/O, environment access, network calls, process calls,
  forbidden modules, and dunder traversal are rejected before execution.
- AST inspection is explicitly not represented as the security boundary.
- `SandboxBackend` is the backend protocol; `DockerSandboxBackend` is the real
  generated-code execution boundary. No production in-process backend exists.
- Generated source, generated tests, and the normalized fixture are sent as one
  bounded JSON document over stdin. The Docker argv contains no user code or
  fixture data and has no bind mounts.
- Docker runs with no network, read-only root, UID/GID `65534`, all capabilities
  dropped, no-new-privileges, explicit memory/CPU/PID/open-file/wall-clock
  limits, no IPC namespace, and bytecode writes disabled.
- Secret-like fixture keys are rejected; host environment variables are never
  forwarded to the container.
- Results are a structured JSON object plus the Docker exit code. Timeout and
  malformed-output failures are explicit and cannot be reported as success.

## Integration contract

Generated source must expose `execute(inputs)`. Generated tests must expose
`run_tests(execute, fixture)`. The runner executes the tests and then the
capability with the normalized fixture. Decimal/date/dataclass outputs are
normalized to deterministic JSON forms.

## Verification

See `tests/unit/tooling/test_generated_sandbox.py` for AST and Docker argv
security tests. `tests/integration/test_generated_docker_sandbox.py` performs
real Docker execution, non-root/read-only/network/secret checks, and a real
wall-clock timeout when the pre-pulled `python:3.11-slim` image is available.

## Contract change request

None.
