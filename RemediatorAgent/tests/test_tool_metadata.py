import json
from types import SimpleNamespace

from agent import Agent
from registry.tool import ToolOutput, tool_metadata


def test_tool_metadata_reads_mcp_v2_snake_case_schema():
    tools = [
        SimpleNamespace(
            name="kubectl",
            description="read-only kubectl",
            input_schema={"type": "object", "properties": {"command": {"type": "string"}}},
        )
    ]

    metadata = tool_metadata(tools)

    assert metadata["kubectl"]["schema"]["properties"]["command"]["type"] == "string"
    assert metadata["kubectl"]["description"] == "read-only kubectl"


def test_tool_output_serializes_result_for_langfuse():
    output = ToolOutput(
        name="kubectl",
        kwargs={"command": "get pods"},
        result={"ok": True, "stdout": "checkoutservice 1/1 Running"},
    )

    payload = Agent._serialize_tool_output(output)

    assert payload == {
        "name": "kubectl",
        "kwargs": {"command": "get pods"},
        "result": {"ok": True, "stdout": "checkoutservice 1/1 Running"},
    }
    assert "ToolOutput object" not in json.dumps(payload)
    assert "ToolOutput object" not in str(output)
