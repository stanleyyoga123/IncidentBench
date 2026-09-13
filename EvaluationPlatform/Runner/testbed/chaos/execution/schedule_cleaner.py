import time
from pathlib import Path

from ...command.command_logger import CommandLogger
from ...domain.chaos_schedule import ChaosSchedule
from ...kubernetes.chaos_schedule_client import ChaosScheduleClient
from .physical_machine_state_cleaner import PhysicalMachineStateCleaner


class ScheduleCleaner:
    def __init__(
        self,
        client: ChaosScheduleClient,
        logger: CommandLogger,
        physical_machine_cleaner: PhysicalMachineStateCleaner | None = None,
        *,
        timeout_seconds: int = 240,
        poll_seconds: int = 5,
        monotonic=time.monotonic,
        sleep=time.sleep,
    ) -> None:
        self.client = client
        self.logger = logger
        self.physical_machine_cleaner = physical_machine_cleaner
        self.timeout_seconds = timeout_seconds
        self.poll_seconds = poll_seconds
        self.monotonic = monotonic
        self.sleep = sleep

    def clean(
        self,
        schedule: ChaosSchedule,
        output_dir: Path,
        prefix: str,
    ) -> dict:
        delete = self.client.delete(schedule)
        delete_metadata = self.logger.write(delete, output_dir, f"{prefix}-delete")
        finalizer_recovery = None
        delete_retry_metadata = None
        if not delete.succeeded:
            recovery_results = self.client.recover_destroyed_experiment_finalizers()
            finalizer_recovery = {
                identity: self.logger.write(
                    result,
                    output_dir,
                    f"{prefix}-finalizer-{identity.replace('/', '-').replace('.', '-')}",
                )
                for identity, result in recovery_results.items()
            }
            if any(identity != "scan" for identity in recovery_results):
                delete = self.client.delete(schedule)
                delete_retry_metadata = self.logger.write(
                    delete,
                    output_dir,
                    f"{prefix}-delete-retry",
                )
        deadline = self.monotonic() + self.timeout_seconds
        attempts = []
        child_attempts = []
        absent = False
        schedule_absent = False
        children_absent = False
        periodic_finalizer_recovery = []
        next_recovery = self.monotonic() + max(
            30.0, schedule.child_duration_seconds + 5.0
        )
        while True:
            verification = self.client.get(schedule)
            attempt = self.logger.write(
                verification,
                output_dir,
                f"{prefix}-verify-{len(attempts) + 1:03d}",
            )
            attempts.append(attempt)
            child_verification = self.client.get_children(schedule)
            child_attempt = self.logger.write(
                child_verification,
                output_dir,
                f"{prefix}-children-verify-{len(child_attempts) + 1:03d}",
            )
            child_attempts.append(child_attempt)
            schedule_absent = (
                verification.returncode == 0 and not verification.stdout.strip()
            )
            children_absent = (
                child_verification.returncode == 0
                and not child_verification.stdout.strip()
            )
            if schedule_absent and children_absent:
                absent = True
                break
            now = self.monotonic()
            if now >= next_recovery:
                recovery_results = (
                    self.client.recover_destroyed_experiment_finalizers()
                )
                recovery_index = len(periodic_finalizer_recovery) + 1
                periodic_finalizer_recovery.append(
                    {
                        identity: self.logger.write(
                            result,
                            output_dir,
                            (
                                f"{prefix}-periodic-finalizer-{recovery_index:03d}-"
                                f"{identity.replace('/', '-').replace('.', '-')}"
                            ),
                        )
                        for identity, result in recovery_results.items()
                    }
                )
                next_recovery = now + 30.0
            remaining = deadline - now
            if remaining <= 0:
                break
            self.sleep(min(self.poll_seconds, remaining))
        physical_machine = None
        if absent and self.physical_machine_cleaner is not None:
            physical_machine = self.physical_machine_cleaner.clean_schedule(
                schedule,
                output_dir,
                f"{prefix}-physical-machine",
            )
        physical_machine_clean = (
            physical_machine is None or physical_machine["returncode"] == 0
        )
        return {
            "returncode": (
                0 if delete.succeeded and absent and physical_machine_clean else 1
            ),
            "delete": delete_metadata,
            "delete_retry": delete_retry_metadata,
            "finalizer_recovery": finalizer_recovery,
            "periodic_finalizer_recovery": periodic_finalizer_recovery,
            "verification": attempts,
            "child_verification": child_attempts,
            "schedule_absent": schedule_absent,
            "children_absent": children_absent,
            "absent": absent,
            "physical_machine": physical_machine,
        }
