import json
from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel

from common.constant import TOOLS_METADATA_PATH
from common.decorator import log_runtime
from schema.tool import TOOL_SCHEMAS, ToolCallOutput
from prompt.knowledge import CLUSTER_KNOWLEDGE
from registry.tool_context import build_tool_usage_context
from tools import (
    AgentSpawner,
    ClusterProfileTool,
    JaegerTool,
    KubectlTool,
    LokiTool,
    NetworkTool,
    PrometheusTool,
    RemediatorTool,
)

from config import SETTINGS


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    schema: type[BaseModel]
    fn: Callable[..., dict[str, Any]]


class ToolRegistry:
    def __init__(self) -> None:
        with open(TOOLS_METADATA_PATH) as file:
            self._metadata = json.load(file)
        self._tools = self._build_tools()

    def describe(self, names: list[str] | None = None) -> str:
        selected = names or list(self._tools)
        return json.dumps(
            [
                {
                    "name": self._tools[name].name,
                    "description": self._tools[name].description,
                    "schema": self._tools[name].schema.model_json_schema(),
                }
                for name in selected
                if name in self._tools
            ]
        )

    def describe_openai_format(self, names: list[str]) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": self._to_openai_function_name(self._tools[name].name),
                    "description": self._tools[name].description,
                    "parameters": self._tools[name].schema.model_json_schema(),
                },
            }
            for name in names
            if name in self._tools
        ]

    def names(self) -> set[str]:
        return set(self._tools)

    def usage_context(self, names: list[str]) -> str:
        return build_tool_usage_context(
            names=names,
            descriptions={
                name: self._tools[name].description
                for name in names
                if name in self._tools
            },
        )

    def run(self, name: str, kwargs: dict[str, Any]) -> ToolCallOutput:
        try:
            tool_name = self._from_openai_function_name(name)
            tool = self._tools[tool_name]
            args = tool.schema(**kwargs)
            result = tool.fn(**args.model_dump())
            return ToolCallOutput(name=tool_name, kwargs=kwargs, result=result)
        except Exception as exc:
            return ToolCallOutput(
                name=name,
                kwargs=kwargs,
                result={
                    "ok": False,
                    "error": str(exc),
                    "exception_type": type(exc).__name__,
                },
            )

    def _build_tools(self) -> dict[str, Tool]:
        kubectl = KubectlTool(**SETTINGS.tools.kubectl.model_dump())
        prometheus = PrometheusTool(**SETTINGS.tools.prometheus.model_dump())
        loki = LokiTool(**SETTINGS.tools.loki.model_dump())
        jaeger = JaegerTool(**SETTINGS.tools.jaeger.model_dump())
        network = NetworkTool(
            path=SETTINGS.tools.kubectl.path,
            **SETTINGS.tools.network.model_dump(),
        )
        profile = ClusterProfileTool(
            kubectl=kubectl,
            prometheus=prometheus,
            loki=loki,
            network=network,
        )
        remediator = RemediatorTool()
        agent_spawner = AgentSpawner(
            model=SETTINGS.client.params.model,
            base_url=SETTINGS.client.params.url,
            knowledge=CLUSTER_KNOWLEDGE,
            timeout_seconds=SETTINGS.client.params.timeout_seconds,
        )

        handlers: dict[str, Callable[..., dict[str, Any]]] = {
            "kubectl": kubectl.run,
            "prometheus": prometheus.query,
            "loki": loki.query,
            "jaeger.list_services": jaeger.list_services,
            "jaeger.retrieve_slow_traces": jaeger.retrieve_slow_traces,
            "jaeger.investigate_trace": jaeger.investigate_trace,
            "jaeger.retrieve_bottleneck": jaeger.retrieve_bottleneck,
            "network.topology": network.topology,
            "network.latency_matrix": network.latency_matrix,
            "network.bandwidth": network.bandwidth,
            "network.path": network.path,
            "network.dns": network.dns,
            "network.tcp_connect": network.tcp_connect,
            "cluster.profile_baseline": profile.profile_baseline,
            "agent_spawner": agent_spawner.run,
            "remediator.write_file": remediator.write_file,
            "remediator.run_ansible": remediator.run_ansible,
        }

        tools = {}
        for item in self._metadata:
            name = item["name"]
            tools[name] = Tool(
                name=name,
                description=item["description"],
                schema=TOOL_SCHEMAS[name],
                fn=log_runtime()(handlers[name]),
            )
        return tools

    def _to_openai_function_name(self, name: str) -> str:
        return name.replace(".", "__")

    def _from_openai_function_name(self, name: str) -> str:
        return name.replace("__", ".")


TOOL_REGISTRY = ToolRegistry()
