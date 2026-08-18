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
        timeout_seconds: int = 120,
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
        absent = False
        while True:
            verification = self.client.get(schedule)
            attempt = self.logger.write(
                verification,
                output_dir,
                f"{prefix}-verify-{len(attempts) + 1:03d}",
            )
            attempts.append(attempt)
            if verification.returncode == 0 and not verification.stdout.strip():
                absent = True
                break
            remaining = deadline - self.monotonic()
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
            "verification": attempts,
            "absent": absent,
            "physical_machine": physical_machine,
        }
