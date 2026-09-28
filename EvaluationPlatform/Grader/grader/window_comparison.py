"""Descriptive baseline versus sliding scheduled-chaos windows, using archives only."""
from __future__ import annotations

from .time_scope import chaos_intervals

import csv
import math
from bisect import bisect_left, bisect_right

from .archive_metrics import client_history, counter_window, metric_series, timestamp, windows
from .research import epoch, read


METRICS = {
    'response_time_p95_seconds': ('Service P95 (time average)', 'seconds'),
    'http_5xx_rate': ('HTTP 5xx rate (time average)', 'requests/s'),
}


def error_rate_series(root):
    """User-selected imputation: absent 5xx samples become zero at traffic timestamps.

    Only successful archived result matrices qualify. Explicit nonfinite samples,
    failed/missing query files, and gaps in traffic remain unavailable.
    """
    series = metric_series(root, 'http_5xx_rate')
    raw = read(root / 'metrics/http_5xx_rate.json', {})
    if raw.get('status', 'success') != 'success' or not isinstance(raw.get('data', {}).get('result'), list):
        return series, {}
    traffic = metric_series(root, 'traffic_rps')
    recorded = {}
    for row in raw['data']['result']:
        labels = row.get('metric', {})
        key = (labels.get('destination_workload_namespace'), labels.get('destination_workload'))
        recorded[key] = {float(t) for t, _ in row.get('values', [])}
    imputed = {}
    for key, samples in traffic.items():
        absent = {t for t, _ in samples} - recorded.get(key, set())
        imputed[key] = absent
        series[key] = sorted(series.get(key, []) + [(t, 0.0) for t in absent])
    return series, imputed


def validate_window(minutes):
    if not math.isfinite(minutes) or minutes <= 0:
        raise ValueError('comparison window minutes must be finite and positive')


def time_average(samples, start, end, step):
    """Right-endpoint integration; no sample represents more than one scrape step."""
    selected = [(t, v) for t, v in samples if start < t <= end]
    area = covered = 0.0
    previous = start
    for t, v in selected:
        span = min(step, t - previous)
        area += span * v
        covered += span
        previous = t
    coverage = covered / (end - start)
    return {'value': area / covered if covered and len(selected) >= 2 and coverage >= .9 else None,
            'coverage': coverage, 'samples': len(selected)}


def _client_means(root, rows):
    path = next((root / 'loadgenerator').glob('*_stats_history.csv'))
    by_line = {}
    with path.open(newline='') as handle:
        for line, raw in enumerate(csv.DictReader(handle), 2):
            try:
                value = float(raw['Total Average Response Time'])
                if math.isfinite(value) and value >= 0:
                    by_line[line] = value / 1000
            except (ValueError, KeyError, TypeError):
                pass
    return {r['t']: by_line.get(r['line']) for r in rows}


