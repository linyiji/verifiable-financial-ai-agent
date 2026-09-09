"""Strict, session-only Alpha provider authority; never a gateway token."""

from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator


class Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


def https_url(value):
    parsed = urlsplit(value)
    port = parsed.port
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("Invalid provider HTTPS port")
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or any(c.isspace() for c in value)
        or any(c in value for c in "[]()<>\\")
    ):
        raise ValueError("Invalid provider HTTPS URL")
    return value.rstrip("/")


class Credential(Closed):
    alias: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    value: SecretStr

    @field_validator("value")
    @classmethod
    def complete(cls, value):
        raw = value.get_secret_value()
        if not 12 <= len(raw) <= 4096 or any(c.isspace() for c in raw):
            raise ValueError("Incomplete credential")
        return value


class FMPRegistry(Closed):
    base_url: str
    credentials: tuple[Credential, ...] = Field(min_length=4, max_length=4)
    pool_policy: Literal["existing-bounded-fmp/v1"] = "existing-bounded-fmp/v1"
    max_attempts: Literal[4] = 4
    _https = field_validator("base_url")(https_url)

    @model_validator(mode="after")
    def distinct(self):
        if (
            len({c.alias for c in self.credentials}) != 4
            or len({c.value.get_secret_value() for c in self.credentials}) != 4
        ):
            raise ValueError("Four distinct FMP credentials required")
        return self


class BochaRegistry(Closed):
    endpoint: Literal["https://api.bocha.cn/v1/web-search"]
    credential: Credential


class ModelRegistry(Closed):
    base_url: str
    credential: Credential
    models: tuple[str, ...]
    _https = field_validator("base_url")(https_url)


class DirectCredentialRegistry(Closed):
    payload_schema: Literal["direct-provider-registry/v1"]
    fmp: FMPRegistry
    bocha: BochaRegistry
    mimo: ModelRegistry
    teamorouter: ModelRegistry

    @model_validator(mode="after")
    def model_authority(self):
        if self.mimo.models != ("mimo-v2.5",) or self.teamorouter.models != (
            "gpt-5.6-sol",
            "gpt-5.6-luna",
            "gpt-5.6-terra",
        ):
            raise ValueError("Unsupported Alpha model authority")
        return self

    def secret_payload(self):
        """Explicit in-memory crypto/socket boundary. Never log or persist this value."""
        data = self.model_dump(mode="json")
        for out, item in zip(data["fmp"]["credentials"], self.fmp.credentials, strict=True):
            out["value"] = item.value.get_secret_value()
        for name in ("bocha", "mimo", "teamorouter"):
            data[name]["credential"]["value"] = getattr(
                self, name
            ).credential.value.get_secret_value()
        return data

    def settings_values(self):
        return dict(
            vfa_credential_mode="direct_registry",
            fmp_api_key=None,
            fmp_api_keys=tuple(c.value for c in self.fmp.credentials),
            fmp_base_url=self.fmp.base_url,
            bocha_api_key=self.bocha.credential.value,
            mimo_api_key=self.mimo.credential.value,
            mimo_base_url=self.mimo.base_url,
            mimo_authority_file=None,
            mimo_data_model="mimo-v2.5",
            mimo_chat_model="mimo-v2.5",
            teamorouter_api_key=self.teamorouter.credential.value,
            teamorouter_base_url=self.teamorouter.base_url,
            teamorouter_model="gpt-5.6-sol",
            teamorouter_fallback_model="gpt-5.6-luna",
        )


@dataclass(frozen=True)
class DirectRegistrySession:
    registry: DirectCredentialRegistry = field(repr=False)
    mode: str = "direct_registry"

    @property
    def metadata(self):
        return {
            "mode": "DIRECT_REGISTRY",
            "fmp_credentials": 4,
            "bocha_web": "CONFIGURED",
            "bocha_ai": "OUT_OF_SCOPE",
            "mimo": "CONFIGURED",
            "teamorouter": "CONFIGURED",
        }


def from_owner_staging(data):
    """Parent-only, exact known private schema import; no registry fallback/merge."""
    providers = data["providers"]
    if set(providers) != {"fmp", "bocha", "mimo", "teamorouter"}:
        raise ValueError("Unexpected provider scope")
    if any(p.get("enabled") is not True for p in providers.values()):
        raise ValueError("Alpha providers must be explicitly enabled")
    for name, alias, models in (
        ("mimo", "mimo_direct", {"mimo-v2.5"}),
        ("teamorouter", "teamorouter_default", {"gpt-5.6-sol", "gpt-5.6-luna", "gpt-5.6-terra"}),
    ):
        if (
            set(providers[name]["credentials"]) != {alias}
            or set(providers[name]["models"]) != models
        ):
            raise ValueError("Unexpected Alpha model authority or credential slots")

    def credential(provider, alias):
        value = providers[provider]["credentials"][alias]
        return {"alias": alias, "value": value["value"] if isinstance(value, dict) else value}

    members = providers["fmp"]["credential_pools"]["fmp_default_pool"]["members"]
    if set(providers["fmp"]["credentials"]) != set(members):
        raise ValueError("Unexpected FMP slots")
    bocha = providers["bocha"]
    if set(bocha["credentials"]) != {"bocha_web_search"} or set(bocha["capabilities"]) != {
        "web_search"
    }:
        raise ValueError("Bocha Web Search only")
    return DirectCredentialRegistry.model_validate(
        {
            "payload_schema": "direct-provider-registry/v1",
            "fmp": {
                "base_url": providers["fmp"]["base_url"],
                "credentials": [credential("fmp", n) for n in members],
            },
            "bocha": {
                "endpoint": bocha["capabilities"]["web_search"]["endpoint"],
                "credential": credential("bocha", "bocha_web_search"),
            },
            "mimo": {
                "base_url": providers["mimo"]["base_url"],
                "models": ["mimo-v2.5"],
                "credential": credential("mimo", "mimo_direct"),
            },
            "teamorouter": {
                "base_url": providers["teamorouter"]["base_url"],
                "models": ["gpt-5.6-sol", "gpt-5.6-luna", "gpt-5.6-terra"],
                "credential": credential("teamorouter", "teamorouter_default"),
            },
        }
    )
