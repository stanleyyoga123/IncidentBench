from unittest import TestCase

from prompt.agent import REMEDIATOR_EXECUTION_PROMPT
from prompt.expert import AGENT_ORCHESTRATOR_PROMPT, REMEDIATOR_PROMPT


class RemediatorPromptTest(TestCase):
    def test_orchestrator_requires_service_and_node_baseline_profiles(self):
        self.assertIn(
            "## Mandatory Baseline Profiling Workflow",
            AGENT_ORCHESTRATOR_PROMPT,
        )
        self.assertIn(
            "Baseline profiling is the first investigation gate",
            AGENT_ORCHESTRATOR_PROMPT,
        )
        self.assertIn(
            "Your first tool call must be `cluster.profile_baseline`",
            AGENT_ORCHESTRATOR_PROMPT,
        )
        self.assertIn(
            "every current cluster node",
            AGENT_ORCHESTRATOR_PROMPT,
        )
        self.assertIn(
            "discovers every current Deployment in the namespace",
            AGENT_ORCHESTRATOR_PROMPT,
        )
        self.assertIn(
            "aggregate Prometheus service/node metrics",
            AGENT_ORCHESTRATOR_PROMPT,
        )
        self.assertIn(
            "do not spawn an agent",
            AGENT_ORCHESTRATOR_PROMPT,
        )
        self.assertIn(
            "passive overlay/underlay probe coverage",
            AGENT_ORCHESTRATOR_PROMPT,
        )
        self.assertIn(
            "Baseline Profile: compact per-service and per-node coverage",
            AGENT_ORCHESTRATOR_PROMPT,
        )

    def test_requires_direct_kubectl_for_state_validation(self):
        self.assertIn(
            "Use the `kubectl` tool directly for all read-only pre-action validation",
            REMEDIATOR_PROMPT,
        )
        self.assertIn("Never validate through Ansible", REMEDIATOR_PROMPT)
        self.assertIn("do not fall back to Ansible validation", REMEDIATOR_PROMPT)
        self.assertIn("named node reports `Ready`", REMEDIATOR_PROMPT)
        self.assertIn(
            "validation used direct `kubectl` and was not performed through Ansible",
            REMEDIATOR_PROMPT,
        )

    def test_execution_prompt_keeps_validation_out_of_ansible(self):
        self.assertIn(
            "validate the current cluster state with direct, read-only `kubectl`",
            REMEDIATOR_EXECUTION_PROMPT,
        )
        self.assertIn(
            "Never validate via Ansible",
            REMEDIATOR_EXECUTION_PROMPT,
        )
        self.assertIn(
            "verify the resulting state with direct, read-only `kubectl`",
            REMEDIATOR_EXECUTION_PROMPT,
        )
        self.assertIn(
            "explicitly state that validation was performed with direct `kubectl` rather than Ansible",
            REMEDIATOR_EXECUTION_PROMPT,
        )

    def test_orchestrator_can_recommend_scoped_workload_relocation(self):
        self.assertIn(
            "active workload anomaly is isolated to pods on one node",
            AGENT_ORCHESTRATOR_PROMPT,
        )
        self.assertIn(
            "reversible pod-template scheduling constraint", AGENT_ORCHESTRATOR_PROMPT
        )
        self.assertIn("namespaced workload placement change", AGENT_ORCHESTRATOR_PROMPT)
        self.assertIn(
            "prefer cordon and drain when multiple workloads", AGENT_ORCHESTRATOR_PROMPT
        )

    def test_orchestrator_checks_impact_beyond_detector_named_service(self):
        self.assertIn(
            "investigation entry point, not as the guaranteed root cause or the complete blast radius",
            AGENT_ORCHESTRATOR_PROMPT,
        )
        self.assertIn(
            "direct upstream and downstream dependencies", AGENT_ORCHESTRATOR_PROMPT
        )
        self.assertIn("workloads sharing an implicated node", AGENT_ORCHESTRATOR_PROMPT)
        self.assertIn("services with confirmed impact", AGENT_ORCHESTRATOR_PROMPT)
        self.assertIn("Impact Scope:", AGENT_ORCHESTRATOR_PROMPT)

    def test_orchestrator_enforces_jaeger_discovery_workflow(self):
        self.assertIn("## Jaeger Trace Workflow", AGENT_ORCHESTRATOR_PROMPT)
        self.assertIn(
            "always include both `jaeger.list_services` and `jaeger.retrieve_slow_traces`",
            AGENT_ORCHESTRATOR_PROMPT,
        )
        self.assertIn(
            "Never expose `jaeger.investigate_trace` or `jaeger.retrieve_bottleneck` without also exposing both prerequisite tools",
            AGENT_ORCHESTRATOR_PROMPT,
        )
        list_services_position = AGENT_ORCHESTRATOR_PROMPT.index(
            "The agent's first Jaeger call must be `jaeger.list_services`"
        )
        slow_traces_position = AGENT_ORCHESTRATOR_PROMPT.index(
            "It must then call `jaeger.retrieve_slow_traces`"
        )
        self.assertLess(list_services_position, slow_traces_position)
        self.assertIn(
            "before `jaeger.investigate_trace` or `jaeger.retrieve_bottleneck` may be called",
            AGENT_ORCHESTRATOR_PROMPT,
        )
        self.assertIn(
            "do not call either trace-level tool with a guessed service name or trace ID",
            AGENT_ORCHESTRATOR_PROMPT,
        )

    def test_remediator_uses_one_affinity_patch_for_relocation(self):
        self.assertIn("## Workload Relocation", REMEDIATOR_PROMPT)
        self.assertIn(
            "requiredDuringSchedulingIgnoredDuringExecution", REMEDIATOR_PROMPT
        )
        self.assertIn("operator: NotIn", REMEDIATOR_PROMPT)
        self.assertIn(
            "do not separately delete pods or run `rollout restart`", REMEDIATOR_PROMPT
        )
        self.assertIn("every replacement pod", REMEDIATOR_PROMPT)
        self.assertIn(
            "one reversible Deployment pod-template affinity patch",
            REMEDIATOR_EXECUTION_PROMPT,
        )

    def test_remediator_supports_node_level_relocation(self):
        self.assertIn("## Node-Level Relocation", REMEDIATOR_PROMPT)
        self.assertIn("allowed `cordon` and `drain` workflow", REMEDIATOR_PROMPT)
        self.assertIn(
            "Leave the node cordoned when continued isolation is required",
            REMEDIATOR_PROMPT,
        )
        self.assertIn("conditional `uncordon`", REMEDIATOR_PROMPT)
        self.assertIn("for a node evacuation", REMEDIATOR_EXECUTION_PROMPT)
