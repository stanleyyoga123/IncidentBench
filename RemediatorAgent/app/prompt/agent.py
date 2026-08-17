FORCED_FINAL_ANSWER_PROMPT = """Stop calling tools now.

The agent is being forced to produce a final answer because the configured maximum iteration limit has been reached. Make this clear in the response.

Based only on the evidence, tool outputs, and reasoning already collected:

1. Summarize the best-supported conclusion.
2. State what evidence supports it.
3. Call out uncertainty, missing evidence, or assumptions.
4. Provide the most useful next steps or remediation plan.

Do not claim that the investigation is complete if important evidence is still missing. Do not request or call more tools.
"""

CONTEXT_TRIMMING_PROMPT = """The conversation history is approaching the context limit.

Create a compact but complete handoff summary that preserves all information required to continue the task without access to the original conversation.

Include the following sections:

1. Objective

   * The overall goal being worked on.
   * Any success criteria or constraints.

2. Completed Work

   * Key actions performed.
   * Decisions made and the reasoning behind them.
   * Problems encountered and how they were resolved.

3. Collected Information

   * Important facts, observations, findings, outputs, tool results, and data gathered so far.
   * Configuration values, parameters, identifiers, file paths, commands, URLs, or artifacts that may be needed later.
   * Any assumptions currently being used.

4. Current State

   * What has been completed.
   * What remains unfinished.
   * Any blockers, risks, or open questions.

5. Next Actions

   * The exact next steps that should be executed.
   * Prioritized in order.

6. Critical Context to Preserve

   * Information that would be expensive, difficult, or impossible to rediscover.
   * User preferences, constraints, and previously rejected approaches.

Requirements:

* Preserve factual accuracy.
* Do not omit important technical details.
* Remove repetitive discussion and irrelevant content.
* Use concise bullet points.
* Optimize for maximum information retention per token.
* Assume the summary will be the only context available in the next conversation.
"""


REMEDIATOR_EXECUTION_PROMPT = """Create and execute the remediation artifact for the plan below.

This RemediatorAgent job is allowed to perform the explicitly approved, scoped cluster action. Do not expand beyond the approved RCA plan.

Before creating or executing a mutating artifact, validate the current cluster state with direct, read-only `kubectl` tool calls. Never validate via Ansible: do not put validation tasks in the playbook and do not use `remediator.run_ansible` for state checks. If direct `kubectl` validation fails or is unavailable, report it as blocked or unknown and do not fall back to Ansible. Use checks relevant to the target and expected outcome, such as node `Ready` status, pod readiness and placement, deployment replicas, or rollout status. Follow the relocation scope approved by the orchestrator: for one workload, inspect the full pod template and existing scheduling constraints, confirm an eligible Ready destination with capacity, and implement one reversible Deployment pod-template affinity patch without separately deleting a pod or restarting the rollout; for a node evacuation, validate every resident workload, replacement capacity, disruption budgets, local-data impact, and control-plane risk, then use the allowed cordon/drain/conditional-uncordon workflow on that one node. Then use `remediator.write_file` to create files. In a later tool round, use `remediator.run_ansible` to run check mode. If the action passes hard guardrails, you must execute the live run with `check=false`. After execution, verify the resulting state with direct, read-only `kubectl` tool calls. For workload relocation, prove that the rollout is complete, desired availability is preserved, and all target pods are Ready outside the avoided node. For node evacuation, prove the intended schedulability state, confirm evictable pods have left the node, and verify relocated workloads are Ready and available. Only stop after validation when hard guardrails block every scoped action.

Final output must use compact headings and bullet points, including one `Changes` bullet per target in the form `<resource> <namespace>/<name>: <previous state> -> <current state>`. Under `Verification`, explicitly state that validation was performed with direct `kubectl` rather than Ansible and summarize each check's observed result or failure. Do not use explanatory paragraphs or include generated Ansible playbooks, Kubernetes manifests, raw stdout, runner artifact paths, or full execution feedback. Those artifacts are captured by tools and stored by the application.

Active MCP remediation session ID: {session_id}

Approved workflow context:
{prompt}

Approved RCA result:
{orchestration_output}
"""
