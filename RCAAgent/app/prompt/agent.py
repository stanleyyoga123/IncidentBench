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
