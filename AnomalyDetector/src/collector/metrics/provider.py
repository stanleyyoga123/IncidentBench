from __future__ import annotations

import math
import re
import time
from collections.abc import Callable
from typing import Any

from adapter.prometheus import PrometheusAdapter
from collector.metrics.prometheus import PrometheusCollector
from collector.metrics.query import QueryBuilder
from schema.storage import Metadata, MetricSeries


class PrometheusSeriesProvider:
    """Fetches one stateless, aligned historical snapshot for a detector run."""

    def __init__(
        self,
        collector: PrometheusCollector,
        *,
        namespaces: list[str],
        excluded_nodes: list[str] | None = None,
        history_minutes: int = 65,
        query_step_seconds: int = 30,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not namespaces:
            raise ValueError("at least one namespace must be configured")
        self._collector = collector
        self._namespace_regex = self._regex_union(namespaces)
        self._excluded_node_regex = self._regex_union(excluded_nodes or []) or None
        self._history_seconds = history_minutes * 60
        self._step_seconds = query_step_seconds
        self._clock = clock
        self._rules_verified = False

    async def close(self) -> None:
        await self._collector.close()

    async def fetch_recent(self) -> list[MetricSeries]:
        if not self._rules_verified:
            await self._collector.verify_recording_rules(
                QueryBuilder.required_record_names()
            )
            self._rules_verified = True

        end = math.floor(self._clock() / self._step_seconds) * self._step_seconds
        start = end - self._history_seconds
        payload = await self._collector.collect_range(
            start=start,
            end=end,
            step=self._step_seconds,
            namespace_regex=self._namespace_regex,
            excluded_node_regex=self._excluded_node_regex,
        )
        return self._to_series(PrometheusAdapter.transform(payload))

    @staticmethod
    def _regex_union(values: list[str]) -> str:
        return "|".join(re.escape(value) for value in sorted(set(values)))

    @staticmethod
    def _to_series(
        payload: dict[str, dict[str, dict[str, list[dict[str, Any]]]]],
    ) -> list[MetricSeries]:
        result = []
        for resource, named_metrics in payload.items():
            for name, metrics in named_metrics.items():
                for metric, rows in metrics.items():
                    by_timestamp = {}
                    for row in rows:
                        timestamp = float(row["timestamp"])
                        value = float(row["value"])
                        if math.isfinite(timestamp) and math.isfinite(value):
                            by_timestamp[timestamp] = value
                    if not by_timestamp:
                        continue

                    ordered = sorted(by_timestamp.items())
                    result.append(
                        MetricSeries(
                            metadata=Metadata(
                                name=name,
                                resource=resource,
                                metric=metric,
                            ),
                            timestamps=[timestamp for timestamp, _ in ordered],
                            values=[value for _, value in ordered],
                        )
                    )
        return result
