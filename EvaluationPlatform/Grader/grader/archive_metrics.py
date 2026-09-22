"""Offline measurements from the original Runner's Locust CSV and Prometheus files.

No reconstructed histograms, fault observations, or action timestamps. The service
recovery proxy is deliberately distinct from verified client sustained recovery.
"""
from __future__ import annotations

import csv
import math
from datetime import datetime, timezone
from statistics import median

from .research import read, epoch
from .time_scope import chaos_intervals, contains, VERSION


def timestamp(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


def client_history(root):
    paths = sorted((root / 'loadgenerator').glob('*_stats_history.csv'))
    if len(paths) != 1:
        raise ValueError('requires exactly one Locust stats history CSV')
    rows = []
    with paths[0].open(newline='') as handle:
        for line, raw in enumerate(csv.DictReader(handle), 2):
            if raw.get('Name') != 'Aggregated':
                continue
            try:
                t = float(raw['Timestamp'])
                attempted = int(raw['Total Request Count'])
                failed = int(raw['Total Failure Count'])
                if not math.isfinite(t) or not 0 <= failed <= attempted:
                    raise ValueError('invalid counters')
            except (ValueError, KeyError, TypeError):
                # A bad sample creates a gap, never a zero-valued observation.
                continue
            rows.append({'t': t, 'attempted': attempted, 'failed': failed, 'line': line})
    if any(b['t'] <= a['t'] for a, b in zip(rows, rows[1:])):
        raise ValueError('duplicate or unordered aggregate client timestamps')
    return rows, str(paths[0].relative_to(root))


def counter_window(rows, start, end):
    selected = [r for r in rows if start <= r['t'] <= end]
    result = {'attempted': None, 'failed': None, 'failure_ratio': None,
              'successful_rps': None, 'measured_seconds': 0, 'coverage': 0,
              'source_lines': None, 'counter_reset': False}
    if len(selected) < 2:
        return result
    first, last = selected[0], selected[-1]
    if any(b[k] < a[k] for a, b in zip(selected, selected[1:]) for k in ('attempted', 'failed')):
        result['counter_reset'] = True
        return result
    n, failed = last['attempted'] - first['attempted'], last['failed'] - first['failed']
    if failed > n:
        result['counter_reset'] = True
        return result
    duration = last['t'] - first['t']
    covered = sum(b['t'] - a['t'] for a, b in zip(selected, selected[1:]) if b['t'] - a['t'] <= 5)
    return {**result, 'attempted': n, 'failed': failed,
            'failure_ratio': failed / n if n else None,
            'successful_rps': (n - failed) / duration,
            'measured_seconds': duration, 'coverage': covered / (end - start),
            'source_lines': [first['line'], last['line']],
            'measured_start': timestamp(first['t']), 'measured_end': timestamp(last['t'])}


def metric_series(root, name):
    result = {}
    for row in read(root / 'metrics' / (name + '.json'), {}).get('data', {}).get('result', []):
        labels = row.get('metric', {})
        key = (labels.get('destination_workload_namespace'), labels.get('destination_workload'))
        if not all(key):
            continue
        if key in result:
            raise ValueError('ambiguous workload series in ' + name)
        samples = []
        for t, v in row.get('values', []):
            t, v = float(t), float(v)
            if math.isfinite(t) and math.isfinite(v) and v >= 0:
                samples.append((t, v))
        if any(b[0] <= a[0] for a, b in zip(samples, samples[1:])):
            raise ValueError('unordered metric samples in ' + name)
        result[key] = samples
    return result


def metric_window(samples, start, end, step):
    """Each finite scrape supports at most one scrape interval, clipped to window."""
    points = [(t, v) for t, v in samples if start < t <= end]
    covered = sum(max(0, min(step, t - max(start, points[i-1][0] if i else start)))
                  for i, (t, _) in enumerate(points))
    return points, min(1, covered / (end - start))


def windows(root, metadata):
    metrics = metadata.get('metrics') or read(root / 'metrics/metrics.json', {})
    begin = epoch(metrics.get('start'))
    baseline_end = begin + float(metadata['baseline_seconds'])
    deadline = min(epoch(metrics.get('end')), chaos_intervals(metadata)[-1][1])
    steps = metadata.get('chaos_steps', [])
    faults = [s for s in steps if s.get('chaos') and not s.get('idle')]
    if not faults:
        raise ValueError('missing recorded chaos steps')
    onset = epoch(faults[0].get('active_started_at'))
    if not begin < baseline_end <= onset < deadline:
        raise ValueError('invalid archived baseline/chaos/observation timing')
    return begin, baseline_end, onset, deadline, metrics, faults


def evaluate_archive(root, p, metadata):
    result = {'status': 'not_evaluable', 'reason': None, 'measurement_basis': 'archive_service_recovery_proxy',
              'recovered': None, 'recovery_seconds': None, 'active_fault_recovery': None,
              'proxy_recovered': None, 'proxy_recovery_seconds': None, 'censored': None,
              'baseline': None, 'harm': None, 'intervals': [], 'time_scope': VERSION,
              'limitations': [
                  'Latency is assessed separately for each baseline-active service; no application-wide interval P95 is reconstructed.',
                  'Whole-run Locust CSV percentiles are excluded; interval percentiles cannot be reconstructed from cumulative percentiles.',
                  'Chaos active_started_at records schedule application, not observed fault activation. Active-fault recovery and causal benefit are unverified.',
                  'No independent safety assessment, action verification or matched agents-off experiment is required for this descriptive proxy.']}
    def unavailable(reason, status='not_evaluable'):
        result.update(status=status, reason=reason)
        return result
    try:
        rows, source = client_history(root)
        begin, base_end, onset, deadline, metrics, faults = windows(root, metadata)
        spans = [(a, min(b, deadline)) for a, b in chaos_intervals(metadata) if a < deadline]
        observation_seconds = sum(b-a for a,b in spans)
        # Whole-run cumulative summaries cannot establish chaos-only percentiles.
        result['client_summary'] = None
        result['limitations'].append('Whole-run client mean/P95 omitted: cumulative summaries include baseline and post-chaos data.')
        base_start = base_end - p['baseline_seconds']
        if base_start < begin:
            return unavailable('baseline shorter than evaluation window', 'invalid')
        if metadata.get('baseline_health', {}).get('passed') is False:
            return unavailable('archived baseline health check failed', 'invalid')
        phases = {r['name']: r.get('status') for r in metadata.get('phases', [])}
        if phases.get('baseline') != 'completed':
            return unavailable('completed baseline phase is not recorded')
        if 'baseline_health' not in metadata:
            result['limitations'].append('Application baseline health assessment was not archived; eligibility uses completed baseline and measured client failures.')
        base = counter_window(rows, base_start, base_end)
        baseline_bins = [counter_window(rows, t, t+p['interval_seconds']) for t in
                         (base_start+i*p['interval_seconds'] for i in range(p['baseline_seconds']//p['interval_seconds']))]
        result.update(baseline=base, timing={'baseline_start': timestamp(base_start), 'baseline_end': timestamp(base_end),
                      'scheduled_fault_start': timestamp(onset), 'observation_end': timestamp(deadline),
                      'source': 'metadata.json#metrics,baseline_seconds,chaos_steps'},
                      chaos_intervals=[{'start': timestamp(a), 'end': timestamp(b)} for a,b in spans],
                      observation_seconds=observation_seconds, sources=[source, 'metadata.json',
                          'metrics/response_time_p95_seconds.json', 'metrics/traffic_rps.json'])
        if base['coverage'] < p['minimum_coverage'] or any(b['coverage'] < p['minimum_coverage'] or (b['attempted'] or 0) < p['minimum_requests'] for b in baseline_bins):
            return unavailable('baseline client counters have insufficient coverage or requests')
        if base['failure_ratio'] > p['maximum_baseline_failure_ratio']:
            return unavailable('baseline client failure ratio exceeds policy', 'invalid')
        traffic = metric_series(root, 'traffic_rps')
        latency = metric_series(root, 'response_time_p95_seconds')
        step = float(metrics.get('step_seconds', 15))
        if not 0 < step <= p['interval_seconds'] / 2:
            return unavailable('at least two service samples per evaluation interval are required')
        targets = sorted(key for key, samples in traffic.items() if any(v > 0 for t,v in samples if base_start < t <= base_end))
        services = []
        for key in targets:
            lat, lc = metric_window(latency.get(key, []), base_start, base_end, step)
            rate, rc = metric_window(traffic[key], base_start, base_end, step)
            services.append({'namespace': key[0], 'workload': key[1],
                             'baseline_p95_time_median_seconds': median(v for t,v in lat) if lat else None,
                             'baseline_rps_time_median': median(v for t,v in rate) if rate else None,
                             'baseline_coverage': min(lc, rc)})
        result['services'] = services
        if not services or any(s['baseline_coverage'] < p['minimum_coverage'] or not s['baseline_rps_time_median'] for s in services):
            return unavailable('baseline-active service latency or traffic evidence is missing')
        result['limits'] = {'failure_ratio': base['failure_ratio'] + p['failure_ratio_allowance'],
                            'successful_rps': base['successful_rps'] * p['throughput_fraction'],
                            'service_latency_multiplier': p['latency_multiplier'],
                            'service_traffic_fraction': p['throughput_fraction']}
        parts = [counter_window(rows, a, b) for a, b in spans]
        harm = dict(parts[0])
        if len(parts) > 1:
            measured = sum(part['measured_seconds'] for part in parts)
            known = all(part['attempted'] is not None for part in parts)
            attempted = sum(part['attempted'] for part in parts) if known else None
            failed = sum(part['failed'] for part in parts) if known else None
            harm = {'attempted': attempted, 'failed': failed,
                    'failure_ratio': failed / attempted if attempted else None,
                    'successful_rps': (attempted-failed)/measured if known and measured else None,
                    'measured_seconds': measured, 'counter_reset': any(part['counter_reset'] for part in parts),
                    'coverage': sum(part['coverage']*(b-a) for part,(a,b) in zip(parts,spans))/observation_seconds,
                    'segments': parts}
        result['client_observed_totals'] = {**harm, 'source': source, 'time_scope': VERSION}
        result['harm'] = {**harm, 'coverage_adequate': harm['coverage'] >= p['minimum_coverage'],
                          'slow_requests_lower_bound': None, 'slow_requests_upper_bound': None, 'source': source}
        result['limitations'].append('Slow-request counts cannot be derived from archived percentiles; failed counts cover only the reported measured endpoints.')
        streak = 0
        degraded = False
        first_candidate = None
        valid_seconds = 0
        missing_services = set()
        aligned_start = begin + math.ceil((onset-begin) / p['interval_seconds']) * p['interval_seconds']
        for i in range(int((deadline-aligned_start) // p['interval_seconds'])):
            start = aligned_start + i*p['interval_seconds']; end = start+p['interval_seconds']
            if not contains(spans, start, end):
                streak = 0
                continue
            client = counter_window(rows, start, end)
            qualified = client['coverage'] >= p['minimum_coverage']
            client_ok = (client['attempted'] or 0) >= p['minimum_requests'] and client['failure_ratio'] is not None and client['failure_ratio'] <= result['limits']['failure_ratio'] and client['successful_rps'] >= result['limits']['successful_rps']
            checks = []
            for key, service in zip(targets, services):
                lat, lc = metric_window(latency.get(key, []), start, end, step)
                rate, rc = metric_window(traffic[key], start, end, step)
                covered = min(lc, rc) >= p['minimum_coverage'] and len(lat) >= 2 and len(rate) >= 2
                if not covered:
                    missing_services.add(key)
                qualified = qualified and covered
                ok = bool(covered and max(v for t,v in lat) <= service['baseline_p95_time_median_seconds'] * p['latency_multiplier'] and min(v for t,v in rate) >= service['baseline_rps_time_median'] * p['throughput_fraction'])
                checks.append({'workload': key[1], 'namespace': key[0], 'covered': covered, 'healthy': ok,
                               'maximum_p95_seconds': max((v for t,v in lat), default=None),
                               'minimum_rps': min((v for t,v in rate), default=None)})
            healthy = bool(qualified and client_ok and all(s['healthy'] for s in checks))
            if qualified:
                valid_seconds += p['interval_seconds']
                degraded = degraded or not healthy
            streak = streak+p['interval_seconds'] if healthy and degraded else 0
            if streak >= p['sustain_seconds'] and first_candidate is None:
                first_candidate = end-p['sustain_seconds']
            result['intervals'].append({'start': timestamp(start), 'end': timestamp(end), **client,
                                        'qualified': qualified, 'healthy': healthy, 'services': checks})
        result['coverage'] = valid_seconds/observation_seconds
        result['service_coverage'] = {'missing': [list(k) for k in sorted(missing_services)], 'source': 'metrics/*.json'}
        if result['coverage'] < p['minimum_coverage']:
            return unavailable('incident client/service telemetry coverage insufficient')
        if not degraded:
            return unavailable('no qualifying interval showed degradation; recovery is not demonstrated', 'no_observed_degradation')
        recovered = first_candidate is not None
        result.update(status='proxy_recovered' if recovered else 'proxy_unresolved',
                      reason='client reliability/throughput and each service returned to baseline tolerances' if recovered else 'no sustained return within the recorded observation window',
                      proxy_recovered=recovered, censored=not recovered)
        if recovered:
            result['proxy_recovery_seconds'] = first_candidate-onset
            result['proxy_recovery_at'] = timestamp(first_candidate)
            # Describe scheduled phase only, never claim active-fault verification.
            result['recovery_schedule_phase'] = 'unknown'
            try:
                if first_candidate >= max(epoch(f.get('cleanup_started_at')) for f in faults):
                    result['recovery_schedule_phase'] = 'after_schedule_cleanup'
                for fault in faults:
                    if epoch(fault.get('active_started_at')) <= first_candidate and first_candidate+p['sustain_seconds'] <= epoch(fault.get('cleanup_started_at')):
                        result['recovery_schedule_phase'] = 'during_scheduled_chaos'
                        break
            except (ValueError, TypeError):
                result['limitations'].append('Schedule cleanup timestamps are incomplete; recovery phase is unknown.')
        return result
    except (ValueError, KeyError, TypeError, OSError, AttributeError) as exc:
        return unavailable('archive evidence unavailable: ' + str(exc))


def client_summary(root):
    paths = sorted((root / 'loadgenerator').glob('*_stats.csv'))
    if len(paths) != 1:
        return None
    with paths[0].open(newline='') as handle:
        raw = next((r for r in csv.DictReader(handle) if r.get('Name') == 'Aggregated'), None)
    if raw is None:
        return None
    def number(key):
        try:
            value = float(raw[key])
            return value if math.isfinite(value) and value >= 0 else None
        except (ValueError, KeyError, TypeError):
            return None
    n, failed = number('Request Count'), number('Failure Count')
    return {'source': str(paths[0].relative_to(root)) + '#Aggregated', 'window': 'entire Locust run including baseline',
            'attempted': n, 'failed': failed, 'failure_ratio': failed/n if n and failed is not None else None,
            'p95_seconds': number('95%')/1000 if number('95%') is not None else None,
            'average_response_seconds': number('Average Response Time')/1000 if number('Average Response Time') is not None else None}


def error_ratios(root):
    """Exact label/time matches only; absent 5xx series remains unknown."""
    traffic = metric_series(root, 'traffic_rps')
    errors = metric_series(root, 'http_5xx_rate')
    spans = chaos_intervals(read(root / 'metadata.json', {}))
    result = []
    for key, series in traffic.items():
        rates = dict(series)
        ratios = [(t,v/rates[t]) for t,v in errors.get(key, []) if contains(spans, t) and rates.get(t, 0) > 0 and v <= rates[t]]
        result.append({'namespace': key[0], 'workload': key[1], 'samples': len(ratios),
                       'time_median': median(v for t,v in ratios) if ratios else None,
                       'maximum': max((v for t,v in ratios), default=None),
                       'source': ['metrics/http_5xx_rate.json', 'metrics/traffic_rps.json']})
    return result
