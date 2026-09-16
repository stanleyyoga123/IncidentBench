import pytest

from hooks import reset_evaluation_lock as recovery


def test_release_running_owner_without_reset(monkeypatch):
    actions = []

    def api(context, action):
        assert context['run_id'] == 'interrupted-run'
        actions.append(action)
        return {'run_id': None if action == 'release' else 'interrupted-run',
                'maintenance': action != 'state'}

    monkeypatch.setattr(recovery, 'api', api)
    recovery.reset_lock({}, 'interrupted-run')
    assert actions == ['state', 'pause', 'release']


@pytest.mark.parametrize('owner', [None, 'another-run'])
def test_no_mutation_for_clear_or_different_owner(monkeypatch, owner):
    actions = []

    def api(context, action):
        actions.append(action)
        return {'run_id': owner}

    monkeypatch.setattr(recovery, 'api', api)
    if owner is None:
        recovery.reset_lock({}, 'interrupted-run')
    else:
        with pytest.raises(ValueError, match='does not match'):
            recovery.reset_lock({}, 'interrupted-run')
    assert actions == ['state']


def test_failed_pause_does_not_release(monkeypatch):
    actions = []

    def api(context, action):
        actions.append(action)
        if action == 'pause':
            raise RuntimeError('Orchestrator pause returned HTTP 409')
        return {'run_id': 'interrupted-run'}

    monkeypatch.setattr(recovery, 'api', api)
    with pytest.raises(RuntimeError, match='409'):
        recovery.reset_lock({}, 'interrupted-run')
    assert actions == ['state', 'pause']


def test_discovers_current_owner(monkeypatch):
    calls = []
    def api(context, action):
        calls.append((action, context['run_id']))
        return {'run_id': None if action == 'release' else 'stale-run', 'maintenance': True}
    monkeypatch.setattr(recovery, 'api', api)
    recovery.reset_lock({})
    assert calls == [('state', ''), ('pause', 'stale-run'), ('release', 'stale-run')]


def test_discovery_already_clear(monkeypatch):
    calls = []
    def api(context, action):
        calls.append(action)
        return {'run_id': None}
    monkeypatch.setattr(recovery, 'api', api)
    recovery.reset_lock({})
    assert calls == ['state']


def test_discovered_owner_changes_before_pause(monkeypatch):
    calls = []
    def api(context, action):
        calls.append(action)
        if action == 'pause':
            assert context['run_id'] == 'old-run'
            raise RuntimeError('Orchestrator pause returned HTTP 409')
        return {'run_id': 'old-run'}
    monkeypatch.setattr(recovery, 'api', api)
    with pytest.raises(RuntimeError, match='409'):
        recovery.reset_lock({})
    assert calls == ['state', 'pause']
