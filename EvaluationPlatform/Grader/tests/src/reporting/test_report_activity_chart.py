"""Protect faithful plotting of missing counts, measured zeros, and sample SD."""
import matplotlib.pyplot as plt
import pandas as pd

from reporting import report
from reporting.report_activity_chart import activity_chart


def test_activity_chart_distinguishes_unknown_zero_and_single_run_and_preserves_sd():
    summary = pd.DataFrame([{
        'application': 'sock-shop', 'resource_type': 'node', 'fault_type': 'memory',
        'runs': 2, 'anomaly_mean': 1., 'anomaly_std': 2., 'anomaly_n': 2,
        'rca_mean': 0., 'rca_std': float('nan'), 'rca_n': 1,
        'remediation_mean': float('nan'), 'remediation_std': float('nan'),
        'remediation_n': 0,
    }])

    figure = activity_chart(summary)
    try:
        anomaly, rca, remediation = figure.axes
        anomaly_points, _, whiskers = anomaly.containers[0].lines
        assert list(anomaly_points.get_xdata()) == [1.]
        assert whiskers[0].get_segments()[0][:, 0].tolist() == [-1., 3.]
        assert anomaly.get_xlim()[0] < -1
        rca_points, _, rca_whiskers = rca.containers[0].lines
        assert list(rca_points.get_xdata()) == [0.]
        assert rca_points.get_markerfacecolor() == 'white'
        assert not rca_whiskers
        assert remediation.containers == []
        assert [text.get_text() for text in remediation.texts] == ['Unknown (n=0)']
        assert 'Node · Memory' in [label.get_text() for label in anomaly.get_yticklabels()]
    finally:
        plt.close(figure)


def test_activity_chart_keeps_application_style_and_row_order_across_subsets():
    rows = []
    for app in ('sock-shop', 'online-boutique'):
        for resource, fault in (('pod', 'cpu-headroom'), ('node', 'memory')):
            row = {'application': app, 'resource_type': resource, 'fault_type': fault, 'runs': 2}
            for kind in ('anomaly', 'rca', 'remediation'):
                row.update({f'{kind}_mean': 2., f'{kind}_std': 1., f'{kind}_n': 2})
            rows.append(row)
    summary = pd.DataFrame(rows)
    figure = activity_chart(summary)
    subset = activity_chart(summary.loc[summary.application == 'sock-shop'])
    try:
        full_points = figure.axes[0].containers[2].lines[0]
        subset_points = subset.axes[0].containers[0].lines[0]
        assert full_points.get_color() == subset_points.get_color()
        assert full_points.get_marker() == subset_points.get_marker()
        assert [label.get_text() for label in figure.axes[0].get_yticklabels()] == [
            'Node · Memory', 'Pod · CPU headroom']
    finally:
        plt.close(figure)
        plt.close(subset)


def test_activity_chart_empty_cohort_shows_no_data():
    figure = activity_chart(pd.DataFrame())
    try:
        assert figure.axes[0].texts[0].get_text() == 'No selected completed runs available'
        assert not figure.axes[0].containers
    finally:
        plt.close(figure)


def test_report_embeds_activity_chart_with_custom_output_stem(tmp_path):
    fixture = report.GRADER_ROOT / 'examples/report-demo'
    output = tmp_path / 'comparison.md'

    assert report.main(['--results-dir', str(fixture / 'results'),
                        '--grades-dir', str(fixture / 'grades'),
                        '--apps', 'sock-shop', 'online-boutique',
                        '--output', str(output)]) == 0

    text = output.read_text()
    assert '![Workflow activity comparison](comparison-activity.png)' in text
    assert '[Download vector chart](comparison-activity.svg)' in text
    assert (tmp_path / 'comparison-activity.png').stat().st_size > 0
    assert (tmp_path / 'comparison-activity.svg').stat().st_size > 0
