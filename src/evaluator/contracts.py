from datetime import date
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

ROUTES = {"teamorouter-sol", "teamorouter-luna", "mimo-direct"}
PATHS = {
    "profile": "/stable/profile",
    "income": "/stable/income-statement",
    "balance": "/stable/balance-sheet-statement",
    "cashflow": "/stable/cash-flow-statement",
    "peers": "/stable/stock-peers",
    "quote": "/stable/quote",
    "historical": "/stable/historical-price-eod/full",
    "analyst": "/stable/grades-consensus",
    "news": "/stable/news/stock-latest",
    "transcript": "/stable/earning-call-transcript",
}


class EvaluationAuthorizationError(RuntimeError):
    """Not a provider failure: never retry/switch routes to evade authority."""

    def __init__(self, code="EVALUATION_AUTHORITY_UNAVAILABLE"):
        self.code = (
            code
            if code
            in {
                "EVALUATION_AUTHORITY_UNAVAILABLE",
                "EVALUATION_CREDENTIAL_INVALID",
                "EVALUATION_CREDENTIAL_EXPIRED",
                "EVALUATION_CREDENTIAL_REVOKED",
                "EVALUATION_BUDGET_EXHAUSTED",
                "EVALUATION_ROUTE_NOT_ALLOWED",
                "EVALUATION_RATE_LIMITED",
                "EVALUATION_REQUEST_INVALID",
            }
            else "EVALUATION_AUTHORITY_UNAVAILABLE"
        )
        super().__init__(self.code)


def gateway_url(value, *, allow_loopback=False):
    try:
        u = urlsplit(value)
        valid = u.scheme == "https" or (
            allow_loopback and u.scheme == "http" and u.hostname in {"127.0.0.1", "::1"}
        )
        if not valid or not u.hostname or u.username or u.password or u.query or u.fragment:
            raise ValueError()
        if u.path not in {"", "/"} or u.port == 0:
            raise ValueError()
        return value.rstrip("/")
    except Exception:
        raise EvaluationAuthorizationError("EVALUATION_REQUEST_INVALID") from None


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Message(Strict):
    role: Literal["system", "user", "assistant"]
    content: str = Field(max_length=100_000)


class ModelOperation(Strict):
    route_id: Literal["teamorouter-sol", "teamorouter-luna", "mimo-direct"]
    messages: list[Message] = Field(min_length=1, max_length=64)
    schema_name: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    response_schema: dict

    # Correlation is not authorization; no caller-supplied quota identity.
    @model_validator(mode="after")
    def bound_schema(self):
        import json

        raw = json.dumps(self.response_schema)
        if len(raw) > 100_000:
            raise ValueError("schema too large")

        def walk(node, depth=0):
            if depth > 40:
                raise ValueError("schema too deep")
            if isinstance(node, dict):
                if "$ref" in node and not str(node["$ref"]).startswith("#"):
                    raise ValueError("external schema reference")
                for value in node.values():
                    walk(value, depth + 1)
            elif isinstance(node, list):
                for value in node:
                    walk(value, depth + 1)

        walk(self.response_schema)
        return self


class DataOperation(Strict):
    operation: Literal[
        "profile",
        "income",
        "balance",
        "cashflow",
        "peers",
        "quote",
        "historical",
        "analyst",
        "news",
        "transcript",
    ]
    params: dict[str, str | int]

    @model_validator(mode="after")
    def validate_params(self):
        import re

        allowed = {"symbol"}
        if self.operation in {"income", "balance", "cashflow"}:
            allowed |= {"period", "limit"}
        elif self.operation == "historical":
            allowed |= {"from", "to", "limit"}
        elif self.operation == "news":
            allowed = {"symbols", "limit", "page"}
        elif self.operation == "transcript":
            allowed |= {"year", "quarter"}
        if set(self.params) - allowed:
            raise ValueError("unregistered financial parameter")
        if (
            self.operation in {"historical", "income", "balance", "cashflow", "news"}
            and set(self.params) != allowed
        ):
            raise ValueError("required financial bounds missing")
        symbol = self.params.get("symbols" if self.operation == "news" else "symbol")
        if not isinstance(symbol, str) or not re.fullmatch(r"[A-Za-z0-9.^-]{1,20}", symbol):
            raise ValueError("single symbol required")
        for key, low, high in [
            ("limit", 1, 500),
            ("page", 0, 0),
            ("year", 1980, 2100),
            ("quarter", 1, 4),
        ]:
            if key in self.params:
                val = self.params[key]
                if isinstance(val, bool) or not str(val).isdigit() or not low <= int(val) <= high:
                    raise ValueError("financial parameter out of bounds")
        if "period" in self.params and self.params["period"] not in {"annual", "quarter"}:
            raise ValueError("invalid period")
        dates = [
            date.fromisoformat(str(self.params[k])) for k in ("from", "to") if k in self.params
        ]
        if len(dates) == 2 and not 0 <= (dates[1] - dates[0]).days <= 1000:
            raise ValueError("invalid date range")
        return self


class CredentialPolicy(Strict):
    routes: set[Literal["teamorouter-sol", "teamorouter-luna", "mimo-direct"]]
    financial_data_allowed: bool = False
    expires_at: int = Field(gt=0)
    max_llm_requests: int = Field(ge=0, le=10000)
    max_data_requests: int = Field(ge=0, le=100000)
    requests_per_minute: int = Field(ge=1, le=1000)
