from typing import Any, Protocol

from src.domain.base import JsonObject
from src.domain.capability import CapabilityContext


class MCPClient(Protocol):
    async def call_tool(self, name: str, arguments: JsonObject) -> Any: ...


class MCPToolBackend:
    """Optional protocol backend; internal financial functions remain native."""

    def __init__(self, client: MCPClient):
        self._client = client

    async def execute(
        self,
        tool_id: str,
        inputs: JsonObject,
        context: CapabilityContext,
        version: str | None = None,
    ) -> Any:
        del context, version
        return await self._client.call_tool(tool_id, inputs)
