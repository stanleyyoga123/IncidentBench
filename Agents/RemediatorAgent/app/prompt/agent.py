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

Follow the system policy in this order:
1. Validate the approved target, current state, continued need for intervention, and safety with direct read-only `kubectl` calls and relevant observability tools. Preserve existing placement and data requirements. If the plan is stale, no longer needed, unsafe, or cannot be validated, stop with validation-only or blocked output for review; do not invent a substitute action.
2. Use `remediator.write_file` with this job's explicit session_id to create the scoped mutation artifact. Keep validation and verification outside the playbook. Preserve enough prior state for the approved rollback.
3. In a later tool round, run Ansible check mode. Command tasks may be skipped in check mode, so success is not proof that Kubernetes will accept the mutation or that execution is safe. Execute with `check=false` only after check mode succeeds and the current-state guardrails pass. Do not retry an ambiguous live mutation.
4. After execution, verify both the resulting Kubernetes state with direct read-only `kubectl` and the affected service's health with `prometheus`, plus any condition-specific checks required by the plan. Compare current measurements with pre-action evidence over a bounded, relevant observation window. Report Recovery as verified only if all approved checks pass; report not-recovered or unknown otherwise. Do not substitute command success or pod readiness for symptom recovery.

For a workload relocation, verify rollout completion, preserved availability, scheduling constraints, and Ready pods outside the avoided node. For node maintenance, verify schedulability, safe evacuation, replacement workload availability, and condition-specific recovery. Do not weaken existing constraints, discard non-disposable local data, force eviction, or uncordon an impaired node to finish the task.

Final output must use compact headings and bullet points, including one `Changes` bullet per target in the form `<resource> <namespace>/<name>: <previous state> -> <current state>`. Under `Verification`, summarize direct `kubectl` state checks and observability checks, including their windows, measured results, and any failures. Do not use explanatory paragraphs or include generated Ansible playbooks, Kubernetes manifests, raw stdout, runner artifact paths, or full execution feedback. Those artifacts are captured by tools and stored by the application.

Active MCP remediation session ID: {session_id}

Approved workflow context:
{prompt}

Approved RCA result:
{orchestration_output}
"""
