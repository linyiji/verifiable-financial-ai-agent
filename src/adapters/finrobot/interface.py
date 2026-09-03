from typing import Any, Protocol

from src.domain.base import JsonObject


class FinRobotAdapter(Protocol):
    """Narrow reuse boundary; no FinRobot imports leak into agents or domain."""

    async def calculate(self, operation: str, inputs: JsonObject) -> Any: ...

    async def render_report(self, report_data: JsonObject) -> str: ...
