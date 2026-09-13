import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from testbed.configuration import ROOT, resolve_scenario
from testbed.platform import run_one

SOURCE=ROOT/'resources/scenarios/online-boutique-scenario/01-node-delay-worker-3.json'


@pytest.mark.parametrize('failure', [None,'prerun','execution','postrun','cleanup','acquire'])
def test_finalization_and_ownership_failures_are_visible(tmp_path,failure):
    spec=resolve_scenario(SOURCE)
    spec['integration']='bundled' if failure=='acquire' else 'example'
    events=[]
    class Lifecycle:
        def __init__(self,*args):pass
        def integration(self,action):
            events.append(action)
            if failure=='acquire' and action=='prepare':raise RuntimeError('owned by another run')
        def hooks(self,phase,**kwargs):
            events.append(phase)
            if phase==failure:
                if phase=='prerun':raise RuntimeError('pre-run failed')
                return ['post-run failed']
            return []
    def execute(args):
        events.append('execution')
        if failure=='execution':raise RuntimeError('workload failed')
        return 0
    with patch('testbed.platform.Lifecycle',Lifecycle), patch('testbed.platform.run_script',return_value=SimpleNamespace(returncode=1 if failure=='cleanup' else 0)) as cleanup:
        code,safe=run_one(spec,{'port_forward':False,'port_forward_port':8888},tmp_path/'run',execute)
    if failure is None:
        assert code==0 and safe
        assert events==['prepare','prerun','execution','stop','postrun','release']
    elif failure=='acquire':
        assert events==['prepare']
        cleanup.assert_not_called()
    else:
        assert events[-2:]==['stop','postrun']
        assert 'release' not in events
    if failure:
        assert code!=0 and not safe
        assert json.loads((tmp_path/'run/run-status.json').read_text())['status']=='failed'
    if failure=='prerun':assert 'execution' not in events
