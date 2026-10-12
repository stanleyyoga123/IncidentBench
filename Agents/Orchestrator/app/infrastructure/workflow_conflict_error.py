class WorkflowConflictError(RuntimeError):
    """An optimistic workflow or maintenance transition conflicts with current state."""
