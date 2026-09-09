"""Delivery acceptance with fake Docker/release/gateway. No production state or provider use."""

import hashlib
import io
import json
import subprocess
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from installer import cli, credential, release
from installer.errors import MESSAGES, InstallError
from installer.services import DockerServices
from installer.state import State
from src.evaluator.contracts import EvaluationAuthorizationError


class FakeServices:
    image = "vfa-evaluator:source"

    def __init__(self, fail=None):
        self.calls, self.fail = [], fail

    def __getattr__(self, name):
        def call(*args, **kwargs):
            self.calls.append(name)
            if name == self.fail:
                raise InstallError(
                    {
                        "check": "DOCKER_NOT_RUNNING",
                        "database": "DATABASE_START_FAILED",
                        "migrate": "MIGRATION_FAILED",
                        "health": "HEALTH_TIMEOUT",
                    }.get(name, "INSTALLATION_FAILED")
                )
            return "postgres: running\napi: running\nweb: running"

        return call


def session():
    return SimpleNamespace(
        url="https://offline.example",
        _token=SecretStr("synthetic-private-token"),
        metadata={
            "routes": {"teamorouter-sol": {}, "mimo-direct": {}},
            "llm_remaining": 9,
            "data_remaining": 9,
            "financial_data_allowed": True,
        },
    )


def setup(tmp_path, fail=None):
    service = FakeServices(fail)
    state = State(tmp_path)
    app = cli.Installer(
        state, service, discover=lambda *a: Path("offline.vfaeval"), unlock=lambda p: session()
    )
    return app, state, service


def test_fresh_install_autostarts_and_opens_after_health(tmp_path, capsys):
    app, state, services = setup(tmp_path)
    app.install(source=True)
    assert services.calls == [
        "check",
        "ports",
        "storage",
        "runtime_dependencies",
        "database",
        "migrate",
        "start",
        "health",
    ]
    assert state.data["stage"] == "READY" and state.data["ready"]
    assert (tmp_path / "open-browser").read_text() == "http://127.0.0.1:4173"
    assert "synthetic-private-token" not in state.path.read_text() + capsys.readouterr().out


def test_existing_install_and_resume_revalidate_authority(tmp_path):
    app, _, service = setup(tmp_path, "migrate")
    with pytest.raises(InstallError, match="MIGRATION_FAILED"):
        app.install(source=True)
    assert "start" not in service.calls
    app, state, service = setup(tmp_path)
    assert state.data["stage"] == "MIGRATION"
    app.start(no_open=True)
    assert state.data["ready"] and not (tmp_path / "open-browser").exists()
    app.start(no_open=True)
    assert service.calls.count("migrate") == 2


@pytest.mark.parametrize(
    "failure", ["check", "runtime_dependencies", "database", "migrate", "health"]
)
def test_failed_stage_never_opens_browser(tmp_path, failure):
    app, state, _ = setup(tmp_path, failure)
    with pytest.raises(InstallError):
        app.start()
    assert not state.data.get("ready") and not (tmp_path / "open-browser").exists()


@pytest.mark.parametrize(
    "code",
    [
        "NO_EVALUATOR_CREDENTIAL",
        "INVALID_EVALUATOR_CREDENTIAL",
        "CREDENTIAL_EXPIRED",
        "CREDENTIAL_REVOKED",
        "GATEWAY_UNREACHABLE",
        "QUOTA_EXHAUSTED",
    ],
)
def test_failed_credential_never_starts_services(tmp_path, code):
    app, _, service = setup(tmp_path)

    def denied(path):
        raise InstallError(code)

    app.unlock = denied
    with pytest.raises(InstallError, match=code):
        app.start()
    assert "start" not in service.calls


def test_full_proof_flag_uses_same_packaged_runtime_and_policy(tmp_path):
    app, _, service = setup(tmp_path)
    app.start(full_proof=True, no_open=True)
    assert "runtime_dependencies" in service.calls
    assert "migrate" in service.calls and "start" in service.calls


@pytest.mark.parametrize("count", [0, 1, 2])
def test_discovery_spaces_unicode_and_selection(tmp_path, count, capsys):
    for i in range(count):
        (tmp_path / f"评估 {i}.vfaeval").write_bytes(b"encrypted fixture")
    if not count:
        with pytest.raises(InstallError, match="NO_EVALUATOR_CREDENTIAL"):
            credential.discover([tmp_path], ask=lambda _: "")
    else:
        found = credential.discover([tmp_path], ask=lambda _: "2")
        assert found.name == f"评估 {count - 1}.vfaeval"
    assert "encrypted fixture" not in capsys.readouterr().out


def test_discovery_rejects_symlink(tmp_path):
    actual = tmp_path / "private.txt"
    actual.write_text("not a bundle")
    (tmp_path / "alias.vfaeval").symlink_to(actual)
    with pytest.raises(InstallError):
        credential.discover([tmp_path], ask=lambda _: "")


