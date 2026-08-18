import time

from ...chaos.catalog.chaos_catalog import ChaosCatalog
from ...command.command_logger import CommandLogger
from ...domain.scenario import ScenarioStep
from ...kubernetes.chaos_schedule_client import ChaosScheduleClient
from .execution_context import ChaosExecutionContext
from .result_factory import finish_step, new_step_result, utc_now
from .schedule_cleaner import ScheduleCleaner


class ScheduledStepExecutor:
    def __init__(
        self,
        catalog: ChaosCatalog,
        client: ChaosScheduleClient,
        cleaner: ScheduleCleaner,
        logger: CommandLogger,
        *,
        monotonic=time.monotonic,
    ) -> None:
        self.catalog = catalog
        self.client = client
        self.cleaner = cleaner
        self.logger = logger
        self.monotonic = monotonic

    def execute(self, step: ScenarioStep, context: ChaosExecutionContext) -> dict:
        result = new_step_result(step)
        schedules = self.catalog.resolve_many(step.chaos)
        entries = []
        for schedule in schedules:
            entry = {
                "reference": schedule.reference,
                "resource": schedule.to_metadata()["resource"],
                "prepare": None,
                "apply": None,
                "cleanup": None,
            }
            entries.append(entry)
        result["schedules"] = entries
        interrupted = False
        failed = False
        active_started = None
        context.log(
            f"chaos step {step.index}: applying {len(schedules)} Schedule(s) "
            f"for {step.duration}s"
        )
        try:
            for schedule, entry in zip(schedules, entries):
                output = context.artifacts.chaos_schedule(
                    step.index, step.name, schedule.reference
                )
                entry["prepare"] = self.cleaner.clean(schedule, output, "prepare")
                if entry["prepare"]["returncode"] != 0:
                    failed = True
                    result["error"] = (
                        f"failed to remove stale Schedule {schedule.reference}"
                    )
                    break
            if not failed:
                for schedule, entry in zip(schedules, entries):
                    output = context.artifacts.chaos_schedule(
                        step.index, step.name, schedule.reference
                    )
                    apply = self.client.apply(schedule)
                    entry["apply"] = self.logger.write(apply, output, "apply")
                    if not apply.succeeded:
                        failed = True
                        result["error"] = f"failed to apply Schedule {schedule.reference}"
                        break
            if not failed:
                active_started = self.monotonic()
                result["active_started_at"] = utc_now()
                context.wait_until(step.duration, active_started)
        except KeyboardInterrupt:
            interrupted = True
            result["error"] = "interrupted by user"
        except Exception as exc:
            failed = True
            result["error"] = repr(exc)
        finally:
            result["cleanup_started_at"] = utc_now()
            cleanup_started = self.monotonic()
            if active_started is not None:
                result["actual_active_duration_seconds"] = max(
                    0.0, cleanup_started - active_started
                )
            cleanup_failed = False
            for schedule, entry in reversed(list(zip(schedules, entries))):
                output = context.artifacts.chaos_schedule(
                    step.index, step.name, schedule.reference
                )
                try:
                    entry["cleanup"] = self.cleaner.clean(
                        schedule, output, "cleanup"
                    )
                    cleanup_failed |= entry["cleanup"]["returncode"] != 0
                except KeyboardInterrupt:
                    interrupted = True
                    cleanup_failed = True
                    entry["cleanup"] = {
                        "returncode": 1,
                        "error": "interrupted during cleanup",
                    }
                except Exception as exc:
                    cleanup_failed = True
                    entry["cleanup"] = {"returncode": 1, "error": repr(exc)}
        if cleanup_failed:
            status = "cleanup_failed"
            if result["error"] is None:
                result["error"] = "one or more Schedules could not be safely removed"
        elif interrupted:
            status = "interrupted"
        elif failed:
            status = "failed"
        else:
            status = "completed"
        return finish_step(result, status)
