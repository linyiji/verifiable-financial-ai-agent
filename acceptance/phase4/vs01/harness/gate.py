"""Fail-closed orchestration primitives for the Phase 4 VS01 acceptance gate.

The module owns acceptance infrastructure only.  It starts external product
processes, provisions a disposable PostgreSQL database, verifies public evidence,
and aggregates specialist control fragments.  It imports no product module and
never supplies business responses or runtime events.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import signal
import subprocess
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

VS01_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
FRAGMENT_ROOT = VS01_ROOT / "manifest" / "fragments"
MANIFEST_PATH = VS01_ROOT / "PHASE4_VS01_ACCEPTANCE_MANIFEST.json"
RESULT_JSON_NAME = "PHASE4_VS01_ACCEPTANCE_RESULT.json"
RESULT_MARKDOWN_NAME = "PHASE4_VS01_ACCEPTANCE_RESULT.md"

CONTRACT_REVISION = "764d76132cfac13d47125e031b280b7894eb249f"
SOURCE_PARENT = "4b6721b6db433aae300f94750e1a405b6b450501"
SOURCE_TREE = "35c47508ed65220c26620f5ec4bdd14cb798480d"
CONTRACT_SET_SHA256 = "0bf6c824d553847fa129a429715aedc36a30601a97421f4447cdd3f6d6a81741"
V17_R2_SHA256 = "fc184034e448e85190aa4cfd92b89e90b9f258307632920daa8d8cd73c600c19"
FINAL_FREEZE_DECISION_SHA256 = "8b7fd1a7002224f056fe18ea7250dc39024f4dfb8e3e105152cb8356d29cb191"
REQUESTED_BRANCH = "phase4/vs01-acceptance"
AUTHORIZED_BRANCH = "p4-vs01-acceptance"
AUTHORIZED_REMOTE_BRANCH = "origin/p4-vs01-acceptance"
NEXT_EXACT_ACTION = "PARENT_WAIT_FOR_A_B_C_AND_X_THEN_EXECUTE_WAVE1_VS01_INTEGRATION_GATE"

ALLOWED_CONTROL_STATUSES = frozenset(
    {
        "READY",
        "BLOCKED_BY_A",
        "BLOCKED_BY_B",
        "BLOCKED_BY_C",
        "BLOCKED_BY_PARENT",
        "PASS",
        "FAIL",
    }
)
REQUIRED_CONTROL_FIELDS = frozenset(
    {
        "control_id",
        "contract_source",
        "contract_section_ref",
        "owner_dependency",
        "layer",
        "positive_negative",
        "test_implementation_path",
        "precondition",
        "expected_result",
        "actual_result",
        "status",
    }
)
SECRET_NAME_PATTERN = re.compile(
    r"(?:authorization|api[_-]?key|bearer|secret|password|private[_-]?key|cookie|"
    r"public[_-]?key|refresh[_-]?token|access[_-]?token|prompt|"
    r"chain[_-]?of[_-]?thought|scratch(?:pad|[_-]?reasoning)|"
    r"(?:analysis|reasoning)[_-]?trace|thought[_-]?process|model[_-]?reasoning|"
    r"raw[_-]?provider[_-]?payload|provider[_-]?raw)",
    re.IGNORECASE,
)
SECRET_VALUE_PATTERNS = (
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{8,}", re.IGNORECASE),
    re.compile(r"\b(?:sk|pk|api)[-_][A-Za-z0-9_-]{16,}", re.IGNORECASE),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)
HIDDEN_REASONING_PATTERN = re.compile(
    r"(?:hidden chain[- ]of[- ]thought|chain[- ]of[- ]thought|scratch reasoning|"
    r"scratchpad|internal reasoning|system prompt|reasoning trace|analysis trace|"
    r"thought process|model reasoning|raw provider payload)",
    re.IGNORECASE,
)
INTERNAL_PATH_PATTERN = re.compile(r"(?:/Users/|/home/|[A-Za-z]:\\|artifact://)")
STACK_TRACE_PATTERN = re.compile(
    r"(?:Traceback \(most recent call last\)|\bat\s+\S+\s+\([^\n)]*:\d+:\d+\))",
    re.IGNORECASE,
)
PROVIDER_SECRET_NAME_PATTERN = re.compile(
    r"(?:(?:qiji|mimo|teamorouter|fmp|langfuse)[_-]?(?:api[_-]?)?"
    r"(?:key|secret|token|password)|(?:key|secret|token|password)[_-]?"
    r"(?:qiji|mimo|teamorouter|fmp|langfuse))",
    re.IGNORECASE,
)
FORBIDDEN_COMMAND_PATTERN = re.compile(
    r"(?:mock|fixture|demo|testserver|fake[-_ ]?backend)", re.IGNORECASE
)
SENSITIVE_CONFIG_KEY = re.compile(
    r"(?:password|secret|token|authorization|cookie|api[_-]?key|dsn|database_url)",
    re.IGNORECASE,
)


class GateError(RuntimeError):
    """The acceptance gate cannot establish a required fact."""


class GateConfigurationError(GateError):
    """Integrated configuration is absent, unsafe, or cannot prove reality."""


class PublicSurfaceViolation(AssertionError):
    """A captured public product surface contains forbidden material."""


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GateConfigurationError(f"invalid JSON document: {path.name}") from exc
    if not isinstance(value, dict):
        raise GateConfigurationError(f"JSON root must be an object: {path.name}")
    return value


def load_control_fragments(fragment_root: Path = FRAGMENT_ROOT) -> list[dict[str, Any]]:
    paths = sorted(fragment_root.glob("*.json"))
    if not paths:
        raise GateConfigurationError("no VS01 control fragments were found")
    fragments: list[dict[str, Any]] = []
    seen_fragments: set[str] = set()
    seen_controls: set[str] = set()
    for path in paths:
        fragment = _read_json_object(path)
        if fragment.get("schema_version") != "phase4-vs01-acceptance-fragment/v1":
            raise GateConfigurationError(f"unsupported fragment schema: {path.name}")
        fragment_id = fragment.get("fragment_id")
        if not isinstance(fragment_id, str) or not fragment_id:
            raise GateConfigurationError(f"fragment_id is missing: {path.name}")
        if fragment_id in seen_fragments:
            raise GateConfigurationError(f"duplicate fragment_id: {fragment_id}")
        seen_fragments.add(fragment_id)
        controls = fragment.get("controls")
        if not isinstance(controls, list) or not controls:
            raise GateConfigurationError(f"fragment controls are missing: {fragment_id}")
        for control in controls:
            if not isinstance(control, dict) or not REQUIRED_CONTROL_FIELDS <= set(control):
                raise GateConfigurationError(f"malformed control in {fragment_id}")
            control_id = control["control_id"]
            if not isinstance(control_id, str) or not control_id.startswith("VS01-"):
                raise GateConfigurationError(f"invalid control_id in {fragment_id}")
            if control_id in seen_controls:
                raise GateConfigurationError(f"duplicate control_id: {control_id}")
            if control["status"] not in ALLOWED_CONTROL_STATUSES:
                raise GateConfigurationError(f"invalid status for {control_id}")
            seen_controls.add(control_id)
        fragments.append(fragment)
    return fragments


def aggregate_manifest(
    fragments: Sequence[Mapping[str, Any]],
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    controls = sorted(
        (dict(control) for fragment in fragments for control in fragment["controls"]),
        key=lambda control: control["control_id"],
    )
    ids = [control["control_id"] for control in controls]
    if len(ids) != len(set(ids)):
        raise GateConfigurationError("aggregate contains duplicate control IDs")
    counts = Counter(control["status"] for control in controls)
    dependencies: list[dict[str, Any]] = []
    for fragment in fragments:
        for dependency in fragment.get("dependencies", []):
            if isinstance(dependency, dict):
                dependencies.append(dict(dependency))
    return {
        "schema_version": "phase4-vs01-acceptance-manifest/v1",
        "generated_at": generated_at or utc_now(),
        "scope": "VS01_ACCEPTANCE_HARNESS_ONLY",
        "authority": {
            "contract_revision": CONTRACT_REVISION,
            "approved_source_parent": SOURCE_PARENT,
            "approved_source_tree": SOURCE_TREE,
            "phase4_contract_set_sha256": CONTRACT_SET_SHA256,
            "v17_r2_canonical_sha256": V17_R2_SHA256,
            "final_freeze_decision_sha256": FINAL_FREEZE_DECISION_SHA256,
        },
        "fragment_ids": sorted(str(fragment["fragment_id"]) for fragment in fragments),
        "dependencies": dependencies,
        "controls": controls,
        "summary": {
            "total": len(controls),
            "by_status": dict(sorted(counts.items())),
            "integrated_execution_required": sum(
                control["layer"] != "HARNESS_SELF_TEST" for control in controls
            ),
        },
    }


def materialize_manifest(
    destination: Path = MANIFEST_PATH,
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    manifest = aggregate_manifest(load_control_fragments(), generated_at=generated_at)
    write_json(destination, manifest)
    return manifest


def safe_command(command: Any, *, component: str) -> tuple[str, ...]:
    if not isinstance(command, list) or not command:
        raise GateConfigurationError(f"{component}.command must be a non-empty JSON array")
    if not all(isinstance(part, str) and part for part in command):
        raise GateConfigurationError(f"{component}.command contains a non-string/empty argument")
    joined = " ".join(command)
    if FORBIDDEN_COMMAND_PATTERN.search(joined):
        raise GateConfigurationError(f"{component}.command names a mock/Demo/fixture surface")
    # Commands are executed as argv with ``shell=False``.  Product identity is
    # established from managed-process ownership plus the frozen public HTTP
    # behavior, not from framework or script names: gunicorn, a compiled binary,
    # or a container entry point are all legitimate implementations.
    if Path(command[0]).name.lower() in {
        "bash",
        "cmd",
        "cmd.exe",
        "fish",
        "powershell",
        "pwsh",
        "sh",
        "zsh",
    }:
        raise GateConfigurationError(f"{component}.command cannot use a shell wrapper")
    return tuple(command)


def safe_relative_cwd(value: Any, *, component: str) -> Path:
    if not isinstance(value, str) or not value:
        raise GateConfigurationError(f"{component}.cwd must be a non-empty repository path")
    raw = Path(value)
    candidate = raw.resolve() if raw.is_absolute() else (REPOSITORY_ROOT / raw).resolve()
    try:
        candidate.relative_to(REPOSITORY_ROOT)
    except ValueError as exc:
        raise GateConfigurationError(f"{component}.cwd escapes the repository") from exc
    if not candidate.is_dir():
        raise GateConfigurationError(f"{component}.cwd does not exist")
    if VS01_ROOT == candidate or VS01_ROOT in candidate.parents:
        raise GateConfigurationError(f"{component} cannot launch an acceptance harness as product")
    return candidate


def validate_safe_extra_env(value: Any, *, component: str) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise GateConfigurationError(f"{component}.extra_env must be an object")
    result: dict[str, str] = {}
    for name, content in value.items():
        if not isinstance(name, str) or not isinstance(content, str):
            raise GateConfigurationError(f"{component}.extra_env must contain strings")
        if SENSITIVE_CONFIG_KEY.search(name):
            raise GateConfigurationError(
                f"{component}.extra_env cannot contain secret/DSN values; inherit them by name"
            )
        try:
            scan_public_surface({"configured_value": content})
        except PublicSurfaceViolation as exc:
            raise GateConfigurationError(
                f"{component}.extra_env contains a forbidden secret/path value"
            ) from exc
        parsed = urlsplit(content)
        if parsed.scheme and (parsed.username is not None or parsed.password is not None):
            raise GateConfigurationError(
                f"{component}.extra_env cannot contain credential-bearing URLs"
            )
        result[name] = content
    return result


def _absolute_http_url(value: Any, *, label: str) -> str:
    if not isinstance(value, str):
        raise GateConfigurationError(f"{label} must be a URL")
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise GateConfigurationError(f"{label} must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password:
        raise GateConfigurationError(f"{label} must not contain credentials")
    if parsed.query or parsed.fragment:
        raise GateConfigurationError(f"{label} must not contain a query or fragment")
    return value.rstrip("/")


def _service_base_url(value: Any, *, label: str) -> str:
    result = _absolute_http_url(value, label=label)
    if urlsplit(result).path not in {"", "/"}:
        raise GateConfigurationError(f"{label} must be an origin-level service URL")
    return result


def _api_base_url(value: Any, *, label: str) -> str:
    result = _absolute_http_url(value, label=label)
    if urlsplit(result).path != "/api":
        raise GateConfigurationError(f"{label} must use the frozen /api route prefix")
    return result


def validate_integrated_config(value: Mapping[str, Any]) -> dict[str, Any]:
    if value.get("schema_version") != "phase4-vs01-runner-config/v1":
        raise GateConfigurationError("unsupported integrated runner config schema")
    result = dict(value)
    x_delivery_sha = value.get("x_delivery_sha")
    if (
        not isinstance(x_delivery_sha, str)
        or not re.fullmatch(r"[0-9a-f]{40}", x_delivery_sha)
        or x_delivery_sha == "0" * 40
    ):
        raise GateConfigurationError(
            "x_delivery_sha must be the reviewed 40-hex commit reachable from the pushed X branch"
        )
    result["x_delivery_sha"] = x_delivery_sha
    for component in ("backend", "frontend", "frontend_unavailable"):
        raw = value.get(component)
        if not isinstance(raw, dict):
            raise GateConfigurationError(f"{component} configuration is required")
        checked = dict(raw)
        checked["command"] = safe_command(raw.get("command"), component=component)
        checked["cwd"] = safe_relative_cwd(raw.get("cwd"), component=component)
        checked["url"] = _service_base_url(raw.get("url"), label=f"{component}.url")
        checked["extra_env"] = validate_safe_extra_env(raw.get("extra_env"), component=component)
        result[component] = checked
    if (
        urlsplit(result["frontend"]["url"]).netloc
        == urlsplit(result["frontend_unavailable"]["url"]).netloc
    ):
        raise GateConfigurationError("frontend origins must be distinct")
    primary_api_base = _api_base_url(
        value.get("frontend_api_base_url"), label="frontend_api_base_url"
    )
    unavailable_api_base = _api_base_url(
        value.get("frontend_unavailable_api_base_url"),
        label="frontend_unavailable_api_base_url",
    )
    if primary_api_base == unavailable_api_base:
        raise GateConfigurationError("frontend API bases must be distinct")
    result["frontend_api_base_url"] = primary_api_base
    result["frontend_unavailable_api_base_url"] = unavailable_api_base
    unavailable = _service_base_url(
        value.get("unavailable_backend_url"), label="unavailable_backend_url"
    )
    result["unavailable_backend_url"] = unavailable
    if primary_api_base != f"{result['backend']['url']}/api":
        raise GateConfigurationError(
            "frontend_api_base_url must be the managed backend URL plus frozen /api"
        )
    if unavailable_api_base != f"{unavailable}/api":
        raise GateConfigurationError(
            "frontend_unavailable_api_base_url must be the verified unreachable URL plus /api"
        )
    browser = value.get("browser")
    if not isinstance(browser, dict):
        raise GateConfigurationError("browser configuration is required")
    browser_command = browser.get("command")
    if browser_command != ["npm", "run", "test:real"]:
        raise GateConfigurationError(
            "browser.command must invoke the tracked VS01 real Playwright entry point exactly"
        )
    browser_cwd_raw = browser.get("cwd", "acceptance/phase4/vs01/browser")
    if not isinstance(browser_cwd_raw, str) or not browser_cwd_raw:
        raise GateConfigurationError("browser.cwd must name the tracked browser harness")
    browser_cwd = Path(browser_cwd_raw)
    if not browser_cwd.is_absolute():
        browser_cwd = (REPOSITORY_ROOT / browser_cwd).resolve()
    else:
        browser_cwd = browser_cwd.resolve()
    expected_browser_cwd = (VS01_ROOT / "browser").resolve()
    if browser_cwd != expected_browser_cwd or not browser_cwd.is_dir():
        raise GateConfigurationError("browser.cwd must be the tracked VS01 browser harness")
    node24_command = browser.get("node24_command")
    expected_node24_command = [
        "npx",
        "--offline",
        "--yes",
        "--package=node@24.8.0",
        "--call",
    ]
    if node24_command != expected_node24_command:
        raise GateConfigurationError(
            "browser.node24_command must be the documented offline Node 24 launcher"
        )
    result["browser"] = {
        **browser,
        "command": tuple(browser_command),
        "node24_command": tuple(node24_command),
        "cwd": browser_cwd,
    }
    capture = value.get("sse_scenario_capture")
    if not isinstance(capture, dict):
        raise GateConfigurationError("sse_scenario_capture configuration is required")
    driver_path = capture.get("driver_path")
    if (
        not isinstance(driver_path, str)
        or not driver_path
        or Path(driver_path).is_absolute()
        or ".." in Path(driver_path).parts
        or driver_path.startswith("acceptance/phase4/vs01/")
    ):
        raise GateConfigurationError(
            "sse_scenario_capture.driver_path must be a repository-relative non-harness path"
        )
    capture_command = safe_command(
        capture.get("command"),
        component="sse_scenario_capture",
    )
    if capture_command.count(driver_path) != 1:
        raise GateConfigurationError(
            "sse_scenario_capture.command must name the tracked driver exactly once"
        )
    capture_timeout = capture.get("timeout_seconds", 900)
    if (
        isinstance(capture_timeout, bool)
        or not isinstance(capture_timeout, (int, float))
        or capture_timeout <= 0
        or capture_timeout > 3600
    ):
        raise GateConfigurationError("sse_scenario_capture.timeout_seconds must be in (0, 3600]")
    result["sse_scenario_capture"] = {
        **capture,
        "driver_path": driver_path,
        "command": capture_command,
        "cwd": safe_relative_cwd(capture.get("cwd", "."), component="sse_scenario_capture"),
        "timeout_seconds": float(capture_timeout),
    }
    postgres = value.get("postgres")
    if not isinstance(postgres, dict):
        raise GateConfigurationError("postgres configuration is required")
    admin_env = postgres.get("admin_url_env", "VS01_POSTGRES_ADMIN_URL")
    if not isinstance(admin_env, str) or not admin_env:
        raise GateConfigurationError("postgres.admin_url_env must be an environment-variable name")
    prefix = postgres.get("database_prefix", "vfas_vs01_")
    if not isinstance(prefix, str) or not re.fullmatch(r"[a-z][a-z0-9_]{3,30}_", prefix):
        raise GateConfigurationError("postgres.database_prefix is not a safe generated prefix")
    migrate = postgres.get("migration_command")
    if (
        not isinstance(migrate, list)
        or not migrate
        or not all(isinstance(part, str) and part for part in migrate)
    ):
        raise GateConfigurationError("postgres.migration_command must be a non-empty array")
    result["postgres"] = {
        **postgres,
        "admin_url_env": admin_env,
        "database_prefix": prefix,
        "migration_command": tuple(migrate),
    }
    for alias in ("object_a", "object_b"):
        raw = value.get(alias)
        if not isinstance(raw, dict):
            raise GateConfigurationError(f"{alias} is required")
        required = {"symbol", "company_name", "exchange", "currency"}
        if required - set(raw):
            raise GateConfigurationError(f"{alias} lacks required Object fields")
    for name in ("goal_a", "goal_b", "as_of"):
        if not isinstance(value.get(name), str) or not value[name]:
            raise GateConfigurationError(f"{name} is required")
    return result


def load_integrated_config(path: Path) -> dict[str, Any]:
    return validate_integrated_config(_read_json_object(path))


def _postgres_parts(url: str) -> tuple[Any, str]:
    parsed = urlsplit(url)
    base_scheme = parsed.scheme.split("+", 1)[0]
    if base_scheme not in {"postgres", "postgresql"} or not parsed.hostname:
        raise GateConfigurationError("PostgreSQL admin URL must use postgres[ql][+driver]")
    database = unquote(parsed.path.lstrip("/"))
    if not database:
        raise GateConfigurationError("PostgreSQL admin URL must name an administrative database")
    return parsed, database


def redact_url(url: str) -> str:
    parsed, database = _postgres_parts(url)
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    return f"postgresql://<redacted>@{host}{port}/{database}"


def _libpq_env(url: str) -> dict[str, str]:
    parsed, database = _postgres_parts(url)
    # The supplied admin URL is the sole connection authority for this run.  Clear
    # libpq variables that could otherwise be inherited by ``run_command`` and
    # silently redirect psql to a service, host, database, user, or credential.
    result = {
        name: ""
        for name in (
            "PGAPPNAME",
            "PGCHANNELBINDING",
            "PGCONNECT_TIMEOUT",
            "PGDATABASE",
            "PGGSSENCMODE",
            "PGHOST",
            "PGHOSTADDR",
            "PGKRBSRVNAME",
            "PGOPTIONS",
            "PGPASSFILE",
            "PGPASSWORD",
            "PGPORT",
            "PGREQUIREPEER",
            "PGSERVICE",
            "PGSERVICEFILE",
            "PGSSLCERT",
            "PGSSLCRL",
            "PGSSLCRLDIR",
            "PGSSLKEY",
            "PGSSLMODE",
            "PGSSLROOTCERT",
            "PGTARGETSESSIONATTRS",
            "PGUSER",
        )
    }
    result.update(
        {
            "PGHOST": parsed.hostname or "",
            "PGDATABASE": database,
            "PGAPPNAME": "vfas-vs01-acceptance",
        }
    )
    if parsed.port is not None:
        result["PGPORT"] = str(parsed.port)
    if parsed.username is not None:
        result["PGUSER"] = unquote(parsed.username)
    if parsed.password is not None:
        result["PGPASSWORD"] = unquote(parsed.password)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    ssl_mode = query.get("sslmode", query.get("ssl"))
    if ssl_mode is not None:
        result["PGSSLMODE"] = ssl_mode
    return result


def application_database_url(
    admin_url: str,
    database_name: str,
    *,
    application_scheme: str | None = None,
) -> str:
    parsed, _ = _postgres_parts(admin_url)
    scheme = application_scheme or parsed.scheme
    if not re.fullmatch(r"postgres(?:ql)?(?:\+[a-zA-Z0-9_.-]+)?", scheme):
        raise GateConfigurationError("PostgreSQL application URL scheme is invalid")
    # Preserve the administrator's transport query verbatim.  Driver-specific
    # query translation belongs to the reviewed integrated configuration, not to
    # this implementation-neutral acceptance harness.
    query = urlencode(parse_qsl(parsed.query, keep_blank_values=True))
    return urlunsplit((scheme, parsed.netloc, f"/{quote(database_name, safe='')}", query, ""))


@dataclass(frozen=True)
class CommandObservation:
    returncode: int
    duration_seconds: float
    stdout: str = field(repr=False)
    stderr: str = field(repr=False)


def run_command(
    command: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str] | None = None,
    timeout_seconds: float = 120.0,
    inherit_environment: bool = True,
) -> CommandObservation:
    started = time.monotonic()
    base_environment = (
        dict(os.environ)
        if inherit_environment
        else {
            name: os.environ[name]
            for name in ("PATH", "LANG", "LC_ALL", "TMPDIR", "SYSTEMROOT")
            if name in os.environ
        }
    )
    try:
        process = subprocess.run(
            list(command),
            cwd=cwd,
            env={**base_environment, **dict(env or {})},
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GateError(f"command could not complete: {Path(command[0]).name}") from exc
    return CommandObservation(
        process.returncode,
        round(time.monotonic() - started, 3),
        process.stdout,
        process.stderr,
    )


@dataclass
class PostgreSQLIsolation:
    admin_url: str = field(repr=False)
    database_prefix: str
    psql_binary: str = "psql"
    database_name: str | None = None
    server_version_num: int | None = None
    created: bool = False
    connections_blocked: bool = False
    last_block_evidence: dict[str, Any] | None = field(default=None, init=False)

    def _psql(self, sql: str, *, database_url: str | None = None) -> str:
        active_url = database_url or self.admin_url
        observation = run_command(
            [
                self.psql_binary,
                "--no-psqlrc",
                "--set",
                "ON_ERROR_STOP=1",
                "--tuples-only",
                "--no-align",
                "--command",
                sql,
            ],
            cwd=REPOSITORY_ROOT,
            env=_libpq_env(active_url),
            timeout_seconds=30,
        )
        if observation.returncode != 0:
            raise GateError("PostgreSQL command failed (diagnostics withheld to protect DSN)")
        return observation.stdout.strip()

    def preflight(self) -> dict[str, Any]:
        _, admin_database = _postgres_parts(self.admin_url)
        rows = self._psql("SHOW server_version_num;").splitlines()
        if len(rows) != 1 or not rows[0].isdigit():
            raise GateError("PostgreSQL did not return one numeric server_version_num")
        version = int(rows[0])
        if version // 10_000 != 16:
            raise GateError("integrated VS01 requires PostgreSQL server major version 16")
        self.server_version_num = version
        return {
            "backend": "postgresql",
            "server_major": 16,
            "server_version_num": version,
            "admin_database": admin_database,
            "credential_exposed": False,
        }

    def create(self, *, application_scheme: str | None = None) -> str:
        if self.created or self.database_name is not None:
            raise GateError("PostgreSQL isolation may be created only once")
        if self.server_version_num is None:
            self.preflight()
        suffix = f"{int(time.time())}_{secrets.token_hex(5)}"
        database_name = f"{self.database_prefix}{suffix}"
        if not re.fullmatch(r"[a-z][a-z0-9_]{8,63}", database_name):
            raise GateError("generated PostgreSQL database identifier is unsafe")
        self._psql(f"CREATE DATABASE \"{database_name}\" TEMPLATE template0 ENCODING 'UTF8';")
        self.database_name = database_name
        self.created = True
        app_url = application_database_url(
            self.admin_url,
            database_name,
            application_scheme=application_scheme,
        )
        observed = self._psql("SELECT current_database();", database_url=app_url)
        if observed != database_name:
            raise GateError("isolated PostgreSQL connection resolved to a different database")
        return app_url

    def _checked_database_name(self) -> str:
        database_name = self.database_name
        if not self.created or database_name is None:
            raise GateError("isolated PostgreSQL database has not been created")
        if not database_name.startswith(self.database_prefix) or not re.fullmatch(
            r"[a-z][a-z0-9_]{8,63}", database_name
        ):
            raise GateError("isolated PostgreSQL database is outside the generated namespace")
        return database_name

    def block_connections(self) -> dict[str, Any]:
        """Make the disposable database unreachable and terminate its sessions.

        This creates a causal black-box probe: a managed Product request that was
        successful immediately beforehand must stop succeeding while this exact
        database is unavailable.  All SQL runs through the separate admin DB.
        """

        database_name = self._checked_database_name()
        if self.connections_blocked:
            raise GateError("isolated PostgreSQL connections are already blocked")
        self._psql(f'ALTER DATABASE "{database_name}" WITH ALLOW_CONNECTIONS false;')
        # Mark the state immediately so a later verification error is still
        # recoverable by the runner's finally path.
        self.connections_blocked = True
        terminated_text = self._psql(
            "SELECT count(*) FROM pg_stat_activity "
            f"WHERE datname = '{database_name}' AND pid <> pg_backend_pid() "
            "AND pg_terminate_backend(pid);"
        )
        allowed = self._psql(
            f"SELECT datallowconn::text FROM pg_database WHERE datname = '{database_name}';"
        )
        active_text = self._psql(
            "SELECT count(*) FROM pg_stat_activity "
            f"WHERE datname = '{database_name}' AND pid <> pg_backend_pid();"
        )
        if not terminated_text.isdigit() or allowed != "false" or active_text != "0":
            raise GateError("isolated PostgreSQL connection block could not be verified")
        evidence = {
            "database_name_sha256": hashlib.sha256(database_name.encode()).hexdigest(),
            "allow_connections": False,
            "terminated_sessions": int(terminated_text),
            "remaining_sessions": 0,
        }
        self.last_block_evidence = evidence
        return dict(evidence)

    def restore_connections(self) -> dict[str, Any]:
        database_name = self._checked_database_name()
        if not self.connections_blocked:
            raise GateError("isolated PostgreSQL connections are not blocked")
        self._psql(f'ALTER DATABASE "{database_name}" WITH ALLOW_CONNECTIONS true;')
        allowed = self._psql(
            f"SELECT datallowconn::text FROM pg_database WHERE datname = '{database_name}';"
        )
        if allowed != "true":
            raise GateError("isolated PostgreSQL connection restoration could not be verified")
        self.connections_blocked = False
        return {
            "database_name_sha256": hashlib.sha256(database_name.encode()).hexdigest(),
            "allow_connections": True,
        }

    def drop(self) -> None:
        database_name = self.database_name
        if not self.created or database_name is None:
            return
        if not database_name.startswith(self.database_prefix) or not re.fullmatch(
            r"[a-z][a-z0-9_]{8,63}", database_name
        ):
            raise GateError("refusing to drop a database outside the generated VS01 namespace")
        self._psql(f'DROP DATABASE "{database_name}" WITH (FORCE);')
        self.created = False
        self.connections_blocked = False

    def safe_evidence(self) -> dict[str, Any]:
        return {
            "backend": "postgresql",
            "server_major": 16 if self.server_version_num else None,
            "server_version_num": self.server_version_num,
            "isolated_database_created": self.created,
            "connections_blocked": self.connections_blocked,
            "causal_block_exercised": self.last_block_evidence is not None,
            "database_name_sha256": hashlib.sha256(
                (self.database_name or "").encode("utf-8")
            ).hexdigest()
            if self.database_name
            else None,
            "database_prefix": self.database_prefix,
            "credentials_recorded": False,
        }


@dataclass
class ManagedService:
    name: str
    command: tuple[str, ...]
    cwd: Path
    url: str
    health_path: str = "/"
    extra_env: Mapping[str, str] = field(default_factory=dict, repr=False)
    process: subprocess.Popen[bytes] | None = field(default=None, init=False, repr=False)
    boundary_ids: list[str] = field(default_factory=list, init=False)

    def start(self, *, inherited_env: Mapping[str, str], timeout_seconds: float = 45) -> str:
        if self.process is not None and self.process.poll() is None:
            raise GateError(f"{self.name} is already running")
        assert_url_unreachable(f"{self.url}{self.health_path}")
        boundary = f"{self.name}-{secrets.token_hex(12)}"
        try:
            self.process = subprocess.Popen(
                list(self.command),
                cwd=self.cwd,
                env={**os.environ, **dict(inherited_env), **dict(self.extra_env)},
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as exc:
            raise GateError(f"{self.name} could not start") from exc
        self.boundary_ids.append(boundary)
        try:
            wait_for_http(
                f"{self.url}{self.health_path}",
                timeout_seconds=timeout_seconds,
                process=self.process,
            )
            if self.process.poll() is not None:
                raise GateError(f"{self.name} exited after another process answered health")
        except Exception:
            self.stop()
            raise
        return boundary

    def stop(self, *, timeout_seconds: float = 10) -> None:
        process = self.process
        if process is None or process.poll() is not None:
            self.process = None
            return
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=timeout_seconds)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=5)
        finally:
            self.process = None

    def restart(self, *, inherited_env: Mapping[str, str], timeout_seconds: float = 45) -> str:
        previous_count = len(self.boundary_ids)
        self.stop()
        boundary = self.start(inherited_env=inherited_env, timeout_seconds=timeout_seconds)
        if len(self.boundary_ids) != previous_count + 1:
            raise GateError("restart did not cross a managed process boundary")
        return boundary

    def safe_evidence(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "url": self.url,
            "health_path": self.health_path,
            "managed_process": True,
            "start_count": len(self.boundary_ids),
            "process_boundary_ids": list(self.boundary_ids),
            "command_sha256": hashlib.sha256("\0".join(self.command).encode()).hexdigest(),
        }


def wait_for_http(
    url: str,
    *,
    timeout_seconds: float,
    process: subprocess.Popen[bytes] | None = None,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_status: int | None = None
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            raise GateError("managed product process exited before health readiness")
        try:
            request = Request(url, headers={"Accept": "application/json"})
            with urlopen(request, timeout=1.5) as response:  # noqa: S310
                last_status = response.status
                if 200 <= response.status < 400:
                    return
        except HTTPError as exc:
            last_status = exc.code
        except (URLError, TimeoutError, OSError):
            pass
        time.sleep(0.15)
    suffix = f" (last HTTP status {last_status})" if last_status is not None else ""
    raise GateError(f"service health deadline expired{suffix}")


def assert_url_unreachable(url: str) -> None:
    try:
        with urlopen(Request(url), timeout=0.5):  # noqa: S310
            pass
    except (URLError, TimeoutError, OSError):
        return
    except HTTPError as exc:
        raise GateConfigurationError("unavailable backend URL resolved to an HTTP service") from exc
    raise GateConfigurationError("unavailable backend URL is reachable")


def scan_public_surface(value: Any, *, sentinel: str | None = None) -> dict[str, Any]:
    violations: list[str] = []

    def visit(node: Any, path: str) -> None:
        if isinstance(node, Mapping):
            for key, child in node.items():
                key_text = str(key)
                if SECRET_NAME_PATTERN.search(key_text) or PROVIDER_SECRET_NAME_PATTERN.search(
                    key_text
                ):
                    violations.append(f"forbidden public field at {path}.{key_text}")
                visit(child, f"{path}.{key_text}")
        elif isinstance(node, (list, tuple)):
            for index, child in enumerate(node):
                visit(child, f"{path}[{index}]")
        elif isinstance(node, str):
            if sentinel and sentinel in node:
                violations.append(f"acceptance secret sentinel exposed at {path}")
            if any(pattern.search(node) for pattern in SECRET_VALUE_PATTERNS):
                violations.append(f"credential-like text exposed at {path}")
            if HIDDEN_REASONING_PATTERN.search(node):
                violations.append(f"hidden reasoning text exposed at {path}")
            if INTERNAL_PATH_PATTERN.search(node):
                violations.append(f"internal path/reference exposed at {path}")
            if STACK_TRACE_PATTERN.search(node):
                violations.append(f"stack trace exposed at {path}")

    visit(value, "$public")
    if violations:
        raise PublicSurfaceViolation("; ".join(sorted(set(violations))))
    return {
        "secret_leakage": 0,
        "hidden_cot_exposed": False,
        "internal_path_exposed": False,
        "scanned_sha256": sha256_json(value),
    }


def parse_playwright_result(path: Path) -> dict[str, Any]:
    report = _read_json_object(path)
    stats = report.get("stats")
    if not isinstance(stats, dict):
        raise GateError("Playwright result lacks stats")
    expected = stats.get("expected")
    unexpected = stats.get("unexpected")
    if not isinstance(expected, int) or not isinstance(unexpected, int):
        raise GateError("Playwright result stats are malformed")
    flaky = stats.get("flaky", 0)
    skipped = stats.get("skipped", 0)
    if expected != 6 or unexpected != 0 or flaky != 0 or skipped != 0:
        raise GateError("the exact six real VS01 browser scenarios did not all pass")
    return {
        "expected": expected,
        "unexpected": unexpected,
        "flaky": flaky,
        "skipped": skipped,
    }


def apply_outcomes(
    manifest: Mapping[str, Any],
    outcomes: Mapping[str, Mapping[str, Any]],
    *,
    integrated: bool,
) -> list[dict[str, Any]]:
    controls: list[dict[str, Any]] = []
    for raw in manifest["controls"]:
        control = dict(raw)
        outcome = outcomes.get(control["control_id"])
        if outcome is not None:
            status = outcome.get("status")
            if status not in {"PASS", "FAIL"}:
                raise GateError(f"invalid executed outcome for {control['control_id']}")
            control["status"] = status
            control["actual_result"] = outcome.get("actual_result")
            if "evidence" in outcome:
                control["evidence"] = outcome["evidence"]
        elif integrated and control["layer"] != "HARNESS_SELF_TEST":
            control["status"] = "FAIL"
            control["actual_result"] = "REQUIRED_EVIDENCE_ABSENT"
        controls.append(control)
    return controls


def _git_text(*arguments: str, repository: Path = REPOSITORY_ROOT) -> str | None:
    try:
        process = subprocess.run(
            ["git", *arguments],
            cwd=repository,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return None
    if process.returncode != 0:
        return None
    return process.stdout.strip()


def _remote_ref_sha(
    ref: str,
    *,
    repository: Path = REPOSITORY_ROOT,
    remote: str = "origin",
) -> str | None:
    """Resolve one exact remote ref without trusting a local tracking ref."""

    output = _git_text("ls-remote", "--refs", remote, ref, repository=repository)
    if not output:
        return None
    matches: list[str] = []
    for line in output.splitlines():
        fields = line.split()
        if len(fields) == 2 and fields[1] == ref and re.fullmatch(r"[0-9a-f]{40}", fields[0]):
            matches.append(fields[0])
    return matches[0] if len(matches) == 1 else None


def collect_delivery_metadata(repository: Path = REPOSITORY_ROOT) -> dict[str, Any]:
    """Measure delivery/scope state without treating it as Product evidence."""

    head = _git_text("rev-parse", "HEAD", repository=repository)
    branch = _git_text("branch", "--show-current", repository=repository)
    upstream = _git_text(
        "rev-parse",
        "--abbrev-ref",
        "--symbolic-full-name",
        "@{upstream}",
        repository=repository,
    )
    local_tracking_sha = _git_text("rev-parse", "@{upstream}", repository=repository)
    branch_ref = f"refs/heads/{branch}" if branch else None
    remote_branch_sha = _remote_ref_sha(branch_ref, repository=repository) if branch_ref else None
    source_parent_is_ancestor = (
        _git_text("merge-base", "--is-ancestor", SOURCE_PARENT, "HEAD", repository=repository)
        is not None
    )
    source_parent_tree = _git_text("rev-parse", f"{SOURCE_PARENT}^{{tree}}", repository=repository)
    changed_text = _git_text("diff", "--name-only", SOURCE_PARENT, repository=repository)
    untracked_text = _git_text("ls-files", "--others", "--exclude-standard", repository=repository)
    changed_paths = {
        line
        for text in (changed_text, untracked_text)
        if text
        for line in text.splitlines()
        if line
    }
    owned_prefix = "acceptance/phase4/vs01/"
    outside_owned_scope = sorted(
        path for path in changed_paths if not path.startswith(owned_prefix)
    )
    phase4_sha = _remote_ref_sha("refs/heads/phase4", repository=repository)
    main_sha = _remote_ref_sha("refs/heads/main", repository=repository)
    proposals = [path for path in changed_paths if "SEMANTIC_PATCH_PROPOSAL" in Path(path).name]
    clean = _git_text("status", "--porcelain", "--untracked-files=all", repository=repository) == ""
    remote_branch = f"origin/{branch}" if branch and remote_branch_sha else None
    return {
        "requested_branch": REQUESTED_BRANCH,
        "actual_branch": branch,
        "authorized_branch": AUTHORIZED_BRANCH,
        "branch_substitution_authorized": branch == AUTHORIZED_BRANCH,
        "configured_upstream": upstream,
        "remote_branch": remote_branch,
        "expected_remote_branch": AUTHORIZED_REMOTE_BRANCH,
        "base_sha": SOURCE_PARENT,
        "source_parent_is_ancestor": source_parent_is_ancestor,
        "source_parent_tree": source_parent_tree,
        "source_parent_tree_matches_authority": source_parent_tree == SOURCE_TREE,
        "branch_sha_at_execution": head,
        # Result bundles are written below the ignored ``out/`` tree, so a clean
        # pushed execution can name the exact immutable harness revision without
        # creating a self-referential result commit.
        "final_branch_sha": head,
        "final_branch_sha_resolution": "EXACT_HARNESS_REVISION_AT_EXECUTION",
        "delivery_snapshot_semantics": "PUSHED_CLEAN_HARNESS_REVISION_AT_EXECUTION",
        "local_tracking_sha_at_execution": local_tracking_sha,
        "remote_branch_sha_at_execution": remote_branch_sha,
        "upstream_sha_at_execution": remote_branch_sha,
        "branch_pushed": bool(head and head == remote_branch_sha),
        "worktree_clean_at_execution": clean,
        "branch_pushed_and_clean_at_execution": bool(head and head == remote_branch_sha and clean),
        "worktree": str(repository.resolve()),
        "worktree_portable": "$HOME/Verifiable_Financial_Agent_System_phase4/vs01-acceptance",
        "changed_path_count": len(changed_paths),
        "outside_acceptance_owned_scope": outside_owned_scope,
        "product_source_files_modified": bool(outside_owned_scope),
        "parent_only_files_modified": bool(outside_owned_scope),
        "parent_semantic_patch_proposals": len(proposals),
        "phase4_integration_branch_sha": phase4_sha,
        "phase4_integration_branch_modified_from_base": (
            None if phase4_sha is None else phase4_sha != SOURCE_PARENT
        ),
        "main_sha": main_sha,
        "main_modified_from_base": None if main_sha is None else main_sha != SOURCE_PARENT,
    }


def collect_integrated_x_delivery_metadata(
    x_delivery_sha: str,
    repository: Path = REPOSITORY_ROOT,
) -> dict[str, Any]:
    """Bind Parent's acceptance subtree to a reviewed pushed CodeX X revision.

    Integrated execution legitimately occurs on Parent's branch with Product
    changes.  Those changes cannot waive the independent harness provenance
    check: the configured X revision must be reachable from the exact remote X
    ref, contain acceptance-only changes from the authorized source parent, and
    have the same ``acceptance/phase4/vs01`` tree as Parent's current checkout.
    """

    if not isinstance(x_delivery_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", x_delivery_sha):
        raise GateError("integrated X delivery SHA is invalid")
    remote_x_sha = _remote_ref_sha(
        "refs/heads/p4-vs01-acceptance",
        repository=repository,
    )
    remote_reachable = bool(
        remote_x_sha
        and _git_text(
            "merge-base",
            "--is-ancestor",
            x_delivery_sha,
            remote_x_sha,
            repository=repository,
        )
        is not None
    )
    source_parent_is_ancestor = (
        _git_text(
            "merge-base",
            "--is-ancestor",
            SOURCE_PARENT,
            x_delivery_sha,
            repository=repository,
        )
        is not None
    )
    source_parent_tree = _git_text(
        "rev-parse",
        f"{SOURCE_PARENT}^{{tree}}",
        repository=repository,
    )
    changed_text = _git_text(
        "diff",
        "--name-only",
        SOURCE_PARENT,
        x_delivery_sha,
        repository=repository,
    )
    changed_paths = tuple(line for line in (changed_text or "").splitlines() if line)
    acceptance_only = bool(changed_paths) and all(
        path.startswith("acceptance/phase4/vs01/") for path in changed_paths
    )
    x_subtree = _git_text(
        "rev-parse",
        f"{x_delivery_sha}:acceptance/phase4/vs01",
        repository=repository,
    )
    parent_subtree = _git_text(
        "rev-parse",
        "HEAD:acceptance/phase4/vs01",
        repository=repository,
    )
    subtree_matches = bool(x_subtree and parent_subtree and x_subtree == parent_subtree)
    verified = bool(
        remote_reachable
        and source_parent_is_ancestor
        and source_parent_tree == SOURCE_TREE
        and acceptance_only
        and subtree_matches
    )
    return {
        "x_delivery_sha": x_delivery_sha,
        "remote_x_branch": AUTHORIZED_REMOTE_BRANCH,
        "remote_x_branch_sha_at_execution": remote_x_sha,
        "x_delivery_sha_reachable_from_remote": remote_reachable,
        "x_source_parent_is_ancestor": source_parent_is_ancestor,
        "x_source_parent_tree_matches_authority": source_parent_tree == SOURCE_TREE,
        "x_changed_path_count": len(changed_paths),
        "x_acceptance_only_scope": acceptance_only,
        "x_acceptance_subtree_sha": x_subtree,
        "parent_acceptance_subtree_sha": parent_subtree,
        "parent_acceptance_subtree_matches_x": subtree_matches,
        "x_delivery_binding_verified": verified,
    }


def _named_readiness(manifest: Mapping[str, Any], harness_ready: bool) -> dict[str, str]:
    ids = {control["control_id"] for control in manifest["controls"]}

    def ready(*required: str) -> str:
        return "READY" if harness_ready and set(required) <= ids else "NOT_READY"

    return {
        "PRODUCTION_FIXTURE_FALLBACK_TEST": ready("VS01-FE-010", "VS01-FE-011"),
        "ONE_CONFIRM_ONE_RUN_TEST": ready("VS01-BE-005", "VS01-FE-005"),
        "AUTO_START_TEST": ready("VS01-BE-006", "VS01-FE-007"),
        "EXACT_RUN_SSE_TEST": ready("VS01-SSE-001", "VS01-SSE-005"),
        "STALE_STREAM_TEST": ready("VS01-REC-008"),
        "SELF_CORRECTION_INVARIANT_TEST": ready("VS01-DYN-003"),
        "CONTROLLED_REPLAN_TEST": ready(
            "VS01-DYN-004", "VS01-DYN-005", "VS01-DYN-006", "VS01-DYN-007"
        ),
    }


def _security_summary(
    outcomes: Mapping[str, Mapping[str, Any]],
    *,
    integrated: bool,
    environment: Mapping[str, Any],
) -> dict[str, Any]:
    secret = outcomes.get("VS01-SEC-001")
    cot = outcomes.get("VS01-SEC-002")
    statuses = {item.get("status") for item in (secret, cot) if isinstance(item, Mapping)}
    scans_complete = (
        environment.get("api_sse_public_surface_scan_completed") is True
        and environment.get("browser_public_surface_scan_completed") is True
    )
    if not integrated or secret is None or cot is None:
        status = "NOT_RUN"
    elif not scans_complete:
        status = "INCOMPLETE"
    elif secret.get("status") == "PASS" and cot.get("status") == "PASS":
        status = "PASS"
    elif "FAIL" in statuses:
        status = "FAIL"
    else:
        status = "INCOMPLETE"
    if not integrated:
        # CodeX preparation did not expose any Product surface.  Preserve the
        # required zero-leakage handoff fields, but scope them explicitly to
        # this acceptance-harness delivery; Product attestation remains NOT_RUN.
        secret_leakage: int | None = 0
        hidden_cot_exposed: bool | None = False
        attestation_scope = "ACCEPTANCE_HARNESS_DELIVERY_ONLY"
    else:
        secret_leakage = 0 if status == "PASS" else None
        hidden_cot_exposed = False if status == "PASS" else None
        attestation_scope = "INTEGRATED_PRODUCT_PUBLIC_SURFACES" if status == "PASS" else "NONE"
    return {
        "integrated_public_surface_scan": status,
        "attestation_scope": attestation_scope,
        "secret_leakage": secret_leakage,
        "hidden_cot_exposed": hidden_cot_exposed,
    }


def _self_test_delivery_failures(delivery: Mapping[str, Any]) -> list[str]:
    failures: list[str] = []
    head = delivery.get("branch_sha_at_execution")
    remote_sha = delivery.get("remote_branch_sha_at_execution")
    predicates = (
        (
            "AUTHORIZED_BRANCH",
            delivery.get("actual_branch") == AUTHORIZED_BRANCH
            and delivery.get("branch_substitution_authorized") is True,
        ),
        (
            "AUTHORIZED_REMOTE_BRANCH",
            delivery.get("remote_branch") == AUTHORIZED_REMOTE_BRANCH,
        ),
        (
            "AUTHORIZED_SOURCE_PARENT_AND_TREE",
            delivery.get("source_parent_is_ancestor") is True
            and delivery.get("source_parent_tree_matches_authority") is True,
        ),
        (
            "REMOTE_BRANCH_AT_EXECUTION_HEAD",
            isinstance(head, str)
            and isinstance(remote_sha, str)
            and head == remote_sha
            and delivery.get("branch_pushed") is True,
        ),
        (
            "WORKTREE_CLEAN_AT_EXECUTION",
            delivery.get("worktree_clean_at_execution") is True
            and delivery.get("branch_pushed_and_clean_at_execution") is True,
        ),
        (
            "ACCEPTANCE_ONLY_SCOPE",
            delivery.get("outside_acceptance_owned_scope") == []
            and delivery.get("product_source_files_modified") is False
            and delivery.get("parent_only_files_modified") is False,
        ),
        (
            "ORIGIN_PHASE4_UNCHANGED_FROM_BASE",
            delivery.get("phase4_integration_branch_modified_from_base") is False,
        ),
        (
            "ORIGIN_MAIN_UNCHANGED_FROM_BASE",
            delivery.get("main_modified_from_base") is False,
        ),
    )
    for name, passed in predicates:
        if not passed:
            failures.append(name)
    return failures


def _integrated_x_delivery_failures(delivery: Mapping[str, Any]) -> list[str]:
    predicates = (
        (
            "X_SHA_REACHABLE_FROM_AUTHORIZED_REMOTE",
            delivery.get("remote_x_branch") == AUTHORIZED_REMOTE_BRANCH
            and delivery.get("x_delivery_sha_reachable_from_remote") is True,
        ),
        (
            "X_AUTHORIZED_SOURCE_PARENT_AND_TREE",
            delivery.get("x_source_parent_is_ancestor") is True
            and delivery.get("x_source_parent_tree_matches_authority") is True,
        ),
        (
            "X_ACCEPTANCE_ONLY_SCOPE",
            delivery.get("x_acceptance_only_scope") is True,
        ),
        (
            "PARENT_ACCEPTANCE_SUBTREE_MATCHES_X",
            delivery.get("parent_acceptance_subtree_matches_x") is True,
        ),
        (
            "X_DELIVERY_BINDING_VERIFIED",
            delivery.get("x_delivery_binding_verified") is True,
        ),
    )
    return [name for name, passed in predicates if not passed]


def _next_action(
    *,
    integrated: bool,
    integrated_pass: bool,
    codex_x_pass: bool,
    controls: Sequence[Mapping[str, Any]],
    harness_checks: Sequence[Mapping[str, Any]],
    required_reality: Mapping[str, Any],
    reality: Mapping[str, Any],
    findings: Sequence[Mapping[str, Any]],
    delivery_failures: Sequence[str],
) -> str:
    if not integrated:
        if codex_x_pass:
            return NEXT_EXACT_ACTION
        failures = [
            f"HARNESS_CHECK:{check.get('check_id', 'UNKNOWN')}"
            for check in harness_checks
            if check.get("status") != "PASS"
        ]
        if not harness_checks:
            failures.append("HARNESS_CHECK:NO_CHECKS_RECORDED")
        failures.extend(f"DELIVERY:{name}" for name in delivery_failures)
        return (
            "RESOLVE_HARNESS_OR_DELIVERY_FAILURES["
            + ",".join(failures or ["UNSPECIFIED"])
            + "]_THEN_RERUN_CODEX_X_SELF_TEST"
        )

    if integrated_pass:
        return (
            "PARENT_RECORD_VS01_GATE_PASS;"
            "PHASE5_AND_QIJI_REMAIN_UNAUTHORIZED_WITHOUT_SEPARATE_AUTHORIZATION"
        )

    blockers = [
        f"CONTROL:{control.get('control_id', 'UNKNOWN')}"
        for control in controls
        if control.get("status") != "PASS"
    ]
    blockers.extend(
        f"REALITY:{key}"
        for key, expected in required_reality.items()
        if reality.get(key) != expected
    )
    blockers.extend(
        f"FINDING:{finding.get('finding_id', 'UNKNOWN')}"
        for finding in findings
        if finding.get("blocking_vs01") is True and finding.get("status", "OPEN") != "RESOLVED"
    )
    blockers.extend(f"DELIVERY:{name}" for name in delivery_failures)
    return (
        "RESOLVE_BLOCKING_VS01_FINDINGS["
        + ",".join(blockers or ["UNSPECIFIED"])
        + "]_THEN_RERUN_SAME_INTEGRATED_COMMAND;"
        "PHASE5_AND_QIJI_REMAIN_UNAUTHORIZED"
    )


def build_result(
    manifest: Mapping[str, Any],
    outcomes: Mapping[str, Mapping[str, Any]],
    *,
    mode: str,
    harness_checks: Sequence[Mapping[str, Any]],
    environment: Mapping[str, Any] | None = None,
    findings: Sequence[Mapping[str, Any]] = (),
    delivery: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if mode not in {"HARNESS_SELF_TEST", "REAL_VS01_EXECUTION"}:
        raise ValueError("unknown VS01 result mode")
    integrated = mode == "REAL_VS01_EXECUTION"
    controls = apply_outcomes(manifest, outcomes, integrated=integrated)
    harness_ready = bool(harness_checks) and all(
        check.get("status") == "PASS" for check in harness_checks
    )
    integrated_pass = (
        integrated and harness_ready and all(control["status"] == "PASS" for control in controls)
    )
    # A real pass is impossible without the independently recorded reality predicates.
    reality = dict(environment or {})
    required_reality = {
        "real_backend": True,
        "real_frontend": True,
        "real_sse": True,
        "real_postgresql_16": True,
        "postgresql_causal_binding": True,
        "managed_backend_restart": True,
        "mock_business_responses": False,
        "candidate_tracked_clean_at_start": True,
        "runtime_sse_capture_bound": True,
        "api_sse_public_surface_scan_completed": True,
        "browser_public_surface_scan_completed": True,
        "x_delivery_binding_verified": True,
    }
    if integrated and any(
        reality.get(key) != expected for key, expected in required_reality.items()
    ):
        integrated_pass = False
    if integrated and any(
        finding.get("blocking_vs01") is True and finding.get("status", "OPEN") != "RESOLVED"
        for finding in findings
    ):
        integrated_pass = False
    counts = Counter(control["status"] for control in controls)
    manifest_counts = Counter(control["status"] for control in manifest["controls"])
    delivery_state = dict(delivery or collect_delivery_metadata())
    fragment_ids = set(manifest.get("fragment_ids", []))
    specialist_fragments = {
        "X1_BACKEND_ACCEPTANCE_HARNESS": "VS01-X1-BACKEND",
        "X2_FRONTEND_JOURNEY_HARNESS": "VS01-X2-FRONTEND",
        "X3_SSE_RECOVERY_HARNESS": "VS01-X3-SSE-RECOVERY",
        "X4_CROSS_COMPONENT_GATE": "VS01-X4-CROSS-COMPONENT-GATE",
    }
    specialists = {
        name: "PASS" if harness_ready and fragment_id in fragment_ids else "FAIL"
        for name, fragment_id in specialist_fragments.items()
    }
    named_readiness = _named_readiness(manifest, harness_ready)
    components = {
        "BACKEND_HARNESS_READY": "YES"
        if specialists["X1_BACKEND_ACCEPTANCE_HARNESS"] == "PASS"
        else "NO",
        "FRONTEND_HARNESS_READY": "YES"
        if specialists["X2_FRONTEND_JOURNEY_HARNESS"] == "PASS"
        else "NO",
        "SSE_HARNESS_READY": "YES" if specialists["X3_SSE_RECOVERY_HARNESS"] == "PASS" else "NO",
        "RESTART_HARNESS_READY": "YES"
        if named_readiness["EXACT_RUN_SSE_TEST"] == "READY"
        and {"VS01-BE-014", "VS01-REC-011", "VS01-REC-015"}
        <= {control["control_id"] for control in manifest["controls"]}
        else "NO",
        "IDENTITY_NEGATIVE_MATRIX_READY": "YES"
        if harness_ready
        and {"VS01-ID-001", "VS01-ID-002", "VS01-ID-003", "VS01-ID-004"}
        <= {control["control_id"] for control in manifest["controls"]}
        else "NO",
        "SECURITY_NEGATIVE_MATRIX_READY": "YES"
        if harness_ready
        and {"VS01-SEC-001", "VS01-SEC-002"}
        <= {control["control_id"] for control in manifest["controls"]}
        else "NO",
    }
    passed_self_tests = sum(
        check.get("passed", 0) for check in harness_checks if isinstance(check.get("passed"), int)
    )
    executed_self_tests = sum(
        check.get("executed", 0)
        for check in harness_checks
        if isinstance(check.get("executed"), int)
    )
    self_test_count_known = any("executed" in check for check in harness_checks)
    security = _security_summary(
        outcomes,
        integrated=integrated,
        environment=reality,
    )
    self_test_scope_safe = (
        delivery_state.get("product_source_files_modified") is False
        and delivery_state.get("parent_only_files_modified") is False
        and delivery_state.get("outside_acceptance_owned_scope") == []
        and delivery_state.get("phase4_integration_branch_modified_from_base") is False
        and delivery_state.get("main_modified_from_base") is False
    )
    delivery_failures = (
        _integrated_x_delivery_failures(delivery_state)
        if integrated
        else _self_test_delivery_failures(delivery_state)
    )
    harness_core_ready = harness_ready and all(value == "PASS" for value in specialists.values())
    codex_x_pass = harness_core_ready and not delivery_failures
    if integrated and not codex_x_pass:
        integrated_pass = False
    next_exact_action = _next_action(
        integrated=integrated,
        integrated_pass=integrated_pass,
        codex_x_pass=codex_x_pass,
        controls=controls,
        harness_checks=harness_checks,
        required_reality=required_reality,
        reality=reality,
        findings=findings,
        delivery_failures=delivery_failures,
    )
    return {
        "schema_version": "phase4-vs01-acceptance-result/v1",
        "generated_at": utc_now(),
        "phase4_codex_x": "PASS" if codex_x_pass else "FAIL",
        "role": "VS01_ACCEPTANCE_HARNESS",
        "execution_mode": mode,
        "authority": dict(manifest["authority"]),
        "manifest_sha256": sha256_json(manifest),
        "harness_status": "READY" if harness_ready else "NOT_READY",
        "vs01_integrated_status": (
            "PASS" if integrated_pass else "FAIL" if integrated else "NOT_RUN"
        ),
        "controls": controls,
        "summary": {"total": len(controls), "by_status": dict(sorted(counts.items()))},
        "manifest_summary": {
            "total": len(manifest["controls"]),
            "ready": manifest_counts.get("READY", 0),
            "blocked_by_a": manifest_counts.get("BLOCKED_BY_A", 0),
            "blocked_by_b": manifest_counts.get("BLOCKED_BY_B", 0),
            "blocked_by_c": manifest_counts.get("BLOCKED_BY_C", 0),
            "blocked_by_parent": manifest_counts.get("BLOCKED_BY_PARENT", 0),
        },
        "specialists": specialists,
        "harness_components": components,
        "named_tests": named_readiness,
        "artifacts": {
            "acceptance_manifest": "acceptance/phase4/vs01/PHASE4_VS01_ACCEPTANCE_MANIFEST.json",
            "top_level_runner": (
                "PYTHONPATH=. python3.11 acceptance/phase4/vs01/run_vs01.py "
                "integrated --config /absolute/path/to/reviewed-vs01-config.json "
                "--output-dir acceptance/phase4/vs01/out/integrated"
            ),
        },
        "harness_self_tests": {
            "passed": passed_self_tests if self_test_count_known else None,
            "executed": executed_self_tests if self_test_count_known else None,
        },
        "harness_checks": [dict(check) for check in harness_checks],
        "environment": reality,
        "findings": [dict(finding) for finding in findings],
        "delivery": delivery_state,
        "codex_x_delivery_gate_applied": True,
        "codex_x_delivery_failures": delivery_failures,
        "safety": {
            **security,
            "product_source_files_modified": delivery_state.get("product_source_files_modified"),
            "parent_only_files_modified": delivery_state.get("parent_only_files_modified"),
            "phase5_activated": False if self_test_scope_safe else None,
            "qiji_integrated": False if self_test_scope_safe else None,
        },
        "ready_for_parent_vs01_gate": (
            integrated_pass if integrated else codex_x_pass and self_test_scope_safe
        ),
        "next_exact_action": next_exact_action,
    }


def result_markdown(result: Mapping[str, Any]) -> str:
    summary = result["summary"]
    manifest_summary = result["manifest_summary"]
    delivery = result["delivery"]
    safety = result["safety"]
    self_tests = result["harness_self_tests"]

    def display(value: Any) -> str:
        if value is True:
            return "YES"
        if value is False:
            return "NO"
        if value is None:
            return "NOT_RUN"
        return str(value)

    count_text = (
        f"{self_tests['passed']}/{self_tests['executed']}"
        if self_tests["executed"] is not None
        else "NOT_RECORDED"
    )
    lines = [
        "# Phase 4 VS01 Acceptance Result",
        "",
        f"PHASE4_CODEX_X = {result['phase4_codex_x']}",
        "",
        f"ROLE = {result['role']}",
        "",
        f"BRANCH_REQUESTED = {delivery.get('requested_branch')}",
        "",
        f"BRANCH = {delivery.get('actual_branch')}",
        "",
        "BRANCH_SUBSTITUTION_AUTHORIZED = "
        f"{display(delivery.get('branch_substitution_authorized'))}",
        "",
        f"WORKTREE = {delivery.get('worktree_portable')}",
        "",
        f"BASE_SHA = {delivery.get('base_sha')}",
        "",
        f"SOURCE_PARENT_IS_ANCESTOR = {display(delivery.get('source_parent_is_ancestor'))}",
        "",
        "SOURCE_PARENT_TREE_MATCHES_AUTHORITY = "
        f"{display(delivery.get('source_parent_tree_matches_authority'))}",
        "",
        f"BRANCH_SHA_AT_EXECUTION = {delivery.get('branch_sha_at_execution')}",
        "",
        "FINAL_BRANCH_SHA = "
        f"{delivery.get('final_branch_sha') or delivery.get('final_branch_sha_resolution')}",
        "",
        f"DELIVERY_SNAPSHOT_SEMANTICS = {delivery.get('delivery_snapshot_semantics')}",
        "",
    ]
    for name, status in result["specialists"].items():
        lines.extend([f"{name} = {status}", ""])
    lines.extend(
        [
            f"VS01_CONTROLS_TOTAL = {manifest_summary['total']}",
            "",
            f"VS01_CONTROLS_READY = {manifest_summary['ready']}",
            "",
            f"VS01_CONTROLS_BLOCKED_BY_A = {manifest_summary['blocked_by_a']}",
            "",
            f"VS01_CONTROLS_BLOCKED_BY_B = {manifest_summary['blocked_by_b']}",
            "",
            f"VS01_CONTROLS_BLOCKED_BY_C = {manifest_summary['blocked_by_c']}",
            "",
            f"VS01_CONTROLS_BLOCKED_BY_PARENT = {manifest_summary['blocked_by_parent']}",
            "",
        ]
    )
    for name, status in result["harness_components"].items():
        lines.extend([f"{name} = {status}", ""])
    for name, status in result["named_tests"].items():
        lines.extend([f"{name} = {status}", ""])
    lines.extend(
        [
            f"VS01_ACCEPTANCE_MANIFEST = {result['artifacts']['acceptance_manifest']}",
            "",
            f"VS01_TOP_LEVEL_RUNNER = {result['artifacts']['top_level_runner']}",
            "",
            f"HARNESS_SELF_TESTS = {count_text}",
            "",
            f"HARNESS_STATUS = {result['harness_status']}",
            "",
            f"VS01_INTEGRATED_STATUS = {result['vs01_integrated_status']}",
            "",
            f"INTEGRATED_PUBLIC_SURFACE_SCAN = {safety['integrated_public_surface_scan']}",
            "",
            f"SECURITY_ATTESTATION_SCOPE = {safety['attestation_scope']}",
            "",
            f"SECRET_LEAKAGE = {display(safety['secret_leakage'])}",
            "",
            f"HIDDEN_COT_EXPOSED = {display(safety['hidden_cot_exposed'])}",
            "",
            f"PRODUCT_SOURCE_FILES_MODIFIED = {display(safety['product_source_files_modified'])}",
            "",
            f"PARENT_ONLY_FILES_MODIFIED = {display(safety['parent_only_files_modified'])}",
            "",
            f"PARENT_SEMANTIC_PATCH_PROPOSALS = {delivery.get('parent_semantic_patch_proposals')}",
            "",
            f"PHASE5_ACTIVATED = {display(safety['phase5_activated'])}",
            "",
            f"QIJI_INTEGRATED = {display(safety['qiji_integrated'])}",
            "",
            f"BRANCH_PUSHED = {display(delivery.get('branch_pushed'))}",
            "",
            f"WORKTREE_CLEAN_AT_EXECUTION = {display(delivery.get('worktree_clean_at_execution'))}",
            "",
            f"REMOTE_BRANCH = {delivery.get('remote_branch')}",
            "",
            f"REMOTE_BRANCH_SHA_AT_EXECUTION = {delivery.get('remote_branch_sha_at_execution')}",
            "",
            "PHASE4_INTEGRATION_BRANCH_MODIFIED = "
            f"{display(delivery.get('phase4_integration_branch_modified_from_base'))}",
            "",
            f"MAIN_MODIFIED = {display(delivery.get('main_modified_from_base'))}",
            "",
            f"READY_FOR_PARENT_VS01_GATE = {display(result['ready_for_parent_vs01_gate'])}",
            "",
            f"NEXT_EXACT_ACTION = {result['next_exact_action']}",
            "",
            "## Executed result counts",
            "",
            f"- Total: `{summary['total']}`",
        ]
    )
    for status, count in summary["by_status"].items():
        lines.append(f"- {status}: `{count}`")
    lines.extend(["", "## Harness checks", ""])
    for check in result["harness_checks"]:
        lines.append(f"- `{check.get('check_id')}`: `{check.get('status')}`")
    lines.extend(["", "## Findings", ""])
    if result["findings"]:
        for finding in result["findings"]:
            lines.append(
                f"- `{finding.get('finding_id')}` ({finding.get('owner')}): "
                f"{finding.get('observed_behavior')}"
            )
    else:
        lines.append("- None recorded by this execution.")
    return "\n".join(lines) + "\n"


def write_result_bundle(output_root: Path, result: Mapping[str, Any]) -> tuple[Path, Path]:
    output_root.mkdir(parents=True, exist_ok=True)
    json_path = output_root / RESULT_JSON_NAME
    markdown_path = output_root / RESULT_MARKDOWN_NAME
    write_json(json_path, result)
    markdown_path.write_text(result_markdown(result), encoding="utf-8")
    return json_path, markdown_path


__all__ = [
    "CONTRACT_SET_SHA256",
    "FINAL_FREEZE_DECISION_SHA256",
    "GateConfigurationError",
    "GateError",
    "MANIFEST_PATH",
    "ManagedService",
    "PostgreSQLIsolation",
    "PublicSurfaceViolation",
    "REPOSITORY_ROOT",
    "VS01_ROOT",
    "aggregate_manifest",
    "application_database_url",
    "apply_outcomes",
    "assert_url_unreachable",
    "build_result",
    "canonical_json_bytes",
    "collect_delivery_metadata",
    "collect_integrated_x_delivery_metadata",
    "load_control_fragments",
    "load_integrated_config",
    "materialize_manifest",
    "parse_playwright_result",
    "redact_url",
    "result_markdown",
    "run_command",
    "scan_public_surface",
    "sha256_json",
    "validate_integrated_config",
    "write_result_bundle",
]
