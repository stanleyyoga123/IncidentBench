from ..domain.run_status import RunStatus


class ExperimentRunner:
    """Coordinate phases; phase classes own all operational details."""

    def __init__(self, phases, finalizer, metadata, log) -> None:
        self.phases = list(phases)
        self.finalizer = finalizer
        self.metadata = metadata
        self.log = log

    def run(self, context) -> int:
        returncode = 0
        try:
            for phase in self.phases:
                from ..artifacts.run_journal import timestamp
                context.metadata['current_phase'] = type(phase).__name__
                context.metadata['phase_started_at'] = timestamp()
                self.metadata.write(context.metadata)
                result = phase.execute(context)
                if result.failed:
                    context.metadata["status"] = result.status.value
                    returncode = result.returncode
                    break
            else:
                context.metadata["status"] = RunStatus.COMPLETED.value
                self.log("experiment completed")
        except KeyboardInterrupt:
            self.log("experiment interrupted")
            context.metadata["status"] = RunStatus.INTERRUPTED.value
            returncode = 130
        except Exception as exc:
            self.log(f"experiment failed: {exc!r}")
            context.metadata["status"] = RunStatus.FAILED.value
            context.metadata["error"] = repr(exc)
            returncode = 1
        finally:
            try:
                from ..artifacts.run_journal import timestamp
                context.metadata['phase_started_at'] = timestamp()
                context.metadata['current_phase'] = type(self.finalizer).__name__
                self.metadata.write(context.metadata)
                self.finalizer.execute(context)
            except Exception as exc:
                self.log(f"finalization failed: {exc!r}")
                context.metadata["finalization_error"] = repr(exc)
                if returncode == 0:
                    context.metadata["status"] = RunStatus.FAILED.value
                    returncode = 1
            finally:
                context.metadata["current_phase"] = None
                self.metadata.write(context.metadata)
                self.log(f"metadata written: {self.metadata.path}")
        return returncode
