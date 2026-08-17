# RemediatorAgent

RemediatorAgent accepts explicitly approved RCA results, queues durable jobs,
and uses the remediation MCPTools profile. A started job is never automatically
retried after failure; ambiguous outcomes become `needs_review`.

The service receives the approved structured RCA snapshot as JSON, persists
tool-created artifacts separately, and returns their filenames in the completed
remediation result.
