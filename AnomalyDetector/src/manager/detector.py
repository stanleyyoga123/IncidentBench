import asyncio
import threading
import time
from typing import Any

import httpx

from adaptation import DetectorProfileRegistry
from collector.metrics.prometheus import (
    PrometheusCollector,
    PrometheusConfigurationError,
)
from collector.metrics.provider import PrometheusSeriesProvider
from common.logger import get_logger
from config import SETTINGS
from controller.orchestrator import AgentOrchestratorSink
from detector.monitor.threshold import ThresholdMonitor
from detector.monitor.z_score import ZScoreMonitor

LOGGER = get_logger("DetectorManager")


class DetectorManager:
    def __init__(
        self,
        series_provider: PrometheusSeriesProvider | None = None,
        sink: AgentOrchestratorSink | None = None,
        monitors: list[Any] | None = None,
        profile_registry: DetectorProfileRegistry | None = None,
    ) -> None:
        metrics = SETTINGS.collector.metrics
        self._series_provider = series_provider or PrometheusSeriesProvider(
            PrometheusCollector(
                base_url=metrics.base_url,
                timeout_seconds=metrics.timeout,
                max_concurrency=metrics.max_concurrency,
            ),
            namespaces=SETTINGS.collector.metadata.namespaces,
            excluded_nodes=SETTINGS.collector.metadata.excluded_nodes,
            history_minutes=metrics.history_minutes,
            query_step_seconds=metrics.query_step_seconds,
        )
        self.profile_registry = profile_registry or DetectorProfileRegistry()
        self._monitors = (
            monitors
            if monitors is not None
            else [
                ZScoreMonitor(
                    cooldown_duration=SETTINGS.detector.cooldown_seconds,
                    profile_registry=self.profile_registry,
                ),
                ThresholdMonitor(
                    cooldown_duration=SETTINGS.detector.cooldown_seconds,
                    profile_registry=self.profile_registry,
                ),
            ]
        )
        orchestrator = SETTINGS.orchestrator
        self._sink = sink or AgentOrchestratorSink(
            orchestrator.base_url,
            orchestrator.ingestion_token,
            orchestrator.timeout_seconds,
            orchestrator.max_attempts,
        )

    async def close(self) -> None:
        await self._series_provider.close()
        await self._sink.close()

    async def detect(self) -> dict[str, Any]:
        started_at = time.monotonic()
        series = await self._series_provider.fetch_recent()
        anomalies = []
        acknowledgements: list[tuple[Any, set[str]]] = []
        for monitor in self._monitors:
            detections = monitor.detect(series)
            detected = [item for item in detections if item.is_anomaly]
            anomalies.extend(detected)
            acknowledgements.append(
                (monitor, {item.metadata.key for item in detected})
            )

        if anomalies:
            await self._sink.ingest(anomalies)
            for monitor, keys in acknowledgements:
                monitor.acknowledge(keys)
        sample_count = sum(len(item.values) for item in series)
        LOGGER.info(
            "Detection cycle completed series=%s samples=%s anomalies=%s duration_seconds=%.3f",
            len(series),
            sample_count,
            len(anomalies),
            time.monotonic() - started_at,
        )
        return {
            "series": len(series),
            "samples": sample_count,
            "anomalies": len(anomalies),
        }

    async def detect_forever(self, stop_event: threading.Event) -> None:
        LOGGER.info(
            "Detector loop started interval_seconds=%s",
            SETTINGS.detector.interval_seconds,
        )
        try:
            while not stop_event.is_set():
                try:
                    await self.detect()
                except PrometheusConfigurationError:
                    LOGGER.exception("Prometheus recording-rule configuration is invalid")
                    raise
                except (httpx.HTTPError, ValueError, KeyError, TypeError):
                    LOGGER.exception(
                        "Skipping detection cycle because Prometheus data is unavailable"
                    )

                await asyncio.to_thread(
                    stop_event.wait,
                    SETTINGS.detector.interval_seconds,
                )
        finally:
            await self.close()
            LOGGER.info("Detector loop stopped")
