import logging
import socket
import threading

from engine import RCAEngine
from schema import RCAJobRequest
from store import RCAJobStore


LOGGER = logging.getLogger("RCAWorker")


class RCAWorker:
    def __init__(self, store: RCAJobStore, engine: RCAEngine, settings):
        self.store = store
        self.engine = engine
        self.settings = settings
        self.owner = f"{socket.gethostname()}:{id(self)}"
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None

    def start(self):
        self.thread = threading.Thread(target=self.run_forever, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=10)

    def run_forever(self):
        while not self.stop_event.is_set():
            try:
                self.run_once()
            except Exception:
                LOGGER.exception("RCA worker iteration failed")
            self.stop_event.wait(self.settings.worker.poll_interval_seconds)

    def run_once(self) -> bool:
        job = self.store.claim(
            self.owner,
            self.settings.worker.lease_seconds,
            self.settings.worker.max_attempts,
        )
        if job is None:
            return False
        heartbeat_stop = threading.Event()
        heartbeat = threading.Thread(
            target=self._heartbeat,
            args=(job.id, heartbeat_stop),
            daemon=True,
        )
        heartbeat.start()
        try:
            request = RCAJobRequest.model_validate(job.request)
            result, raw = self.engine.run(job.id, request)
            self.store.succeed(job.id, result, raw)
        except Exception as exc:
            LOGGER.exception("RCA job %s failed", job.id)
            self.store.fail(job, exc, self.settings.worker.max_attempts)
        finally:
            heartbeat_stop.set()
            heartbeat.join(timeout=5)
        return True

    def _heartbeat(self, job_id, stop_event):
        interval = max(10, self.settings.worker.lease_seconds / 3)
        while not stop_event.wait(interval):
            if not self.store.renew(job_id, self.owner, self.settings.worker.lease_seconds):
                LOGGER.error("Lost RCA execution lease for %s", job_id)
                return
