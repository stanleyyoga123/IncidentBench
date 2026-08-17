from __future__ import annotations

import asyncio
import json
from contextvars import ContextVar
from typing import Any, Callable

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from config import SETTINGS


_AUDIT: ContextVar[Callable[[str, dict, Any], None] | None] = ContextVar(
    "mcp_audit", default=None
)


class audit_tool_calls:
    def __init__(self, callback):
        self.callback = callback

    def __enter__(self):
        self.token = _AUDIT.set(self.callback)

    def __exit__(self, *_args):
        _AUDIT.reset(self.token)


class ToolRegistry:
    def __init__(self):
        self._schemas: dict[str, dict[str, Any]] | None = None

    async def _list_remote(self) -> dict[str, dict[str, Any]]:
        headers = {"Authorization": f"Bearer {SETTINGS.mcp.token}"}
        async with httpx2.AsyncClient(headers=headers, timeout=300) as client:
            async with streamable_http_client(SETTINGS.mcp.url, http_client=client) as streams:
                read, write = streams[0], streams[1]
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    response = await session.list_tools()
                    return {
                        tool.name: {
                            "name": tool.name,
                            "description": tool.description or "",
                            "schema": tool.inputSchema,
                        }
                        for tool in response.tools
                    }

    async def _call_remote(self, name: str, kwargs: dict[str, Any]) -> Any:
        headers = {"Authorization": f"Bearer {SETTINGS.mcp.token}"}
        async with httpx2.AsyncClient(headers=headers, timeout=300) as client:
            async with streamable_http_client(SETTINGS.mcp.url, http_client=client) as streams:
                read, write = streams[0], streams[1]
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    response = await session.call_tool(name, kwargs)
                    if getattr(response, "structuredContent", None) is not None:
                        return response.structuredContent
                    values = []
                    for item in response.content:
                        text = getattr(item, "text", None)
                        if text is None:
                            continue
                        try:
                            values.append(json.loads(text))
                        except json.JSONDecodeError:
                            values.append(text)
                    return values[0] if len(values) == 1 else values

    def _metadata(self) -> dict[str, dict[str, Any]]:
        if self._schemas is None:
            self._schemas = asyncio.run(self._list_remote())
        return self._schemas

    def describe_openai_format(self, names: list[str]) -> list[dict[str, Any]]:
        metadata = self._metadata()
        return [
            {
                "type": "function",
                "function": {
                    "name": name.replace(".", "__"),
                    "description": metadata[name]["description"],
                    "parameters": metadata[name]["schema"],
                },
            }
            for name in names
            if name in metadata
        ]

    def run(self, name: str, kwargs: dict[str, Any]):
        canonical = name.replace("__", ".")
        try:
            result = asyncio.run(self._call_remote(canonical, kwargs))
        except Exception as exc:
            result = {"ok": False, "error": str(exc), "exception_type": type(exc).__name__}
        callback = _AUDIT.get()
        if callback:
            callback(canonical, kwargs, result)
        return type("ToolOutput", (), {"model_dump_json": lambda self: json.dumps({"name": canonical, "kwargs": kwargs, "result": result}, default=str)})()


TOOL_REGISTRY = ToolRegistry()