def compare_windows(root, window_minutes=5.0):
    validate_window(window_minutes)
    duration = window_minutes * 60
    result = {'schema_version': 1, 'status': 'not_evaluable', 'window_seconds': duration,
              'minimum_coverage': .9, 'baseline': None, 'chaos_intervals': [], 'rows': [],
              'limitations': [
                  'Best is selected independently per metric and workload; ties select the earliest window. Lower is better for these metrics; low traffic can also lower error rates.',
                  'P95 values are time averages of archived per-service rolling P95 estimates, not pooled request percentiles. HTTP 5xx rate is requests/s, not a failure percentage.',
                  'Client mean is estimated from differences of cumulative count times cumulative mean. CSV rounding affects it; it assumes every counted request has a response time (Locust CSV omits the missing-response-time count).',
                  'Missing HTTP 5xx samples are imputed as zero only at recorded traffic timestamps; imputed counts are disclosed. This is an analysis assumption, not a measured zero.',
                  'Chaos boundaries describe schedule application until cleanup, not verified fault activity. Prometheus rolling queries can include data preceding a boundary.',
              ]}
    try:
        metadata = read(root / 'metadata.json', {})
        begin, baseline_end, _, deadline, metrics, faults = windows(root, metadata)
        if not any(p.get('name') == 'baseline' and p.get('status') == 'completed' for p in metadata.get('phases', [])):
            raise ValueError('completed baseline is not recorded')
        step = float(metrics.get('step_seconds', 15))
        if not math.isfinite(step) or step <= 0:
            raise ValueError('invalid metrics scrape step')
        result['step_seconds'] = step
        result['baseline'] = {'start': timestamp(begin), 'end': timestamp(baseline_end)}
        candidates = []
        for start, recorded_end in chaos_intervals(metadata):
            end = min(recorded_end, deadline)
            if not baseline_end <= start < end:
                raise ValueError('invalid chaos interval')
            result['chaos_intervals'].append({'start': timestamp(start), 'end': timestamp(end)})
            for i in range(max(0, math.floor((end - start - duration) / step) + 1)):
                candidates.append((start + i * step, start + i * step + duration))
        candidates = sorted(set(candidates))
        result['candidate_windows'] = len(candidates)

        def add(metric, label, unit, namespace, workload, measure):
            baseline = measure(begin, baseline_end)
            measurements = []
            for start, end in candidates:
                item = measure(start, end)
                if item['value'] is not None:
                    measurements.append({**item, 'start': timestamp(start), 'end': timestamp(end)})
            row = {'metric': metric, 'label': label, 'unit': unit, 'namespace': namespace,
                   'workload': workload, 'baseline': baseline, 'eligible_windows': len(measurements),
                   'best': None}
            if baseline['value'] is not None and measurements:
                chosen = dict(min(measurements, key=lambda x: x['value']))
                chosen['absolute_change'] = chosen['value'] - baseline['value']
                chosen['relative_change'] = chosen['absolute_change'] / baseline['value'] if baseline['value'] else None
                row['best'] = chosen
            result['rows'].append(row)

        for metric, (label, unit) in METRICS.items():
            try:
                series, imputed = error_rate_series(root) if metric == 'http_5xx_rate' else (metric_series(root, metric), {})
                if not series:
                    add(metric, label, unit, None, 'unavailable', lambda a, b: {'value': None, 'coverage': 0})
                for (namespace, workload), samples in sorted(series.items()):
                    times = [t for t, _ in samples]
                    def measure(a, b):
                        subset = samples[bisect_right(times, a):bisect_right(times, b)]
                        measured = time_average(subset, a, b, step)
                        measured['imputed_samples'] = sum(a < t <= b for t in imputed.get((namespace, workload), set()))
                        return measured
                    add(metric, label, unit, namespace, workload, measure)
            except (ValueError, TypeError, KeyError, OSError, AttributeError) as exc:
                result['limitations'].append(f'{metric} unavailable: {type(exc).__name__}.')
                add(metric, label, unit, None, 'unavailable', lambda a, b: {'value': None, 'coverage': 0})
        try:
            rows, source = client_history(root)
            means = _client_means(root, rows)
            times = [r['t'] for r in rows]
            def client_mean(a, b):
                selected = rows[bisect_left(times, a):bisect_right(times, b)]
                counts = counter_window(selected, a, b)
                value = None
                if counts['coverage'] >= .9 and (counts['attempted'] or 0) > 0:
                    first, last = selected[0], selected[-1]
                    pairs = list(zip(selected, selected[1:]))
                    if all(means[r['t']] is not None for r in selected):
                        # Cumulative response-time resets invalidate the window too.
                        totals = {r['t']: r['attempted'] * means[r['t']] for r in selected}
                        if all(totals[y['t']] >= totals[x['t']] for x, y in pairs):
                            value = (totals[last['t']] - totals[first['t']]) / counts['attempted']
                return {'value': value, 'coverage': counts['coverage'], 'source_lines': counts['source_lines'],
                        'measured_seconds': counts['measured_seconds']}
            add('client_mean_response_seconds_estimate', 'Client mean response time (estimate)', 'seconds', None, 'client', client_mean)
            result['client_source'] = source
        except (ValueError, TypeError, KeyError, OSError, StopIteration) as exc:
            result['limitations'].append(f'Client mean unavailable: {type(exc).__name__}.')
            add('client_mean_response_seconds_estimate', 'Client mean response time (estimate)', 'seconds', None, 'client', lambda a, b: {'value': None, 'coverage': 0})
        usable = sum(r['best'] is not None for r in result['rows'])
        result['status'] = 'evaluable' if usable == len(result['rows']) else 'partially_evaluable' if usable else 'not_evaluable'
        if not candidates:
            result['reason'] = 'No complete chaos window fits the recorded intervals.'
    except (ValueError, TypeError, KeyError, OSError, AttributeError) as exc:
        result['reason'] = str(exc)
    return result


