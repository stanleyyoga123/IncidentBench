import argparse
import json
import os
import sys
import types
from typing import Any

ROOT = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

# The registry imports remediation tools too. This script does not use them, so keep it runnable without ansible_runner installed.
if "ansible_runner" not in sys.modules:
    ansible_runner = types.ModuleType("ansible_runner")

    def _missing_ansible_runner(*_: Any, **__: Any) -> None:
        raise RuntimeError("ansible_runner is not installed")

    ansible_runner.run = _missing_ansible_runner
    sys.modules["ansible_runner"] = ansible_runner

from config import SETTINGS  # noqa: E402
from registry.tool import TOOL_REGISTRY  # noqa: E402


def run_tool(name: str, kwargs: dict[str, Any]) -> dict[str, Any]:
    return TOOL_REGISTRY.run(name, kwargs).model_dump()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check whether the configured Jaeger tool works and sample traces for a service."
    )
    parser.add_argument(
        "--service",
        default="frontend.online-boutique",
        help="Jaeger service name to sample.",
    )
    parser.add_argument(
        "--limit", type=int, default=5, help="Number of trace samples to request."
    )
    parser.add_argument(
        "--lookback", default="30m", help="Jaeger lookback window, e.g. 15m, 30m, 1h."
    )
    args = parser.parse_args()

    print(f"Jaeger base URL: {SETTINGS.tools.jaeger.base_url}")

    slow_trace_check = run_tool(
        "jaeger.retrieve_slow_traces",
        {
            "service": args.service,
            "lookback": args.lookback,
            "limit": args.limit,
        }
    )
    slow_trace_result = slow_trace_check.get("result", {})
    traces = slow_trace_result.get("traces") or []
    first_trace_id = traces[0].get("traceID") if traces else None
    bottleneck_result = None
    if first_trace_id:
        bottleneck_result = run_tool(
            "jaeger.retrieve_bottleneck",
            {"trace_id": first_trace_id}
        ).get("result")

    output = {
        "working": bool(slow_trace_result.get("ok")),
        "service": args.service,
        "lookback": args.lookback,
        "requested_samples": args.limit,
        "returned_samples": len(traces),
        "trace_error": None if slow_trace_result.get("ok") else slow_trace_result,
        "samples": traces[: args.limit],
        "first_trace_bottleneck": bottleneck_result,
    }
    print(json.dumps(output, indent=2, default=str))
    return 0 if output["working"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
