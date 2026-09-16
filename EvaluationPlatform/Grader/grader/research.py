"""Evidence-based incident outcomes. Never infer observations from agent prose."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime
from pathlib import Path
from statistics import median

DEFAULT_POLICY = Path(__file__).resolve().parents[1] / 'resources' / 'evaluation-policy.json'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def read(path, default=None):
    if not path.is_file():
        return default
    return json.loads(path.read_text(), parse_constant=lambda x: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def policy(path=None):
    value = read(Path(path or DEFAULT_POLICY))
    expected = read(DEFAULT_POLICY)
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError('evaluation policy fields must match the documented policy')
    if value['schema_version'] != 1 or value['methodology_version'] not in ('archive-recovery-v3', 'sustained-recovery-v2'):
        raise ValueError('unsupported evaluation policy version')
    for key in set(value) - {'schema_version', 'methodology_version'}:
        if isinstance(value[key], bool) or not isinstance(value[key], (int, float)) or not math.isfinite(value[key]) or value[key] < 0:
            raise ValueError('invalid policy number: ' + key)
    for key in ('baseline_seconds', 'interval_seconds', 'sustain_seconds', 'minimum_requests', 'bootstrap_samples'):
        if not isinstance(value[key], int) or value[key] <= 0:
            raise ValueError('policy requires positive integer: ' + key)
    for key in ('baseline_seconds', 'sustain_seconds'):
        if value[key] % value['interval_seconds']:
            raise ValueError(key + ' must be a multiple of interval_seconds')
    if value['interval_seconds'] != 30:
        raise ValueError('this methodology requires 30-second intervals')
    if value['baseline_seconds'] < 300 or value['latency_multiplier'] < 1:
        raise ValueError('baseline must cover at least five minutes; latency multiplier must be >= 1')
    if any(not 0 < value[k] <= 1 for k in ('minimum_coverage', 'throughput_fraction')):
        raise ValueError('coverage and throughput fractions must be in (0,1]')
    if any(not 0 <= value[k] <= 1 for k in ('failure_ratio_allowance', 'maximum_baseline_failure_ratio')):
        raise ValueError('failure ratios must be in [0,1]')
    return value


def epoch(value):
    if not isinstance(value, str):
        raise ValueError('missing timestamp')
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.utcoffset() is None or dt.utcoffset().total_seconds() != 0:
        raise ValueError('evidence timestamps must be UTC')
    return dt.timestamp()


def jsonl(path):
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def references(root, refs):
    if not isinstance(refs, list) or not refs:
        return False
    for ref in refs:
        if not isinstance(ref, str):
            return False
        path = (root / ref.split('#', 1)[0]).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            return False
    return True


def records(root, name, run_id):
    rows = jsonl(root / 'evidence' / (name + '.jsonl'))
    for row in rows:
        if row.get('schema_version') != 1 or row.get('run_id') != run_id or row.get('incident_id') != run_id:
            raise ValueError('invalid evidence identity: ' + name)
        epoch(row['timestamp'])
        if not row.get('source') or not row.get('event_type') or not references(root, row.get('evidence_refs')):
            raise ValueError('missing evidence provenance: ' + name)
    return rows


def inventory(root):
    return {name: sorted(str(p.relative_to(root)) for p in root.glob(pattern) if p.is_file())
            for name, pattern in {'telemetry': 'metrics/*.json', 'client': 'loadgenerator/*',
                                  'sessions': 'sessions/*.json', 'evidence': 'evidence/*'}.items()}


def histogram(rows):
    combined = {}
    for row in rows:
        for upper, count in row['latency_histogram']:
            combined[upper] = combined.get(upper, 0) + count
    return sorted(combined.items())


def quantile(bins, q=.95):
    n = sum(count for _, count in bins)
    if not n:
        return None
    total = 0
    for upper, count in bins:
        total += count
        if total >= math.ceil(n * q):
            return upper


def summary(rows):
    attempted = sum(r['attempted'] for r in rows)
    failed = sum(r['failed'] for r in rows)
    seconds = sum(epoch(r['end']) - epoch(r['start']) for r in rows)
    return {'attempted': attempted, 'failed': failed,
            'failure_ratio': failed / attempted if attempted else None,
            'successful_rps': (attempted - failed) / seconds if seconds else None,
            'p95_seconds': quantile(histogram(rows))}


def validate_intervals(rows, run_id):
    previous = None
    for r in rows:
        start, end = epoch(r['start']), epoch(r['end'])
        if r.get('schema_version') != 1 or r.get('run_id') != run_id or r.get('incident_id') != run_id:
            raise ValueError('invalid client identity')
        if previous is not None and start < previous or end <= start:
            raise ValueError('client intervals overlap or are unordered')
        previous = end
        if any(isinstance(r[k], bool) or not isinstance(r[k], int) or r[k] < 0 for k in ('attempted', 'failed')) or r['failed'] > r['attempted']:
            raise ValueError('invalid request counts')
        if not 0 <= r['observed_seconds'] <= end - start:
            raise ValueError('invalid observed duration')
        bins = r['latency_histogram']
        if any(not math.isfinite(u) or u < 0 or not isinstance(n, int) or isinstance(n, bool) or n < 0 for u, n in bins):
            raise ValueError('invalid latency histogram')
        if [u for u, _ in bins] != sorted(set(u for u, _ in bins)) or sum(n for _, n in bins) != r['attempted']:
            raise ValueError('histogram must count every attempted request exactly once')


def qualified(row, p):
    duration = epoch(row['end']) - epoch(row['start'])
    return (abs(duration - p['interval_seconds']) < .01
            and row['observed_seconds'] / duration >= p['minimum_coverage']
            and row['attempted'] >= p['minimum_requests'])


def operational(root, p, events, run_id, metadata):
    result = {'status': 'not_evaluable', 'reason': None, 'recovered': None,
              'recovery_seconds': None, 'recovery_at': None, 'active_fault_recovery': None,
              'censored': None, 'baseline': None, 'harm': None, 'intervals': []}
    def unavailable(reason, status='not_evaluable'):
        result.update(status=status, reason=reason)
        return result
    rows = jsonl(root / 'evidence/client-intervals.jsonl')
    validate_intervals(rows, run_id)
    def select(kind):
        return sorted((e for e in events if e['event_type'] == kind), key=lambda e: epoch(e['timestamp']))
    starts, ends = select('baseline_started'), select('baseline_completed')
    faults, deadlines = select('fault_observed_active'), select('observation_completed')
    if not starts or not ends or not rows:
        return unavailable('missing observed baseline or client intervals')
    begin, end = epoch(starts[-1]['timestamp']), epoch(ends[-1]['timestamp'])
    if end - begin < p['baseline_seconds'] or ends[-1].get('data', {}).get('health_passed') is not True:
        return unavailable('baseline duration or health check failed', 'invalid')
    # Select complete intervals. End is aligned to the last client interval before baseline completion.
    eligible = [r for r in rows if epoch(r['start']) >= begin and epoch(r['end']) <= end]
    if not eligible:
        return unavailable('baseline client intervals unavailable')
    cutoff = epoch(eligible[-1]['end'])
    baseline = [r for r in eligible if epoch(r['start']) >= cutoff - p['baseline_seconds']]
    if (len(baseline) != p['baseline_seconds'] // p['interval_seconds'] or
            not all(qualified(r, p) for r in baseline) or
            any(epoch(b['start']) != epoch(a['end']) for a, b in zip(baseline, baseline[1:]))):
        return unavailable('baseline coverage/request volume insufficient')
    base = summary(baseline)
    result['baseline'] = base
    if base['failure_ratio'] > p['maximum_baseline_failure_ratio']:
        return unavailable('baseline failure ratio exceeds policy', 'invalid')
    if not faults or not deadlines:
        return unavailable('observed fault onset or completed observation unavailable')
    onset, deadline = epoch(faults[0]['timestamp']), epoch(deadlines[-1]['timestamp'])
    experiment = read(root / 'evidence/experiment.json', {})
    planned = experiment.get('deadline_seconds')
    if planned is not None:
        if not isinstance(planned, (int, float)) or planned <= 0 or deadline < onset + planned:
            return unavailable('matched observation deadline was not reached')
        deadline = onset + planned
    if onset < end or deadline <= onset:
        return unavailable('invalid fault/observation ordering', 'invalid')
    guard = service_coverage(root, cutoff - p['baseline_seconds'], cutoff, onset, deadline, p)
    result['service_coverage'] = guard
    if guard['status'] != 'complete':
        return unavailable('baseline-active service telemetry is missing or incomplete')
    result['observation_seconds'] = deadline - onset
    result['fault_onset'] = faults[0]['timestamp']
    limits = {'p95_seconds': base['p95_seconds'] * p['latency_multiplier'],
              'failure_ratio': base['failure_ratio'] + p['failure_ratio_allowance'],
              'successful_rps': base['successful_rps'] * p['throughput_fraction']}
    result['limits'] = limits
    incident = [r for r in rows if epoch(r['start']) >= onset and epoch(r['end']) <= deadline]
    valid = [r for r in incident if qualified(r, p)]
    measured_seconds = sum(epoch(r['end']) - epoch(r['start']) for r in valid)
    coverage = measured_seconds / (deadline - onset)
    result['coverage'] = coverage
    result['harm'] = {**summary(incident), 'measured_seconds': sum(epoch(r['end']) - epoch(r['start']) for r in incident),
                      'coverage_adequate': coverage >= p['minimum_coverage'],
                      'slow_requests_lower_bound': sum(n for u, n in histogram(incident) if u > limits['p95_seconds'] and
                         next((low for low, high in zip([0] + [x[0] for x in histogram(incident)], [x[0] for x in histogram(incident)]) if high == u), 0) >= limits['p95_seconds']),
                      'slow_requests_upper_bound': sum(n for u, n in histogram(incident) if u > limits['p95_seconds'])}
    streak, previous = [], None
    recovery_candidates = []
    for row in incident:
        s = summary([row]); start, finish = epoch(row['start']), epoch(row['end'])
        ok = qualified(row, p) and s['p95_seconds'] <= limits['p95_seconds'] and s['failure_ratio'] <= limits['failure_ratio'] and s['successful_rps'] >= limits['successful_rps']
        if previous != start or not ok:
            streak = []
        if ok:
            streak.append(row)
        previous = finish
        result['intervals'].append({'start': row['start'], 'end': row['end'], **s, 'qualified': qualified(row, p), 'healthy': ok})
        if len(streak) * p['interval_seconds'] >= p['sustain_seconds']:
            candidate = streak[-p['sustain_seconds'] // p['interval_seconds']:]
            recovery_candidates.append((epoch(candidate[0]['start']), finish, candidate[0]['start']))
    if coverage < p['minimum_coverage']:
        return unavailable('incident telemetry coverage insufficient')
    result.update(status='recovered' if recovery_candidates else 'unresolved', recovered=bool(recovery_candidates), censored=not bool(recovery_candidates))
    if not recovery_candidates:
        return result
    recovery_start, recovery_end, recovery_at = recovery_candidates[0]
    result.update(recovery_at=recovery_at, recovery_seconds=recovery_start - onset)
    # Observer emits bounded active intervals, not an inference from Schedule creation.
    spans = [e['data'] for e in select('fault_active_interval')]
    removed = select('fault_observed_removed')
    recurring = faults[0].get('data', {}).get('recurring', False)
    result['active_fault_recovery'] = False if spans or removed else None
    for a, b, at in recovery_candidates:
        intersecting = [s for s in spans if epoch(s['end']) > a and epoch(s['start']) < b]
        active_seconds = sum(max(0, min(b, epoch(s['end'])) - max(a, epoch(s['start']))) for s in intersecting)
        cycles = {s['cycle_id'] for s in intersecting}
        # Recurring windows may contain natural idle periods, but must span a new cycle.
        active_ok = (len(cycles) >= 2 if recurring else active_seconds >= b - a - .01)
        if active_ok and not any(a <= epoch(e['timestamp']) < b for e in removed):
            result['active_fault_recovery'] = True
            result['active_recovery_at'] = at
            result['active_recovery_seconds'] = a - onset
            break
    return result


def evaluate_incident(root, override=None):
    root = Path(root)
    archived_policy = root / 'inputs/evaluation-policy.json'
    policy_error = False
    try:
        p = policy(override or (archived_policy if archived_policy.exists() else None))
    except (ValueError, TypeError, KeyError, OSError):
        if override:
            raise
        p = policy()
        policy_error = True
    result = {'methodology_version': p['methodology_version'], 'policy_hash': digest(p), 'policy': p,
              'policy_source': 'override' if override else 'archived' if archived_policy.exists() else 'default',
              'inventory': inventory(root), 'limitations': [], 'safety': {'status': 'unverified'},
              'execution': {'status': 'unverified', 'applied_actions': None}, 'safe_recovery': None,
              'evidence_quality': 'reported_evidence_quality', 'experiment_type': 'incident'}
    if policy_error:
        result['policy_source'] = 'invalid_archive'
        result['operational'] = {'status': 'invalid', 'reason': 'archived evaluation policy is invalid'}
        result['limitations'].append('Invalid archived policy; no recovery score computed.')
        return result
    try:
        metadata = read(root / 'metadata.json', {})
        context = read(root / 'run-context.json', {})
        run_id = context.get('run_id', root.name)
        spec = context.get('scenario') or read(root / 'inputs/scenario.json', {})
        if spec.get('steps') and all(not step.get('chaos') for step in spec['steps']):
            result['experiment_type'] = 'healthy_control' if spec.get('agents_enabled', metadata.get('agents_enabled')) else 'workload_only'
        events = records(root, 'events', run_id)
        actions, observations = [], []
        invalid_optional = set()
        for name, target in [('actions', actions), ('observations', observations)]:
            try:
                target.extend(records(root, name, run_id))
            except (ValueError, KeyError, TypeError, OSError):
                invalid_optional.add(name)
                result['limitations'].append('Invalid optional ' + name + ' evidence ignored.')
        result['evidence_quality'] = 'referenced_observations' if observations else 'reported_evidence_quality'
        if (root / 'evidence/client-intervals.jsonl').exists():
            result['operational'] = operational(root, p, events, run_id, metadata)
            result['operational']['measurement_basis'] = 'portable_client_histograms'
        else:
            from .archive_metrics import evaluate_archive
            result['operational'] = evaluate_archive(root, p, metadata)
            result['limitations'].extend(result['operational'].get('limitations', []))
        status = read(root / 'run-status.json', {})
        if status.get('status') in ('failed', 'interrupted') or metadata.get('status') in ('failed', 'interrupted', 'cleanup_failed'):
            result['operational'].update(status='invalid', reason='experiment infrastructure failure or interruption', recovered=None)
        applied = [a for a in actions if a['event_type'] == 'action_applied' and a.get('data', {}).get('verified') is True]
        result['execution'] = {'status': 'verified' if applied else 'unverified', 'applied_actions': len(applied) if actions else None}
        try:
            safety = read(root / 'evidence/safety.json', {})
            if not isinstance(safety, dict):
                raise ValueError('invalid safety assessment')
            if safety:
                epoch(safety.get('timestamp'))
        except (ValueError, TypeError, OSError):
            safety = {}
            result['limitations'].append('Invalid independent safety assessment ignored.')
        if (safety.get('schema_version') == 1 and safety.get('run_id') == run_id and safety.get('incident_id') == run_id
                and safety.get('source') and safety.get('event_type') == 'safety_assessment'
                and references(root, safety.get('evidence_refs'))):
            epoch(safety['timestamp'])
            violations = safety.get('critical_violations')
            if isinstance(violations, list) and all(isinstance(v, str) and v for v in violations) and violations:
                result['safety'] = {'status': 'unsafe', 'critical_violations': safety['critical_violations']}
            elif safety.get('coverage_complete') is True and violations == []:
                result['safety'] = {'status': 'verified_safe', 'critical_violations': []}
        op = result['operational']
        if result['safety']['status'] == 'unsafe':
            result['safe_recovery'] = False
        elif op['status'] == 'unresolved':
            result['safe_recovery'] = False
        elif op['status'] == 'recovered' and result['safety']['status'] == 'verified_safe':
            result['safe_recovery'] = True
        try:
            result['supporting'] = supporting(root, events, None if 'actions' in invalid_optional else actions, op)
        except (ValueError, KeyError, TypeError, OSError):
            result['supporting'] = {}
            result['limitations'].append('Supporting measurements unavailable.')
        result['experiment'] = read(root / 'evidence/experiment.json', {})
        result['diagnostics'] = diagnostics(root)
        try:
            from .archive_metrics import error_ratios
            result['diagnostics']['derived_http_5xx_ratio'] = error_ratios(root)
        except (ValueError, TypeError, KeyError, OSError, AttributeError):
            result['diagnostics']['derived_http_5xx_ratio'] = {'status': 'not_evaluable'}
        result['application'] = metadata.get('application', context.get('scenario', {}).get('application', 'unknown'))
        if not observations:
            result['limitations'].append('Final-result evidence claims have not been independently verified.')
        if result['safety']['status'] == 'unverified':
            result['limitations'].append('A complete independent safety assessment is unavailable.')
    except (ValueError, TypeError, KeyError, OSError, AttributeError) as exc:
        result['operational'] = {'status': 'not_evaluable', 'reason': 'invalid or missing evidence: ' + type(exc).__name__}
        result['limitations'].append(result['operational']['reason'])
    return result


def supporting(root, events, actions, op):
    def jobs(name):
        rows = read(root / 'sessions' / (name + '.json'), [])
        return rows if isinstance(rows, list) else []
    rca, rem = jobs('rca_session'), jobs('remediation_run')
    timings = []
    for kind, rows in [('rca', rca), ('remediation', rem)]:
        for r in rows:
            def delta(a, b):
                try:
                    value = epoch(r[b]) - epoch(r[a])
                    return value if value >= 0 else None
                except (KeyError, ValueError, TypeError):
                    return None
            timings.append({'kind': kind, 'job_id': r.get('id'), 'status': r.get('status'),
                            'queue_seconds': delta('created_at', 'started_at'),
                            'execution_seconds': delta('started_at', 'completed_at')})
    detections = [e for e in events if e['event_type'] == 'incident_detected' and e.get('data', {}).get('matched') is True]
    onset = op.get('fault_onset')
    detection_delay = min((epoch(e['timestamp']) - epoch(onset) for e in detections if onset and epoch(e['timestamp']) >= epoch(onset)), default=None)
    coverage = [e for e in events if e['event_type'] == 'detection_coverage_complete']
    healthy = [e for e in events if e['event_type'] == 'healthy_monitoring_completed']
    seconds = sum(e.get('data', {}).get('seconds', 0) for e in healthy)
    false_alerts = [e for e in events if e['event_type'] == 'false_alert_confirmed']
    return {'rca_attempts': len(rca) if (root / 'sessions/rca_session.json').exists() else None, 'remediation_attempts': len(rem) if (root / 'sessions/remediation_run.json').exists() else None, 'job_timings': timings,
            'tool_calls': tool_count(root, rca, actions),
            'detection_recall': int(detection_delay is not None) if coverage and onset else None,
            'detection_delay_seconds': detection_delay,
            'false_alerts_per_healthy_hour': len(false_alerts) / (seconds / 3600) if seconds > 0 and coverage else None,
            'model_usage': model_usage(root),
            'resource_usage': resource_usage(root)}


def resource_usage(root):
    output = {}
    for name in ('deployment_cpu_usage', 'app_instance_count'):
        data = read(root / 'metrics' / (name + '.json'), {})
        rows = []
        for series in data.get('data', {}).get('result', []):
            samples = [(float(t), float(v)) for t, v in series.get('values', []) if math.isfinite(float(v))]
            integral = sum((b[0] - a[0]) * (a[1] + b[1]) / 2 for a, b in zip(samples, samples[1:]) if 0 < b[0] - a[0] <= 60)
            rows.append({'labels': series.get('metric', {}), 'integral': integral if len(samples) > 1 else None})
        output[name] = rows
    return output


def diagnostics(root):
    """Preserve workload series; never aggregate service percentiles into app latency."""
    output = {}
    for path in sorted((root / 'metrics').glob('*.json')):
        try:
            data = read(path, {})
            series = []
            for row in data.get('data', {}).get('result', []):
                values = [(float(t), float(v)) for t,v in row.get('values', []) if math.isfinite(float(t)) and math.isfinite(float(v))]
                series.append({'labels': row.get('metric', {}), 'samples': len(values),
                               'minimum': min((v for t,v in values), default=None),
                               'maximum': max((v for t,v in values), default=None),
                               'time_median': median(v for t,v in values) if values else None,
                               'first_timestamp': values[0][0] if values else None,
                               'last_timestamp': values[-1][0] if values else None})
            output[path.stem] = series
        except (ValueError, TypeError, AttributeError, KeyError):
            output[path.stem] = {'status': 'not_evaluable'}
    return output


def model_usage(root):
    raw = read(root / 'evidence/model-usage.json')
    if not isinstance(raw, dict) or raw.get('schema_version') != 1:
        return None
    fields = ('input_tokens', 'output_tokens', 'input_price_per_million', 'output_price_per_million')
    out = {k: raw.get(k) for k in fields}
    for key, value in out.items():
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int,float)) or not math.isfinite(value) or value < 0):
            raise ValueError('invalid model usage')
    out['cost'] = ((out['input_tokens'] * out['input_price_per_million'] +
                    out['output_tokens'] * out['output_price_per_million']) / 1_000_000
                   if all(v is not None for v in out.values()) and raw.get('currency') and raw.get('pricing_date') else None)
    for k in ('model', 'model_revision', 'currency', 'pricing_date'):
        out[k] = raw.get(k)
    return out


def service_coverage(root, base_start, base_end, onset, deadline, p):
    """Mesh coverage guard only: missing workloads cannot silently disappear.