def markdown(comparison):
    def fmt(value):
        return 'unknown' if value is None else f'{value:.6g}'
    lines = ['## Baseline versus sliding chaos windows', '',
             f"Window: {comparison['window_seconds'] / 60:g} minutes; status: {comparison['status']}.", '']
    if comparison.get('baseline'):
        lines += [f"Full baseline: {comparison['baseline']['start']} to {comparison['baseline']['end']}. Windows advance by {comparison['step_seconds']:g} seconds.", '']
    if comparison.get('reason'):
        lines += [comparison['reason'], '']
    lines += ['| Metric / workload | Unit | Baseline | Window | Value | Change | Change % | UTC start → end | Coverage |',
              '| --- | --- | ---: | --- | ---: | ---: | ---: | --- | ---: |']
    for row in comparison['rows']:
        item = row.get('best') or {}
        change = item.get('relative_change')
        identity = '/'.join(x for x in [row['namespace'], row['workload']] if x)
        cells = [f"{row['label']} / {identity}", row['unit'], fmt(row['baseline']['value']), 'best',
                 fmt(item.get('value')), fmt(item.get('absolute_change')), fmt(change * 100 if change is not None else None),
                 f"{item.get('start', 'unknown')} → {item.get('end', 'unknown')}", fmt(item.get('coverage'))]
        lines.append('| ' + ' | '.join(str(c).replace('|', '\\|') for c in cells) + ' |')
    limitations = [s.replace('Best/worst are independent per metric and workload',
                             'Best is selected independently per metric and workload')
                   for s in comparison['limitations']]
    return '\n'.join(lines + ['', *['- ' + s for s in limitations], ''])


