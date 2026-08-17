import sys
import types
from unittest import TestCase

from pydantic import ValidationError

if "langfuse" not in sys.modules:
    langfuse = types.ModuleType("langfuse")
    langfuse.get_client = lambda: None
    langfuse.propagate_attributes = lambda **_: None
    sys.modules["langfuse"] = langfuse
    langfuse_openai = types.ModuleType("langfuse.openai")
    langfuse_openai.OpenAI = object
    sys.modules["langfuse.openai"] = langfuse_openai

if "openai.types.chat" not in sys.modules:
    openai = types.ModuleType("openai")
    openai_types = types.ModuleType("openai.types")
    openai_types_chat = types.ModuleType("openai.types.chat")
    openai_types_chat.ChatCompletionMessage = object
    sys.modules["openai"] = openai
    sys.modules["openai.types"] = openai_types
    sys.modules["openai.types.chat"] = openai_types_chat

if "ansible_runner" not in sys.modules:
    ansible_runner = types.ModuleType("ansible_runner")
    ansible_runner.run = lambda *_, **__: None
    sys.modules["ansible_runner"] = ansible_runner

from config import (
    JaegerToolSetting,
    KubectlToolSetting,
    LokiToolSetting,
    NetworkToolSetting,
    PrometheusToolSetting,
    ToolsSettings,
)
from manager.orchestrator import (
    ORCHESTRATOR_TOOL_NAMES,
    REMEDIATOR_TOOL_NAMES,
)
from prompt.expert import AGENT_ORCHESTRATOR_PROMPT
from registry.tool import TOOL_REGISTRY
from registry.tool_context import build_tool_usage_context
from schema.tool import ClusterProfileBaselineRequest, NetworkBandwidthRequest


NETWORK_TOOL_NAMES = {
    "network.topology",
    "network.latency_matrix",
    "network.bandwidth",
    "network.path",
    "network.dns",
    "network.tcp_connect",
}


class NetworkIntegrationTest(TestCase):
    def test_network_config_is_backward_compatible(self):
        settings = ToolsSettings(
            kubectl=KubectlToolSetting(path="kubectl", timeout_seconds=30),
            jaeger=JaegerToolSetting(
                base_url="http://jaeger",
                timeout_seconds=10,
            ),
            loki=LokiToolSetting(
                base_url="http://loki",
                timeout_seconds=10,
            ),
            prometheus=PrometheusToolSetting(
                base_url="http://prometheus",
                timeout_seconds=10,
            ),
        )

        self.assertEqual(settings.network, NetworkToolSetting())
        self.assertEqual(settings.network.namespace, "utility")
        self.assertEqual(settings.network.max_duration_seconds, 10)
        self.assertEqual(settings.network.max_bitrate_mbps, 100)
        self.assertEqual(settings.network.max_matrix_nodes, 6)

    def test_bandwidth_schema_enforces_hard_limits(self):
        with self.assertRaises(ValidationError):
            NetworkBandwidthRequest(
                source_node="worker-node-1",
                target_node="worker-node-2",
                duration_seconds=11,
            )
        with self.assertRaises(ValidationError):
            NetworkBandwidthRequest(
                source_node="worker-node-1",
                target_node="worker-node-2",
                bitrate_mbps=101,
            )

    def test_registry_exposes_all_network_tool_schemas(self):
        self.assertTrue(NETWORK_TOOL_NAMES.issubset(TOOL_REGISTRY.names()))

        schemas = TOOL_REGISTRY.describe_openai_format(sorted(NETWORK_TOOL_NAMES))
        names = {item["function"]["name"] for item in schemas}
        self.assertEqual(
            names,
            {name.replace(".", "__") for name in NETWORK_TOOL_NAMES},
        )
        bandwidth = next(
            item for item in schemas if item["function"]["name"] == "network__bandwidth"
        )
        properties = bandwidth["function"]["parameters"]["properties"]
        self.assertEqual(properties["duration_seconds"]["maximum"], 10)
        self.assertEqual(properties["bitrate_mbps"]["maximum"], 100)

    def test_network_usage_context_contains_safety_guidance(self):
        context = build_tool_usage_context(
            names=["network.latency_matrix", "network.bandwidth"],
            descriptions={
                "network.latency_matrix": "Measure latency.",
                "network.bandwidth": "Measure bandwidth.",
            },
        )

        self.assertIn("## network.latency_matrix", context)
        self.assertIn("Flannel VXLAN", context)
        self.assertIn("## network.bandwidth", context)
        self.assertIn("active traffic test", context)
        self.assertIn("never describe the capped result as physical line rate", context)

    def test_orchestrator_allows_exact_network_investigation_tools(self):
        for name in NETWORK_TOOL_NAMES:
            self.assertIn(f"`{name}`", AGENT_ORCHESTRATOR_PROMPT)
        self.assertIn(
            "Use `network.topology` before active probes",
            AGENT_ORCHESTRATOR_PROMPT,
        )

    def test_remediator_excludes_intrusive_network_tools(self):
        self.assertIn("network.topology", REMEDIATOR_TOOL_NAMES)
        self.assertIn("network.latency_matrix", REMEDIATOR_TOOL_NAMES)
        self.assertIn("network.dns", REMEDIATOR_TOOL_NAMES)
        self.assertIn("network.tcp_connect", REMEDIATOR_TOOL_NAMES)
        self.assertNotIn("network.bandwidth", REMEDIATOR_TOOL_NAMES)
        self.assertNotIn("network.path", REMEDIATOR_TOOL_NAMES)


