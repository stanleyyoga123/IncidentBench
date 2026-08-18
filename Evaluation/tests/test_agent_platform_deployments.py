from testbed.constants import AGENT_DEPLOYMENTS


def test_split_agent_platform_scale_and_wait_contract():
    assert AGENT_DEPLOYMENTS == (
        "anomaly-detector",
        "agent-orchestrator",
        "rca-agent",
        "remediator-agent",
        "mcp-tools-investigation",
        "mcp-tools-remediation",
    )
