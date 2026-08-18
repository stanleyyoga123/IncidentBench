from types import SimpleNamespace

from registry.tool import tool_metadata


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
