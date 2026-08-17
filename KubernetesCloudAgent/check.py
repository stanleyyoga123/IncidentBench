import argparse
import json
import os
import sys
import types
from collections.abc import Mapping, Sequence
from typing import Any

ROOT = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

# The registry imports every tool module, including remediation. This check does
# not call remediation tools, so keep it runnable in environments without
# ansible_runner installed.
if "ansible_runner" not in sys.modules:
    ansible_runner = types.ModuleType("ansible_runner")

    def _missing_ansible_runner(*_: Any, **__: Any) -> None:
        raise RuntimeError("ansible_runner is not installed")

    ansible_runner.run = _missing_ansible_runner
    sys.modules["ansible_runner"] = ansible_runner

from config import SETTINGS  # noqa: E402
from registry.tool import TOOL_REGISTRY  # noqa: E402

TOOL_NAMES = ["kubectl", "prometheus", "loki", "jaeger.retrieve_slow_traces"]
NETWORK_TOOL_NAMES = [
    "network.topology",
    "network.latency_matrix",
    "network.bandwidth",
    "network.path",
    "network.dns",
    "network.tcp_connect",
]


def compact(value: Any, max_string: int = 800) -> Any:
    if isinstance(value, Mapping):
        return {key: compact(child, max_string) for key, child in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [compact(item, max_string) for item in value[:10]]
    if isinstance(value, str) and len(value) > max_string:
        return value[:max_string] + f"...[truncated {len(value) - max_string} chars]"
    return value


def print_json(title: str, value: Any) -> None:
    print(f"\n=== {title} ===")
    print(json.dumps(compact(value), indent=2, default=str))


def summarize_tool_schema(tool: dict[str, Any]) -> dict[str, Any]:
    function = tool["function"]
    parameters = function.get("parameters", {})
    properties = parameters.get("properties", {})
    return {
        "name": function["name"],
        "description": function.get("description"),
        "arguments": sorted(properties),
        "required": parameters.get("required", []),
    }


def run_tool(name: str, kwargs: dict[str, Any]) -> dict[str, Any]:
    output = TOOL_REGISTRY.run(name, kwargs)
    return output.model_dump()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Smoke-test the kubectl, Prometheus, Loki, and Jaeger tools exposed to the model."
    )
    parser.add_argument(
        "--schemas-only",
        action="store_true",
        help="Only print the model-facing tool schemas; do not execute tool calls.",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Print unbounded JSON outputs instead of compact summaries.",
    )
    args = parser.parse_args()

    print_json(
        "configured endpoints",
        {
            "kubectl": {
                "path": SETTINGS.tools.kubectl.path,
                "timeout_seconds": SETTINGS.tools.kubectl.timeout_seconds,
            },
            "prometheus": {
                "base_url": SETTINGS.tools.prometheus.base_url,
                "timeout_seconds": SETTINGS.tools.prometheus.timeout_seconds,
            },
            "loki": {
                "base_url": SETTINGS.tools.loki.base_url,
                "timeout_seconds": SETTINGS.tools.loki.timeout_seconds,
            },
            "jaeger": {
                "base_url": SETTINGS.tools.jaeger.base_url,
                "timeout_seconds": SETTINGS.tools.jaeger.timeout_seconds,
            },
            "network": {
                "namespace": SETTINGS.tools.network.namespace,
                "overlay_selector": SETTINGS.tools.network.overlay_selector,
                "underlay_selector": SETTINGS.tools.network.underlay_selector,
                "timeout_seconds": SETTINGS.tools.network.timeout_seconds,
                "max_duration_seconds": SETTINGS.tools.network.max_duration_seconds,
                "max_bitrate_mbps": SETTINGS.tools.network.max_bitrate_mbps,
                "max_matrix_nodes": SETTINGS.tools.network.max_matrix_nodes,
            },
        },
    )

    exposed = TOOL_REGISTRY.describe_openai_format(
        [*TOOL_NAMES, *NETWORK_TOOL_NAMES]
    )
    print_json(
        "model-facing tool schemas", [summarize_tool_schema(tool) for tool in exposed]
    )

    if args.schemas_only:
        return 0

    smoke_calls = {
        "kubectl": {
            "args": ["version", "--client=true", "-o", "yaml"],
            "timeout_seconds": 10,
        },
        "prometheus": {
            "promql": "up",
            "query_type": "instant",
            "filter": {
                "include_paths": [
                    "ok",
                    "error",
                    "exception_type",
                    "url",
                    "status_code",
                    "content_type",
                    "body",
                    "data.status",
                    "data.data.resultType",
                    "data.data.result",
                ],
                "max_items": 20,
                "max_depth": 8,
                "max_string_length": 500,
            },
        },
        "loki": {
            "logql": '{namespace="online-boutique"}',
            "query_type": "range",
            "since": "5m",
            "limit": 5,
            "direction": "BACKWARD",
            "filter": {
                "include_paths": [
                    "ok",
                    "error",
                    "exception_type",
                    "url",
                    "status_code",
                    "content_type",
                    "body",
                    "data.status",
                    "data.data.resultType",
                    "data.data.result",
                ],
                "max_items": 20,
                "max_depth": 8,
                "max_string_length": 500,
            },
        },
        "jaeger.retrieve_slow_traces": {
            "service": "frontend.online-boutique",
            "lookback": "30m",
            "limit": 5,
        },
    }

    failures = 0
    for name in TOOL_NAMES:
        result = run_tool(name, smoke_calls[name])
        if not result.get("result", {}).get("ok"):
            failures += 1
        print_json(
            f"{name} smoke call",
            result if args.full else compact(result),
        )

    print(
        f"\nSmoke test complete: {len(TOOL_NAMES) - failures} passed, {failures} failed."
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