@pytest.mark.parametrize(
    "upstream,owned",
    [
        ("EVALUATION_CREDENTIAL_INVALID", "INVALID_EVALUATOR_CREDENTIAL"),
        ("EVALUATION_CREDENTIAL_EXPIRED", "CREDENTIAL_EXPIRED"),
        ("EVALUATION_CREDENTIAL_REVOKED", "CREDENTIAL_REVOKED"),
        ("EVALUATION_AUTHORITY_UNAVAILABLE", "GATEWAY_UNREACHABLE"),
    ],
)
def test_accepted_gateway_error_mapping(monkeypatch, upstream, owned):
    async def fail(*args):
        raise EvaluationAuthorizationError(upstream)

    monkeypatch.setattr(credential, "prepare_session", fail)
    with pytest.raises(InstallError, match=owned):
        credential.unlock("file", prompt=lambda _: "not-logged-passphrase")


def test_readiness_success_uses_existing_session_contract(monkeypatch):
    async def ready(*args):
        return session()

    monkeypatch.setattr(credential, "prepare_session", ready)
    assert (
        credential.unlock("file", prompt=lambda _: "not-logged-passphrase").metadata[
            "llm_remaining"
        ]
        == 9
    )


def test_safe_state_rejects_secrets(tmp_path):
    state = State(tmp_path)
    for name in ("token", "password", "Authorization", "provider_key"):
        with pytest.raises(AssertionError):
            state.save(**{name: "must not persist"})
    assert not state.path.exists()


def zip_bytes(name="installer/Dockerfile"):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr(name, "FROM scratch")
    return stream.getvalue()


def manifest(raw):
    return {
        "schema": 1,
        "version": "evaluator-1",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "archive_url": f"https://github.com/{release.REPOSITORY}/releases/download/evaluator-1/package.zip",
    }


def test_download_verified_before_extract(tmp_path):
    raw = zip_bytes()
    release.unpack(manifest(raw), tmp_path / "package", read=lambda _: raw)
    assert (tmp_path / "package/installer/Dockerfile").exists()
    with pytest.raises(InstallError, match="INTEGRITY_FAILED"):
        release.unpack(manifest(raw), tmp_path / "bad", read=lambda _: b"tampered")
    assert not (tmp_path / "bad").exists()


@pytest.mark.parametrize(
    "name", ["../escape", "/absolute", "a/../../escape", "C:/windows", "a\\evil"]
)
def test_archive_member_bounds_before_any_write(tmp_path, name):
    raw = zip_bytes(name)
    with pytest.raises(InstallError, match="INTEGRITY_FAILED"):
        release.unpack(manifest(raw), tmp_path / "bad", read=lambda _: raw)
    assert not (tmp_path / "bad").exists()


@pytest.mark.parametrize("version", [None, "evaluator-1"])
def test_release_selection_never_develop(version):
    raw = zip_bytes()
    spec = manifest(raw)
    urls = []

    def read(url):
        urls.append(url)
        if url.startswith(release.API):
            return json.dumps(
                {
                    "tag_name": "evaluator-1",
                    "assets": [
                        {
                            "name": "evaluator-manifest.json",
                            "browser_download_url": spec["archive_url"].replace(
                                "package.zip", "evaluator-manifest.json"
                            ),
                        }
                    ],
                }
            ).encode()
        return json.dumps(spec).encode()

    assert release.resolve(version, read)["version"] == "evaluator-1"
    assert urls[0].endswith("/latest" if version is None else "/tags/evaluator-1")
    assert all("develop" not in u for u in urls)


def test_latest_prerelease_or_no_assets_is_not_installable():
    for response in ({"prerelease": True}, {"assets": []}):
        with pytest.raises(InstallError, match="PUBLICATION_REQUIRED"):
            release.resolve(read=lambda _, response=response: json.dumps(response).encode())


def test_update_installs_selected_image_then_migrates(tmp_path):
    app, state, service = setup(tmp_path)
    app.resolve = lambda version: {"version": "evaluator-2"}
    app.unpack = lambda *a: tmp_path / "release"
    app.install(version="evaluator-2", no_open=True)
    assert state.data["version"] == "evaluator-2"
    assert (
        service.calls.index("install")
        < service.calls.index("migrate")
        < service.calls.index("start")
    )


def test_database_password_separate_and_persistent(tmp_path):
    service = DockerServices(
        tmp_path, "C:/Users/Evaluator/AppData/Local/VFA", "vfa-evaluator:source"
    )
    service.storage()
    password = (tmp_path / "runtime/db.password").read_text()
    service.storage()
    assert (tmp_path / "runtime/db.password").read_text() == password
    compose = service.compose.read_text()
    assert password not in compose and "POSTGRES_PASSWORD_FILE" in compose
    assert "127.0.0.1:8010:8010" in compose and "research" in compose
    config = json.loads(compose)
    api_mounts = config["services"]["api"]["volumes"]
    broker = config["services"]["sandbox-broker"]
    assert not any("docker.sock" in mount for mount in api_mounts)
    assert any("docker.sock" in mount for mount in broker["volumes"])
    assert "ports" not in broker and broker["network_mode"] == "none"
    assert not any("credentials" in mount for mount in broker["volumes"])
    assert (tmp_path / "runtime/db.password").stat().st_mode & 0o777 == 0o600


