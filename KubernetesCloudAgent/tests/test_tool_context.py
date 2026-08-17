from unittest import TestCase

from registry.tool_context import build_tool_usage_context


class ToolContextTest(TestCase):
    def test_builds_context_for_selected_tools_only(self):
        context = build_tool_usage_context(
            names=["prometheus", "kubectl"],
            descriptions={
                "kubectl": "Run kubectl.",
                "prometheus": "Run PromQL.",
                "loki": "Run LogQL.",
            },
        )

        self.assertIn("# Available Tool Operating Guide", context)
        self.assertIn("## prometheus", context)
        self.assertIn("Description: Run PromQL.", context)
        self.assertIn("### Prometheus Metric Reference", context)
        self.assertIn("`traffic_rps`", context)
        self.assertIn("istio_requests_total", context)
        self.assertIn("`response_time_p95_seconds`", context)
        self.assertIn("istio_request_duration_milliseconds_bucket", context)
        self.assertIn("container_memory_working_set_bytes", context)
        self.assertIn("node_netstat_Tcp_RetransSegs", context)
        self.assertIn("node_network_receive_drop_total", context)
        self.assertNotIn("histogram_quantile", context)
        self.assertIn("## kubectl", context)
        self.assertIn("Description: Run kubectl.", context)
        self.assertIn(
            "Kubernetes Events are intentionally excluded",
            context,
        )
        self.assertNotIn("## loki", context)
        self.assertNotIn("Description: Run LogQL.", context)

    def test_ignores_unknown_and_duplicate_tools(self):
        context = build_tool_usage_context(
            names=["kubectl", "unknown", "kubectl"],
            descriptions={"kubectl": "Run kubectl."},
        )

        self.assertEqual(context.count("## kubectl"), 1)
        self.assertNotIn("unknown", context)

    def test_returns_empty_string_when_no_known_tools(self):
        context = build_tool_usage_context(
            names=["unknown"],
            descriptions={"kubectl": "Run kubectl."},
        )

        self.assertEqual(context, "")

    def test_profile_context_describes_latency_bound(self):
        context = build_tool_usage_context(
            names=["cluster.profile_baseline"],
            descriptions={"cluster.profile_baseline": "Build baseline."},
        )

        self.assertIn("ten ICMP samples", context)
        self.assertIn("no active path, DNS, TCP-connect, or bandwidth probes", context)