Client measurements define success; mesh service percentiles are not pooled.
"""
    payload = read(root / 'metrics/traffic_rps.json', {})
    baseline_targets = set()
    covered = set()
    for series in payload.get('data', {}).get('result', []):
        labels = series.get('metric', {})
        target = (labels.get('destination_workload_namespace'), labels.get('destination_workload'))
        if not all(target):
            continue
        samples = [(float(t),float(v)) for t,v in series.get('values', []) if math.isfinite(float(t)) and math.isfinite(float(v))]
        baseline = [(t,v) for t,v in samples if base_start <= t <= base_end]
        if not any(v > 0 for t,v in baseline):
            continue
        baseline_targets.add(target)
        after = [(t,v) for t,v in samples if onset <= t <= deadline]
        def complete(rows, duration):
            times = sorted(set(t for t,v in rows))
            measured = sum(b-a for a,b in zip(times,times[1:]) if 0 < b-a <= 60)
            return len(times) >= 2 and measured / duration >= p['minimum_coverage']
        if complete(baseline, base_end-base_start) and complete(after, deadline-onset):
            covered.add(target)
    return {'status': 'complete' if baseline_targets and covered == baseline_targets else 'not_evaluable',
            'required': [list(x) for x in sorted(baseline_targets)],
            'missing': [list(x) for x in sorted(baseline_targets-covered)],
            'source': 'metrics/traffic_rps.json'}


def tool_count(root, rca, actions):
    if actions is None:
        return None
    if (root / 'evidence/actions.jsonl').exists():
        return sum(a['event_type'] == 'tool_call_recorded' for a in actions)
    # Historical bundled archives can supply counts without exposing tool contents.
    rem = read(root / 'sessions/remediation_session.json')
    if (root / 'sessions/rca_session.json').exists() and isinstance(rem, list):
        jobs = rca + rem
        if all(isinstance(j, dict) and isinstance(j.get('tool_calls'), list) for j in jobs):
            return sum(len(j['tool_calls']) for j in jobs)
    return None
