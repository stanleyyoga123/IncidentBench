from ..artifacts.metadata_repository import MetadataRepository
from ..domain.experiment_context import ExperimentContext
from ..domain.phase_result import PhaseResult


class PhaseSupport:
    def __init__(self, metadata: MetadataRepository, log) -> None:
        self.metadata = metadata
        self.log = log

    def record(self, context: ExperimentContext, result: PhaseResult) -> PhaseResult:
        context.phase_results.append(result)
        context.metadata.setdefault("phases", []).append(
            {
                "name": result.name,
                "status": result.status.value,
                "returncode": result.returncode,
                "details": result.details,
            }
        )
        self.metadata.write(context.metadata)
        return result


def failed_command(result: dict) -> dict | None:
    if result.get("returncode", 0) == 0:
        return None
    deployments = result.get("deployments")
    if deployments:
        return next(
            (value for value in deployments.values() if value["returncode"] != 0),
            result,
        )
    return result
