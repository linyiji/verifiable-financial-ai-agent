from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from src.adapters.fmp.provider import FMPProvider, FMPTransport, HttpxFMPTransport
from src.data.fixtures import FixtureProvider
from src.data.provider import Provider
from src.infrastructure.config.settings import FMPSettings


class FinancialProviderMode(StrEnum):
    AUTO = "auto"
    FMP = "fmp"
    FIXTURE = "fixture"


@dataclass(frozen=True, slots=True)
class FinancialProviderSelection:
    provider: Provider
    mode: FinancialProviderMode
    live: bool


def select_financial_provider(
    *,
    mode: FinancialProviderMode,
    fmp_settings: FMPSettings,
    fixture_path: Path,
    transport: FMPTransport | None = None,
) -> FinancialProviderSelection:
    if mode is FinancialProviderMode.FIXTURE or (
        mode is FinancialProviderMode.AUTO and not fmp_settings.enabled
    ):
        return FinancialProviderSelection(
            provider=FixtureProvider(fixture_path),
            mode=FinancialProviderMode.FIXTURE,
            live=False,
        )
    if not fmp_settings.enabled:
        raise ValueError("FMP mode requested but FMP credentials are not configured")
    resolved_transport = transport or HttpxFMPTransport(fmp_settings)
    return FinancialProviderSelection(
        provider=FMPProvider(resolved_transport),
        mode=FinancialProviderMode.FMP,
        live=True,
    )
