"""Pinned, dependency-injected boundary for approved FinRobot operations."""

from copy import deepcopy
from typing import Any, Protocol

from src.domain.base import JsonObject

from .audit import FINROBOT_PINNED_COMMIT, FinRobotAuditEntry, audit_entry_for_operation


class FinRobotBackend(Protocol):
    """Backend implemented by a later optional-dependency integration package."""

    async def invoke(self, entry: FinRobotAuditEntry, inputs: JsonObject) -> Any: ...


class FinRobotRevisionMismatchError(RuntimeError):
    pass


class FinRobotOperationNotApprovedError(RuntimeError):
    pass


class FinRobotSensitiveInputError(ValueError):
    pass


_SENSITIVE_INPUT_KEYS = frozenset(
    {"api_key", "apikey", "password", "secret", "access_token", "refresh_token"}
)


def _contains_sensitive_input(value: object) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).casefold() in _SENSITIVE_INPUT_KEYS:
                return True
            if _contains_sensitive_input(child):
                return True
    elif isinstance(value, (list, tuple)):
        return any(_contains_sensitive_input(child) for child in value)
    return False


class PinnedFinRobotAdapter:
    """Execute only allowlisted operations from the exact audited revision.

    Upstream importing and optional dependency setup belong to ``FinRobotBackend``.
    This class intentionally receives the backend by injection so merely importing
    the main application cannot trigger FinRobot package side effects.
    """

    def __init__(self, *, backend: FinRobotBackend, source_revision: str) -> None:
        if source_revision != FINROBOT_PINNED_COMMIT:
            raise FinRobotRevisionMismatchError("FinRobot source revision does not match audit pin")
        self._backend = backend
        self._source_revision = source_revision

    @property
    def source_revision(self) -> str:
        return self._source_revision

    @property
    def supported_operations(self) -> tuple[str, ...]:
        return ("charts.render", "report.render_pdf")

    async def execute(self, operation: str, inputs: JsonObject) -> Any:
        try:
            entry = audit_entry_for_operation(operation)
        except (KeyError, PermissionError) as exc:
            raise FinRobotOperationNotApprovedError(
                f"FinRobot operation is not approved: {operation}"
            ) from exc
        if _contains_sensitive_input(inputs):
            raise FinRobotSensitiveInputError(
                "FinRobot render adapter does not accept credential-bearing inputs"
            )
        return await self._backend.invoke(entry, deepcopy(inputs))

    async def calculate(self, operation: str, inputs: JsonObject) -> Any:
        """Compatibility with Phase 1; no upstream calculation is approved for MVP."""

        del inputs
        raise FinRobotOperationNotApprovedError(
            f"No FinRobot calculation is approved for MVP: {operation}"
        )

    async def render_report(self, report_data: JsonObject) -> str:
        rendered = await self.execute("report.render_pdf", report_data)
        if not isinstance(rendered, str):
            raise TypeError("FinRobot PDF backend must return an asset path string")
        return rendered
