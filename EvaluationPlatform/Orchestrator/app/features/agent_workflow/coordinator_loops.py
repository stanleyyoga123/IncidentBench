import logging
import threading

from features.agent_workflow.workflow_coordinator import WorkflowCoordinator
from infrastructure.workflow_conflict_error import WorkflowConflictError

LOGGER = logging.getLogger("AgentOrchestrator")


class CoordinatorLoops:
    def __init__(
        self,
        coordinator: WorkflowCoordinator,
        intake_interval: float,
        reconcile_interval: float,
    ) -> None:
        self._coordinator = coordinator
        self._intake_interval = intake_interval
        self._reconcile_interval = reconcile_interval
        self._stop_event = threading.Event()
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        self._threads = [
            threading.Thread(target=self._intake_loop, daemon=True),
            threading.Thread(target=self._reconcile_loop, daemon=True),
        ]
        for thread in self._threads:
            thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        for thread in self._threads:
            thread.join(timeout=10)

    def _intake_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._coordinator.intake_once()
            except WorkflowConflictError:
                LOGGER.debug("Intake paused by evaluation maintenance")
            except Exception:
                LOGGER.exception("Intake iteration failed")
            self._stop_event.wait(self._intake_interval)

    def _reconcile_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._coordinator.reconcile_once()
            except WorkflowConflictError:
                LOGGER.debug("Reconcile paused by evaluation maintenance")
            except Exception:
                LOGGER.exception("Reconcile iteration failed")
            self._stop_event.wait(self._reconcile_interval)
