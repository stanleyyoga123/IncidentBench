import time
from typing import Any

from dotenv import load_dotenv

load_dotenv()

from common.logger.console import get_logger
from config import SETTINGS
from controller.postgres import PostgresAnomalyStore, get_postgres_store
from manager.orchestrator import AgentManager
from schema.anomaly import AnomalyBatch

LOGGER = get_logger("PostgresWorker")


class PostgresAnomalyWorker:
    def __init__(
        self,
        store: PostgresAnomalyStore,
        manager: AgentManager,
        poll_interval_seconds: int,
    ):
        self._store = store
        self._manager = manager
        self._poll_interval_seconds = poll_interval_seconds

    def run_forever(self) -> None:
        LOGGER.info("Postgres anomaly worker started")

        while True:
            try:
                processed_count = self.run_once()
            except Exception:
                LOGGER.exception("Worker loop failed")
                processed_count = 0

            if processed_count == 0:
                time.sleep(self._poll_interval_seconds)

    def run_once(self) -> int:
        self._store.move_detected_to_in_progress()
        in_progress = self._store.fetch_in_progress_anomalies()
        if not in_progress:
            return 0

        batch = AnomalyBatch.from_rows(in_progress)
        if not self._process_anomaly_batch(batch):
            return 0
        return len(batch.anomalies)

    def _process_anomaly_batch(self, batch: AnomalyBatch) -> bool:
        row_ids = batch.row_ids()
        LOGGER.info(f"Processing in-progress anomaly rows={row_ids}")
        try:
            result = self._manager.run_with_metadata(batch.to_manager_prompt())
            changes: dict[str, Any] = {
                "session_id": result.session_id,
                "remediation_required": result.remediation_required,
            }
            remediation_id = self._store.record_remediation_session_and_complete(
                session_id=result.session_id,
                batch=batch,
                remediation_output=result.remediation_output,
                changes=changes,
            )
        except Exception:
            LOGGER.exception(f"Failed in-progress anomaly rows={row_ids}")
            return False

        LOGGER.info(
            "Completed in-progress anomaly rows=%s remediation_required=%s remediation_id=%s: %s",
            row_ids,
            result.remediation_required,
            remediation_id,
            result.remediation_output,
        )
        return True


def create_worker() -> PostgresAnomalyWorker:
    manager = AgentManager(
        model=SETTINGS.client.params.model,
        base_url=SETTINGS.client.params.url,
        max_orchestration_rounds=SETTINGS.manager.max_orchestration_rounds,
        memory_path=SETTINGS.manager.memory_path,
        memory_max_prompt_chars=SETTINGS.manager.memory_max_prompt_chars,
    )
    return PostgresAnomalyWorker(
        store=get_postgres_store(),
        manager=manager,
        poll_interval_seconds=SETTINGS.postgres.poll_interval_seconds,
    )


if __name__ == "__main__":
    create_worker().run_forever()
