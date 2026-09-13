class EvaluationRunnerError(Exception):
    """Base exception for unexpected runner failures."""


class ScenarioValidationError(EvaluationRunnerError):
    pass


class UnsafeCleanupError(EvaluationRunnerError):
    pass
