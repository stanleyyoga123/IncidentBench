import logging
import socket
import threading

from schema import LearningJobRequest


LOGGER = logging.getLogger("LearningWorker")


class LearningWorker:
    def __init__(self, store, engine, settings):
        self.store = store
        self.engine = engine
        self.settings = settings
        self.owner = f"{socket.gethostname()}:{id(self)}"
        self.stop_event = threading.Event()
        self.thread = None

    def start(self) -> None:
        self.thread = threading.Thread(target=self.run_forever, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=10)

    def run_forever(self) -> None:
        while not self.stop_event.is_set():
            try:
                self.run_once()
            except Exception:
                LOGGER.exception("Learning worker iteration failed")
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
            target=self._heartbeat, args=(job.id, heartbeat_stop), daemon=True
        )
        heartbeat.start()
        try:
            request = LearningJobRequest.model_validate(job.request)
            result, raw = self.engine.run(job.id, request)
            self.store.succeed(job.id, result, raw)
        except Exception as exc:
            LOGGER.exception("Learning job %s failed", job.id)
            self.store.fail(job.id, exc, self.settings.worker.max_attempts)
        finally:
            heartbeat_stop.set()
            heartbeat.join(timeout=5)
        return True

    def _heartbeat(self, job_id, stop_event) -> None:
        interval = max(10, self.settings.worker.lease_seconds / 3)
        while not stop_event.wait(interval):
            if not self.store.renew(job_id, self.owner, self.settings.worker.lease_seconds):
                LOGGER.error("Lost learning execution lease for %s", job_id)
                return