def test_token_handoff_only_stdin_never_argv(tmp_path):
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, stdout=b"", stderr=b"")

    service = DockerServices(tmp_path, str(tmp_path), "vfa-evaluator:source", run=run)
    service.start(session())
    assert all("synthetic-private-token" not in str(args) for args, _ in calls)
    assert b"synthetic-private-token" in calls[-1][1]["input"]
    assert "handoff" in calls[-1][0]


def test_docker_failure_never_exposes_raw_error(tmp_path, capsys):
    def run(args, **kwargs):
        return subprocess.CompletedProcess(args, 1, stdout=b"", stderr=b"secret-password")

    service = DockerServices(tmp_path, str(tmp_path), "vfa-evaluator:source", run=run)
    with pytest.raises(InstallError, match="DOCKER_NOT_RUNNING") as caught:
        service.check()
    assert "secret-password" not in str(caught.value) + capsys.readouterr().out


def test_health_timeout_bounded(tmp_path):
    service = DockerServices(tmp_path, str(tmp_path), "vfa-evaluator:source")
    with pytest.raises(InstallError, match="HEALTH_TIMEOUT"):
        service.health(timeout=0)


@pytest.mark.parametrize("name", ["stop", "status", "doctor", "open"])
def test_cli_commands_route_to_owned_services(tmp_path, monkeypatch, name):
    service = FakeServices()
    monkeypatch.setattr(cli, "DockerServices", lambda *a: service)
    monkeypatch.setattr(cli.Installer, "doctor", lambda self, **kwargs: service.doctor())
    monkeypatch.setattr("sys.argv", ["vfa", name, "--root", str(tmp_path)])
    cli.main()
    assert ({"open": "health"}.get(name, name)) in service.calls
    if name == "stop":
        assert "down" not in service.calls


def test_platform_sources_use_secure_runtime_and_user_paths():
    bash = Path("scripts/install-evaluator.sh").read_text()
    powershell = Path("scripts/install-evaluator.ps1").read_text()
    assert "shasum -a 256" in bash and "Get-FileHash" in powershell
    assert "Read-Host" in powershell and "REBOOT_REQUIRED" in powershell
    assert "LOCALAPPDATA" in powershell and "Application Support" in bash
    assert "wsl --install" not in powershell and "pip install" not in bash
    subprocess.run(["bash", "-n", "scripts/install-evaluator.sh", "installer/vfa.sh"], check=True)


def test_errors_have_action_and_safe_unknown():
    assert "run" in MESSAGES["REBOOT_REQUIRED"].lower()
    assert str(InstallError("secret-token")) == str(InstallError("INSTALLATION_FAILED"))


def test_doctor_no_paid_calls(tmp_path, capsys):
    app, _, services = setup(tmp_path)
    app.doctor()
    assert services.calls == ["check", "status", "runtime_dependencies", "health"]
    assert "Paid upstream calls 0" in capsys.readouterr().out


def test_corrupt_state_has_owned_error_no_traceback(tmp_path, monkeypatch, capsys):
    (tmp_path / "state.json").write_text("private-corrupt-value")
    monkeypatch.setattr("sys.argv", ["vfa", "status", "--root", str(tmp_path)])
    with pytest.raises(SystemExit):
        cli.main()
    output = capsys.readouterr()
    assert "INSTALLATION_FAILED" in output.out
    assert "private-corrupt-value" not in output.out + output.err


@pytest.mark.parametrize("tag", ["../escape", "/absolute", "nested/tag"])
def test_release_tag_cannot_select_filesystem_path(tag):
    with pytest.raises(InstallError, match="PUBLICATION_REQUIRED"):
        release.resolve(read=lambda _: json.dumps({"tag_name": tag}).encode())


@pytest.mark.parametrize("name", ["start", "update"])
def test_cli_start_and_update_dispatch(tmp_path, monkeypatch, name):
    calls = []
    monkeypatch.setattr(cli.Installer, "start", lambda self, **kw: calls.append("start"))
    monkeypatch.setattr(cli.Installer, "install", lambda self, **kw: calls.append(kw))
    monkeypatch.setattr("sys.argv", ["vfa", name, "--root", str(tmp_path), "--version", "v1"])
    cli.main()
    assert calls == (
        ["start"]
        if name == "start"
        else [
            {
                "version": "v1",
                "source": False,
                "bundle": None,
                "no_open": False,
                "full_proof": False,
            }
        ]
    )
