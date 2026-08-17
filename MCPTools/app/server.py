from __future__ import annotations

import contextlib
import secrets
import shlex
from datetime import datetime
from typing import Any

from mcp.server.mcpserver import MCPServer
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from config import Settings, get_settings
from tools import (
    ClusterProfileTool,
    JaegerTool,
    KubectlTool,
    LokiTool,
    NetworkTool,
    PrometheusTool,
    RemediatorTool,
)


READ_KUBECTL_COMMANDS = {
    "api-resources", "api-versions", "auth", "cluster-info", "describe",
    "get", "logs", "rollout", "top", "version",
}


class BearerMiddleware:
    def __init__(self, app, token: str):
        self.app = app
        self.token = token

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("path") != "/health":
            headers = {key.lower(): value for key, value in scope.get("headers", [])}
            supplied = headers.get(b"authorization", b"").decode()
            expected = f"Bearer {self.token}"
            if not secrets.compare_digest(supplied, expected):
                response = JSONResponse({"detail": "invalid bearer token"}, status_code=401)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


def create_server(settings: Settings | None = None):
    settings = settings or get_settings()
    kubectl = KubectlTool(**settings.tools.kubectl.model_dump())
    prometheus = PrometheusTool(**settings.tools.prometheus.model_dump())
    loki = LokiTool(**settings.tools.loki.model_dump())
    jaeger = JaegerTool(**settings.tools.jaeger.model_dump())
    network = NetworkTool(
        path=settings.tools.kubectl.path,
        **settings.tools.network.model_dump(),
    )
    profile = ClusterProfileTool(kubectl, prometheus, loki, network)
    remediator = RemediatorTool(settings.tools.remediation_root)
    mcp = MCPServer(
        "MCPTools",
        version="1.0.0",
        instructions=f"Tool profile: {settings.server.profile}",
    )

    @mcp.tool(name="kubectl", structured_output=True)
    def kubectl_tool(
        args: str | list[str], grep: str | None = None, timeout_seconds: int | None = None
    ) -> dict[str, Any]:
        tokens = shlex.split(args) if isinstance(args, str) else list(args)
        if settings.server.profile == "investigation":
            command = next((token for token in tokens if not token.startswith("-")), "")
            if command not in READ_KUBECTL_COMMANDS:
                return {"ok": False, "blocked": True, "error": "mutating kubectl command blocked by investigation profile"}
            if command == "rollout" and "status" not in tokens:
                return {"ok": False, "blocked": True, "error": "only rollout status is allowed"}
        return kubectl.run(args, grep, timeout_seconds)

    @mcp.tool(name="prometheus", structured_output=True)
    def prometheus_tool(
        promql: str, query_type: str = "instant", time: str | None = None,
        start: str | None = None, end: str | None = None,
        step: str | None = None, filter: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return prometheus.query(promql, query_type, time, start, end, step, filter)

    @mcp.tool(name="loki", structured_output=True)
    def loki_tool(
        logql: str, query_type: str = "range", start: str | None = None,
        end: str | None = None, since: str | None = None, limit: int = 100,
        direction: str = "BACKWARD", filter: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return loki.query(logql, query_type, start, end, since, limit, direction, filter)

    @mcp.tool(name="jaeger.list_services", structured_output=True)
    def jaeger_list_services() -> dict[str, Any]:
        return jaeger.list_services()

    @mcp.tool(name="jaeger.retrieve_slow_traces", structured_output=True)
    def jaeger_slow_traces(
        service: str = "frontend.online-boutique", lookback: str = "30m",
        limit: int = 5, min_duration: str | None = None,
        max_duration: str | None = None,
    ) -> dict[str, Any]:
        return jaeger.retrieve_slow_traces(service, lookback, limit, min_duration, max_duration)

    @mcp.tool(name="jaeger.investigate_trace", structured_output=True)
    def jaeger_investigate_trace(trace_id: str) -> dict[str, Any]:
        return jaeger.investigate_trace(trace_id)

    @mcp.tool(name="jaeger.retrieve_bottleneck", structured_output=True)
    def jaeger_retrieve_bottleneck(trace_id: str) -> dict[str, Any]:
        return jaeger.retrieve_bottleneck(trace_id)

    @mcp.tool(name="network.topology", structured_output=True)
    def network_topology(plane: str = "both") -> dict[str, Any]:
        return network.topology(plane)

    @mcp.tool(name="network.latency_matrix", structured_output=True)
    def network_latency_matrix(
        plane: str = "both", source_nodes: list[str] | None = None,
        target_nodes: list[str] | None = None, count: int = 5,
        include_self: bool = False,
    ) -> dict[str, Any]:
        return network.latency_matrix(plane, source_nodes, target_nodes, count, include_self)

    @mcp.tool(name="network.bandwidth", structured_output=True)
    def network_bandwidth(
        source_node: str, target_node: str, plane: str = "overlay",
        protocol: str = "tcp", direction: str = "forward",
        duration_seconds: int = 5, bitrate_mbps: int = 50,
    ) -> dict[str, Any]:
        return network.bandwidth(source_node, target_node, plane, protocol, direction, duration_seconds, bitrate_mbps)

    @mcp.tool(name="network.path", structured_output=True)
    def network_path(
        source_node: str, target_node: str, plane: str = "overlay",
        protocol: str = "icmp", cycles: int = 5,
    ) -> dict[str, Any]:
        return network.path(source_node, target_node, plane, protocol, cycles)

    @mcp.tool(name="network.dns", structured_output=True)
    def network_dns(
        source_node: str, query: str, plane: str = "overlay",
        record_type: str = "A", timeout_seconds: int = 2, retries: int = 1,
    ) -> dict[str, Any]:
        return network.dns(source_node, query, plane, record_type, timeout_seconds, retries)

    @mcp.tool(name="network.tcp_connect", structured_output=True)
    def network_tcp_connect(
        source_node: str, namespace: str, service: str, port: int,
        plane: str = "overlay", attempts: int = 3, timeout_seconds: int = 2,
    ) -> dict[str, Any]:
        return network.tcp_connect(source_node, namespace, service, port, plane, attempts, timeout_seconds)

    @mcp.tool(name="cluster.profile_baseline", structured_output=True)
    def cluster_profile_baseline(
        namespace: str = "online-boutique", window_minutes: int = 30,
        evaluation_time: str | None = None, include_error_samples: bool = True,
    ) -> dict[str, Any]:
        return profile.profile_baseline(namespace, window_minutes, evaluation_time, include_error_samples)

    if settings.server.profile == "remediation":
        @mcp.tool(name="remediator.write_file", structured_output=True)
        def remediation_write_file(session_id: str, filename: str, content: str) -> dict[str, Any]:
            return remediator.write_file(session_id, filename, content)

        @mcp.tool(name="remediator.run_ansible", structured_output=True)
        def remediation_run_ansible(
            session_id: str, playbook_file: str = "remediation.yml",
            inventory_file: str | None = None, check: bool = True,
            extra_vars: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            return remediator.run_ansible(session_id, playbook_file, inventory_file, check, extra_vars)

    return mcp


def create_app(settings: Settings | None = None):
    settings = settings or get_settings()
    mcp = create_server(settings)
    mcp_app = mcp.streamable_http_app(
        streamable_http_path="/", stateless_http=True, json_response=True
    )

    async def health(_request: Request):
        return JSONResponse({"status": "ok", "profile": settings.server.profile})

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        async with mcp.session_manager.run():
            yield

    root = Starlette(
        routes=[Route("/health", health), Mount("/mcp", app=mcp_app)],
        lifespan=lifespan,
    )
    return BearerMiddleware(root, settings.server.token)
