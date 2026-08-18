from __future__ import annotations

import asyncio
import json
from contextvars import ContextVar
from typing import Any, Callable

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from config import SETTINGS
from registry.tool_context import build_tool_usage_context
from spawner import AgentSpawner


_AUDIT: ContextVar[Callable[[str, dict, Any], None] | None] = ContextVar(
    "mcp_audit", default=None
)


def _mcp_value(obj: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        try:
            value = getattr(obj, name)
        except AttributeError:
            continue
        if value is not None:
            return value
    return default


def tool_metadata(tools: list[Any]) -> dict[str, dict[str, Any]]:
    return {
        tool.name: {
            "name": tool.name,
            "description": getattr(tool, "description", None) or "",
            "schema": _mcp_value(
                tool,
                "input_schema",
                "inputSchema",
                default={"type": "object", "properties": {}},
            ),
        }
        for tool in tools
    }


class ToolOutput:
    def __init__(self, name: str, kwargs: dict[str, Any], result: Any):
        self.name = name
        self.kwargs = kwargs
        self.result = result

    def model_dump(self) -> dict[str, Any]:
        return json.loads(self.model_dump_json())

    def model_dump_json(self) -> str:
        return json.dumps(
            {"name": self.name, "kwargs": self.kwargs, "result": self.result},
            default=str,
        )

    def __str__(self) -> str:
        return self.model_dump_json()


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
        self._spawner = AgentSpawner(
            model=SETTINGS.client.model,
            base_url=SETTINGS.client.url,
            knowledge="",
            timeout_seconds=SETTINGS.client.timeout_seconds,
            api_key=SETTINGS.client.token,
        )

    async def _list_remote(self) -> dict[str, dict[str, Any]]:
        headers = {"Authorization": f"Bearer {SETTINGS.mcp.token}"}
        async with httpx2.AsyncClient(headers=headers, timeout=300) as client:
            async with streamable_http_client(SETTINGS.mcp.url, http_client=client) as streams:
                read, write = streams[0], streams[1]
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    response = await session.list_tools()
                    return tool_metadata(response.tools)

    async def _call_remote(self, name: str, kwargs: dict[str, Any]) -> Any:
        headers = {"Authorization": f"Bearer {SETTINGS.mcp.token}"}
        async with httpx2.AsyncClient(headers=headers, timeout=300) as client:
            async with streamable_http_client(SETTINGS.mcp.url, http_client=client) as streams:
                read, write = streams[0], streams[1]
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    response = await session.call_tool(name, kwargs)
                    structured = _mcp_value(
                        response, "structured_content", "structuredContent"
                    )
                    if structured is not None:
                        return structured
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
            self._schemas["agent_spawner"] = {
                "name": "agent_spawner",
                "description": "Spawn a bounded RCA evidence-gathering sub-agent.",
                "schema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "system_prompt": {"type": "string"},
                        "user_prompt": {"type": "string"},
                        "tools": {"type": "array", "items": {"type": "string"}},
                        "max_rounds": {"type": "integer", "minimum": 5, "maximum": 20, "default": 10},
                    },
                    "required": ["name", "system_prompt", "user_prompt", "tools"],
                },
            }
        return self._schemas

    def names(self) -> set[str]:
        return set(self._metadata())

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

    def usage_context(self, names: list[str]) -> str:
        metadata = self._metadata()
        return build_tool_usage_context(
            names, {name: metadata[name]["description"] for name in names if name in metadata}
        )

    def run(self, name: str, kwargs: dict[str, Any]):
        canonical = name.replace("__", ".")
        if canonical == "agent_spawner":
            result = self._spawner.run(**kwargs)
        else:
            try:
                result = asyncio.run(self._call_remote(canonical, kwargs))
            except Exception as exc:
                result = {"ok": False, "error": str(exc), "exception_type": type(exc).__name__}
        callback = _AUDIT.get()
        if callback:
            callback(canonical, kwargs, result)
        return ToolOutput(canonical, kwargs, result)


TOOL_REGISTRY = ToolRegistry()
