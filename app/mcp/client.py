"""Async MCP client used by the graph nodes, with one retry on failure."""

import json
from pathlib import Path

from mcp import Client

from app.mcp.server import create_server


def payload(result) -> dict:
    """Extract the tool's dict result from a CallToolResult."""
    if result.structured_content is not None:
        data = result.structured_content
        return data.get("result", data)
    return json.loads(result.content[0].text)


class SupportTools:
    def __init__(self, db_path: Path | str | None = None, retries: int = 1, server=None):
        self.server = server or create_server(db_path)
        self.retries = retries

    async def call(self, name: str, **arguments) -> dict:
        args = {k: v for k, v in arguments.items() if v is not None}
        for _ in range(self.retries + 1):
            try:
                async with Client(self.server) as client:
                    result = await client.call_tool(name, args)
                if not result.is_error:
                    return payload(result)
            except Exception:  # noqa: BLE001 - any transport/tool error counts as a failed attempt
                pass
        return {"ok": False, "error": "tool_failure", "message": f"The {name} service is currently unavailable."}
