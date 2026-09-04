"""Versioned arithmetic and methodology policy for authoritative MACD 12/26/9."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Context


@dataclass(frozen=True, slots=True)
class MACDDecimalContextPolicy:
    """One immutable definition shared by production and the independent oracle."""

    policy_id: str
    precision: int
    rounding: str
    fast_span: int
    slow_span: int
    signal_span: int
    ema_adjust: bool
    ema_seed: str

    @property
    def warmup_required(self) -> int:
        return self.slow_span + self.signal_span - 1

    def decimal_context(self) -> Context:
        """Return a fresh context without consulting the process-global context."""

        return Context(prec=self.precision, rounding=self.rounding)


MACD_DECIMAL_CONTEXT_POLICY = MACDDecimalContextPolicy(
    policy_id="macd-decimal-context-v1",
    precision=28,
    rounding=ROUND_HALF_EVEN,
    fast_span=12,
    slow_span=26,
    signal_span=9,
    ema_adjust=False,
    ema_seed="first_observation",
)
