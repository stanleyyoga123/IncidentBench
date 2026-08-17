from typing import Any

from adapter.prometheus_granularity import PrometheusGranularityTransformer
from adapter.prometheus_metric import PrometheusMetricAdapter


MetricDict = dict[str, str | int | float]


class PrometheusAdapter:
    def __init__(self):
        self._metric_adapter = PrometheusMetricAdapter()
        self._granularity_transformer = PrometheusGranularityTransformer()

    @classmethod
    def adapt(cls, payload: dict[str, Any]) -> dict[str, list[MetricDict]]:
        return PrometheusMetricAdapter().adapt(payload)

    @classmethod
    def transform(
        cls,
        payload: dict[str, Any],
    ) -> dict[str, dict[str, dict[str, list[MetricDict]]]]:
        adapted = cls.adapt(payload)
        return PrometheusGranularityTransformer().transform(adapted)