class ClusterProfileIntegrationTest(TestCase):
    def test_profile_schema_is_bounded_and_registered(self):
        schema = ClusterProfileBaselineRequest.model_json_schema()

        self.assertIn("cluster.profile_baseline", TOOL_REGISTRY.names())
        self.assertEqual(
            schema["properties"]["window_minutes"]["minimum"],
            5,
        )
        self.assertEqual(
            schema["properties"]["window_minutes"]["maximum"],
            60,
        )
        openai_schema = TOOL_REGISTRY.describe_openai_format(
            ["cluster.profile_baseline"]
        )
        self.assertEqual(
            openai_schema[0]["function"]["name"],
            "cluster__profile_baseline",
        )

    def test_profiler_is_exposed_directly_to_orchestrator_only(self):
        self.assertEqual(
            ORCHESTRATOR_TOOL_NAMES,
            ["cluster.profile_baseline", "agent_spawner"],
        )
        self.assertNotIn(
            "cluster.profile_baseline",
            REMEDIATOR_TOOL_NAMES,
        )

    def test_profiler_usage_context_preserves_missing_evidence(self):
        context = build_tool_usage_context(
            names=["cluster.profile_baseline"],
            descriptions={"cluster.profile_baseline": "Build a baseline profile."},
        )

        self.assertIn("## cluster.profile_baseline", context)
        self.assertIn("first investigation call", context)
        self.assertIn("missing evidence", context)
        self.assertIn("active directed latency matrix", context.lower())
        self.assertIn("ten icmp samples per directed worker pair", context.lower())
        self.assertIn("no active path, dns, tcp-connect, or bandwidth probes", context.lower())

    def test_orchestrator_requires_profiler_before_spawning_agents(self):
        self.assertIn(
            "Your first tool call must be `cluster.profile_baseline`",
            AGENT_ORCHESTRATOR_PROMPT,
        )
        self.assertIn(
            "do not spawn an agent",
            AGENT_ORCHESTRATOR_PROMPT,
        )
        self.assertNotIn(
            "service-baseline-profiler",
            AGENT_ORCHESTRATOR_PROMPT,
        )
        self.assertNotIn(
            "node-baseline-profiler",
            AGENT_ORCHESTRATOR_PROMPT,
        )
