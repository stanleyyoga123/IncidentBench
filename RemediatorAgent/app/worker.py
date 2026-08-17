import logging
import socket
import threading

from schema import RemediationJobRequest


LOGGER = logging.getLogger("RemediatorWorker")


class RemediatorWorker:
    def __init__(self, store, engine, settings):
        self.store = store
        self.engine = engine
        self.settings = settings
        self.owner = f"{socket.gethostname()}:{id(self)}"
        self.stop_event = threading.Event()
        self.thread = None

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
                LOGGER.exception("Remediator iteration failed")
            self.stop_event.wait(self.settings.worker.poll_interval_seconds)

    def run_once(self):
        job = self.store.claim(self.owner, self.settings.worker.lease_seconds)
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
            request = RemediationJobRequest.model_validate(job.request)
            result, raw = self.engine.run(job.id, request)
            self.store.succeed(job.id, result, raw)
        except Exception as exc:
            LOGGER.exception("Remediation job %s requires review", job.id)
            self.store.needs_review(job.id, exc)
        finally:
            heartbeat_stop.set()
            heartbeat.join(timeout=5)
        return True

    def _heartbeat(self, job_id, stop_event):
        interval = max(10, self.settings.worker.lease_seconds / 3)
        while not stop_event.wait(interval):
            if not self.store.renew(job_id, self.owner, self.settings.worker.lease_seconds):
                LOGGER.error("Lost remediation execution lease for %s", job_id)
                return
