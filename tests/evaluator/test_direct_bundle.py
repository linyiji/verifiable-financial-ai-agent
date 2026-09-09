"""Synthetic, offline direct-registry acceptance; no Owner credentials or network."""

import json
from copy import deepcopy

import pytest

from installer import credential
from installer.cli import Installer
from installer.errors import InstallError
from installer.runtime import direct_settings
from installer.services import DockerServices
from installer.state import State
from src.evaluator.bundle import decrypt_bundle, encrypt_bundle
from src.evaluator.contracts import EvaluationAuthorizationError
from src.evaluator.direct_bundle import (
    DirectBundleError,
    decrypt_direct_bundle,
    encrypt_direct_bundle,
)
from src.evaluator.direct_registry import DirectCredentialRegistry, DirectRegistrySession
from src.infrastructure.config.settings import Settings
from tests.installer.test_installer import TEST_DIGEST, TEST_REVISION, FakeServices

PASSWORD = "synthetic-test-passphrase-only"


def payload():
    def key(alias):
        return {"alias": alias, "value": "SYNTHETIC_SECRET_ONLY_" + alias}

    return {
        "payload_schema": "direct-provider-registry/v1",
        "fmp": {
            "base_url": "https://financialmodelingprep.com",
            "credentials": [key(f"fmp_pool_0{i}") for i in range(1, 5)],
        },
        "bocha": {"endpoint": "https://api.bocha.cn/v1/web-search", "credential": key("bocha_web")},
        "mimo": {
            "base_url": "https://api.xiaomimimo.com/v1",
            "credential": key("mimo_direct"),
            "models": ["mimo-v2.5"],
        },
        "teamorouter": {
            "base_url": "https://api.teamorouter.com/v1",
            "credential": key("teamorouter_default"),
            "models": ["gpt-5.6-sol", "gpt-5.6-luna", "gpt-5.6-terra"],
        },
    }


def registry():
    return DirectCredentialRegistry.model_validate(payload())


def test_round_trip_randomness_and_redaction():
    r = registry()
    first, second = encrypt_direct_bundle(r, PASSWORD), encrypt_direct_bundle(r, PASSWORD)
    assert first != second
    assert decrypt_direct_bundle(first, PASSWORD) == r
    for text in (str(r), r.model_dump_json(), str(DirectRegistrySession(r)), first.decode()):
        assert "SYNTHETIC_SECRET_ONLY" not in text and PASSWORD not in text
    assert DirectRegistrySession(r).metadata["fmp_credentials"] == 4


@pytest.mark.parametrize(
    "mutation",
    [
        "password",
        "ciphertext",
        "salt",
        "nonce",
        "truncate",
        "size",
        "version",
        "schema",
        "kdf",
        "duplicate",
        "base64",
        "bool_version",
    ],
)
def test_fail_closed(mutation):
    raw = encrypt_direct_bundle(registry(), PASSWORD)
    obj = json.loads(raw)
    password = PASSWORD
    if mutation == "password":
        password = "incorrect-password"
    elif mutation in ("ciphertext", "salt", "nonce"):
        value = obj[mutation]
        obj[mutation] = ("B" if value[0] != "B" else "A") + value[1:]
    elif mutation == "version":
        obj["format_version"] = 2
    elif mutation == "schema":
        obj["payload_schema"] = "other/v1"
    elif mutation == "kdf":
        obj["crypto"]["n"] = 2**30
    elif mutation == "base64":
        obj["nonce"] = "not-base64!"
    elif mutation == "bool_version":
        obj["format_version"] = True
    if mutation == "truncate":
        raw = raw[:50]
    elif mutation == "size":
        raw = b"x" * 65537
    elif mutation == "duplicate":
        raw = raw[:-1] + b',"format_version":1}'
    else:
        raw = json.dumps(obj).encode()
    with pytest.raises(DirectBundleError) as exc:
        decrypt_direct_bundle(raw, password)
    assert PASSWORD not in str(exc.value) and "SYNTHETIC_SECRET_ONLY" not in str(exc.value)


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "https://u:p@example.com",
        "https://example.com?key=x",
        "[https://example.com](x)",
        "https://example.com:0",
        "https://example.com:99999",
        "https://example.com:wrong",
        "https://example.com/#x",
        "https:// example.com",
    ],
)
def test_malformed_urls_rejected(url):
    data = payload()
    data["mimo"]["base_url"] = url
    with pytest.raises(ValueError):
        DirectCredentialRegistry.model_validate(data)


