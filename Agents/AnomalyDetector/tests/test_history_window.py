import pytest
from pydantic import ValidationError

from adaptation import DetectorProfileRegistry
from config import MetricsCollectorSettings
from detector.logic.z_score import ZScoreLogic
from schema.storage import Metadata, MetricSeries


def test_thirty_minute_window_supports_default_three_point_detection():
    settings = MetricsCollectorSettings(base_url='http://prometheus.invalid', timeout=10)
    assert settings.history_minutes == 30
    assert settings.query_step_seconds == 30
    count = settings.history_minutes * 60 // settings.query_step_seconds + 1
    profile = DetectorProfileRegistry().resolve(
        'z_score', 'deployments', 'catalogue', 'deployment_cpu_usage',
    )
    assert profile.parameters['lookback'] == 60
    values = [10.0 + i % 2 for i in range(count - 3)] + [100.0] * 3
    series = MetricSeries(
        metadata=Metadata(name='catalogue', resource='deployments', metric='deployment_cpu_usage'),
        timestamps=[float(i * settings.query_step_seconds) for i in range(count)],
        values=values,
    )
    assert ZScoreLogic(**profile.parameters).predict(series).is_anomaly


def test_history_window_rejects_insufficient_samples_for_default_minimum():
    with pytest.raises(ValidationError, match='at least 33 samples'):
        MetricsCollectorSettings(base_url='http://prometheus.invalid', timeout=10,
                                 history_minutes=15, query_step_seconds=30)