def write_comparisons(output, grades):
    rows = []
    for grade in grades:
        comparison = grade['window_comparison']
        path = output / 'runs' / grade['run'] / 'report.md'
        with path.open('a') as handle:
            handle.write('\n' + markdown(comparison))
        for row in comparison['rows']:
            item = row.get('best') or {}
            rows.append({'run': grade['run'], 'metric': row['metric'], 'namespace': row['namespace'],
                         'workload': row['workload'], 'unit': row['unit'], 'window_seconds': comparison['window_seconds'],
                         'baseline_start': comparison['baseline']['start'], 'baseline_end': comparison['baseline']['end'],
                         'baseline': row['baseline']['value'], 'baseline_coverage': row['baseline']['coverage'],
                         'missing_value_policy': 'zero_at_recorded_traffic_timestamps' if row['metric'] == 'http_5xx_rate' else 'no_imputation',
                         'baseline_imputed_samples': row['baseline'].get('imputed_samples', 0),
                         'window_imputed_samples': item.get('imputed_samples', 0),
                         'selection': 'best', 'eligible_windows': row['eligible_windows'],
                         **{k: item.get(k) for k in ('start', 'end', 'value', 'absolute_change', 'relative_change', 'coverage')}})
    csv_output = output / 'csvs'
    csv_output.mkdir(parents=True, exist_ok=True)
    fields = ['run', 'metric', 'namespace', 'workload', 'unit', 'window_seconds',
              'baseline_start', 'baseline_end', 'baseline', 'baseline_coverage',
              'selection', 'eligible_windows', 'start', 'end', 'value',
              'absolute_change', 'relative_change', 'coverage', 'missing_value_policy',
              'baseline_imputed_samples', 'window_imputed_samples']
    with (csv_output / 'window_comparison.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def paired_frontend_window(root, comparison, workload='front-end', namespace=None, max_5xx_rate=.5, baseline_ignore_minutes=5.0):
    """Select minimum time-mean P95 subject to a paired mean 5xx-rate ceiling."""
    if not math.isfinite(max_5xx_rate) or max_5xx_rate < 0:
        raise ValueError('table maximum 5xx rate must be finite and nonnegative')
    if not math.isfinite(baseline_ignore_minutes) or baseline_ignore_minutes < 0:
        raise ValueError('baseline ignore minutes must be finite and nonnegative')
    duration = comparison['window_seconds']
    result = {
        'schema_version': 1, 'status': 'not_evaluable', 'window_seconds': duration,
        'minimum_coverage': .9, 'max_5xx_rate': max_5xx_rate,
        'http_5xx_missing_value_policy': 'zero_at_recorded_traffic_timestamps',
        'selection': 'lowest_p95_with_5xx_at_or_below_threshold_then_earliest',
        'namespace': namespace, 'workload': workload, 'baseline': None, 'best': None,
        'baseline_ignore_minutes': baseline_ignore_minutes,
        'candidate_windows': 0, 'covered_windows': 0, 'eligible_windows': 0,
        'description': f'{namespace + "/" if namespace else ""}{workload}; {duration / 60:g}-minute windows; '
                       f'mean 5xx <= {max_5xx_rate:g} requests/s; lowest mean P95, earliest tie',
    }
    try:
        if not comparison.get('baseline') or not comparison.get('step_seconds'):
            raise ValueError(comparison.get('reason') or 'recorded baseline is unavailable')
        if comparison.get('reason') and comparison['reason'] != 'No complete chaos window fits the recorded intervals.':
            raise ValueError(comparison['reason'])
        begin = epoch(comparison['baseline']['start']) + baseline_ignore_minutes * 60
        baseline_end = epoch(comparison['baseline']['end'])
        step = comparison['step_seconds']
        series = {}
        errors = []
        imputed = {}
        for metric in METRICS:
            try:
                if metric == 'http_5xx_rate':
                    series[metric], imputed = error_rate_series(root)
                else:
                    series[metric] = metric_series(root, metric)
            except (ValueError, TypeError, KeyError, OSError, AttributeError) as exc:
                series[metric] = {}
                errors.append(f'{metric} unavailable: {type(exc).__name__}')
        identities = {key for data in series.values() for key in data
                      if key[1] == workload and (namespace is None or key[0] == namespace)}
        if len(identities) != 1:
            raise ValueError('front-end workload is missing or ambiguous; specify table namespace/workload')
        key = next(iter(identities))
        result['namespace'] = key[0]
        result['description'] = f'{key[0]}/{key[1]}; {duration / 60:g}-minute windows; mean 5xx <= {max_5xx_rate:g} requests/s; lowest mean P95, earliest tie; baseline ignores first {baseline_ignore_minutes:g} minutes'
        samples = {name: data.get(key, []) for name, data in series.items()}
        times = {name: [t for t, _ in values] for name, values in samples.items()}

        def measure(start, end):
            measurements = {}
            for name in METRICS:
                subset = samples[name][bisect_right(times[name], start):bisect_right(times[name], end)]
                measurements[name] = time_average(subset, start, end, step)
            p95, errors = (measurements[name] for name in METRICS)
            return {'start': timestamp(start), 'end': timestamp(end),
                    'p95_seconds': p95['value'], 'http_5xx_rps': errors['value'],
                    'p95_coverage': p95['coverage'], 'http_5xx_coverage': errors['coverage'],
                    'p95_samples': p95['samples'], 'http_5xx_samples': errors['samples'],
                    'http_5xx_imputed_samples': sum(start < t <= end for t in imputed.get(key, set()))}

        if begin < baseline_end:
            result['baseline'] = measure(begin, baseline_end)
            if any(result['baseline'][name] is None for name in ('p95_seconds', 'http_5xx_rps')):
                result['baseline_reason'] = '; '.join(errors) or 'insufficient baseline P95 or 5xx coverage'
        else:
            result['baseline_reason'] = 'baseline exclusion leaves no baseline interval'
        candidates = set()
        for interval in comparison['chaos_intervals']:
            start, end = epoch(interval['start']), epoch(interval['end'])
            for i in range(max(0, math.floor((end - start - duration) / step) + 1)):
                candidates.add((start + i * step, start + i * step + duration))
        result['candidate_windows'] = len(candidates)
        for start, end in sorted(candidates):
            item = measure(start, end)
            if item['p95_seconds'] is None or item['http_5xx_rps'] is None:
                continue
            result['covered_windows'] += 1
            if item['http_5xx_rps'] > max_5xx_rate:
                continue
            result['eligible_windows'] += 1
            if result['best'] is None or item['p95_seconds'] < result['best']['p95_seconds']:
                result['best'] = item
        if result['best'] is not None:
            result['status'] = 'partially_evaluable' if result.get('baseline_reason') else 'evaluable'
        elif not candidates:
            result['reason'] = 'No complete chaos window fits the recorded intervals.'
        elif not result['covered_windows']:
            result['reason'] = 'No window has sufficient coverage for both P95 and 5xx.'
        else:
            result['reason'] = 'No covered window meets the mean 5xx-rate threshold.'
    except (ValueError, TypeError, KeyError, OSError, AttributeError) as exc:
        result['reason'] = str(exc)
    return result