@pytest.mark.parametrize(
    "mutation",
    [
        "three_keys",
        "five_keys",
        "duplicate_key",
        "empty_key",
        "bocha_ai",
        "other_model",
        "missing_schema",
        "extra_provider",
    ],
)
def test_payload_authority(mutation):
    data = payload()
    if mutation == "three_keys":
        data["fmp"]["credentials"].pop()
    elif mutation == "five_keys":
        data["fmp"]["credentials"].append(deepcopy(data["fmp"]["credentials"][0]))
    elif mutation == "duplicate_key":
        data["fmp"]["credentials"][1]["value"] = data["fmp"]["credentials"][0]["value"]
    elif mutation == "empty_key":
        data["mimo"]["credential"]["value"] = ""
    elif mutation == "bocha_ai":
        data["bocha"]["endpoint"] = "https://api.bocha.cn/v1/ai-search"
    elif mutation == "other_model":
        data["teamorouter"]["models"].append("unapproved-model")
    elif mutation == "missing_schema":
        del data["payload_schema"]
    elif mutation == "extra_provider":
        data["other"] = {}
    with pytest.raises(ValueError) as exc:
        DirectCredentialRegistry.model_validate(data)
    assert "SYNTHETIC_SECRET_ONLY" not in str(exc.value)


def test_formats_cannot_be_confused():
    evaluator = encrypt_bundle(
        "vfa_" + "x" * 43, PASSWORD, url="https://gateway.example", credential_id="test"
    )
    with pytest.raises(DirectBundleError):
        decrypt_direct_bundle(evaluator, PASSWORD)
    with pytest.raises(EvaluationAuthorizationError):
        decrypt_bundle(encrypt_direct_bundle(registry(), PASSWORD), PASSWORD)


def test_fixed_discovery_and_conflict(tmp_path):
    fixed = tmp_path / "产品 文件" / "active.vfacred"
    fixed.parent.mkdir()
    fixed.write_bytes(encrypt_direct_bundle(registry(), PASSWORD))
    gateway = tmp_path / "access.vfaeval"
    gateway.write_bytes(b"fixture")
    assert credential.discover([tmp_path], direct_path=fixed) == fixed
    with pytest.raises(InstallError, match="CREDENTIAL_MODE_CONFLICT"):
        credential.discover([tmp_path], str(gateway), direct_path=fixed)
    fixed.unlink()
    assert credential.discover([tmp_path], direct_path=fixed) == gateway
    fixed.symlink_to(gateway)
    with pytest.raises(InstallError):
        credential.discover([tmp_path], direct_path=fixed)


def test_direct_start_doctor_stop_no_gateway(tmp_path, monkeypatch, capsys):
    fixed = tmp_path / "active.vfacred"
    fixed.write_bytes(encrypt_direct_bundle(registry(), PASSWORD))

    async def forbidden(*a, **kw):
        raise AssertionError("Gateway must never be called")

    monkeypatch.setattr(credential, "prepare_session", forbidden)
    services = FakeServices()
    state = State(tmp_path / "state")
    app = Installer(
        state,
        services,
        direct_path=fixed,
        unlock=lambda path: credential.unlock(path, prompt=lambda _: PASSWORD),
        expected_revision=TEST_REVISION,
        expected_digest=TEST_DIGEST,
    )
    app.start(no_open=True)
    assert state.data["ready"]
    app.doctor()
    services.stop()
    assert state.data["ready"]
    output = capsys.readouterr().out
    assert "DIRECT_REGISTRY" in output and "GATEWAY_READINESS" not in output
    assert "SYNTHETIC_SECRET_ONLY" not in output + state.path.read_text()
    assert PASSWORD not in output + state.path.read_text()
    assert services.calls[-1] == "stop"


def test_handoff_is_memory_only_and_overrides_ambient_pool(tmp_path, monkeypatch):
    calls = []
    services = DockerServices(tmp_path, str(tmp_path), "offline-image")
    monkeypatch.setattr(services, "dc", lambda *a, **kw: calls.append((a, kw)))
    services.start(DirectRegistrySession(registry()))
    args, kwargs = calls[-1]
    assert "SYNTHETIC_SECRET_ONLY" not in str(args)
    authority = json.loads(kwargs["payload"])
    monkeypatch.setenv("FMP_API_KEY_1", "UNAUTHORIZED_AMBIENT_CREDENTIAL")
    config = direct_settings(authority, Settings(_env_file=None))
    assert config.vfa_credential_mode == "direct_registry"
    assert len(config.fmp.credentials) == 4
    assert all(
        c.get_secret_value().startswith("SYNTHETIC_SECRET_ONLY") for c in config.fmp.credentials
    )
    assert list(tmp_path.iterdir()) == []
    with pytest.raises(ValueError):
        direct_settings({**authority, "token": "extra"}, config)


def test_hidden_prompt_cannot_fallback(tmp_path):
    fixed = tmp_path / "active.vfacred"
    fixed.write_bytes(encrypt_direct_bundle(registry(), PASSWORD))

    def unavailable(_):
        raise EOFError()

    with pytest.raises(InstallError, match="DIRECT_CREDENTIAL_UNLOCK_FAILED"):
        credential.unlock(fixed, prompt=unavailable)
