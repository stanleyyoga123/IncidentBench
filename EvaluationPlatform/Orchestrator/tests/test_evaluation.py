from contextlib import contextmanager
from copy import deepcopy
from threading import Event, Thread, Condition

import pytest
from fastapi.testclient import TestClient

from api import create_app
from features.evaluation.evaluation_repository import EvaluationRepository
from features.evaluation.evaluation_service import EvaluationService
from infrastructure.maintenance_gate import MaintenanceGate, LOCK
from infrastructure.workflow_conflict_error import WorkflowConflictError
from test_api import FakeStore, FakeClient, settings


class MemoryDatabase:
    """Small transactional driver exercising the control state machine offline."""
    def __init__(self):
        self.state = {'id':1,'run_id':None,'maintenance':False,'reset_done':False}
        self.reset_count = 0
        self.queries = []
        self.condition = Condition()
        self.readers = 0
        self.writer = False

    @contextmanager
    def connection(self):
        db = self
        class Cursor:
            mode = None
            result = None
            def __enter__(self): return self
            def __exit__(self,*_): pass
            def execute(self, query, params=()):
                db.queries.append(query)
                if 'pg_try_advisory_xact_lock_shared' in query:
                    with db.condition:
                        locked = not db.writer
                        if locked:
                            db.readers += 1
                            self.mode = 'read'
                        self.result = {'locked':locked}
                elif 'pg_advisory_xact_lock(' in query:
                    with db.condition:
                        db.condition.wait_for(lambda:not db.writer and not db.readers)
                        db.writer = True
                        self.mode = 'write'
                elif 'pg_advisory_lock_shared' in query:
                    with db.condition:
                        db.condition.wait_for(lambda:not db.writer)
                        db.readers += 1
                        self.mode = 'read'
                elif query.startswith('SELECT') and 'evaluation_control' in query:
                    self.result = deepcopy(db.state)
                elif 'SET run_id=%s' in query:
                    db.state.update(run_id=params[0],maintenance=True,reset_done=False)
                elif 'SET maintenance=true' in query:
                    db.state['maintenance']=True
                elif 'SET maintenance=false' in query:
                    db.state['maintenance']=False
                elif 'SET reset_done=true' in query:
                    db.state['reset_done']=True
                elif 'SET run_id=NULL' in query:
                    db.state['run_id']=None
                elif query.startswith('TRUNCATE'):
                    db.reset_count += 1
                elif 'json_agg' in query:
                    self.result={'data':[]}
            def fetchone(self): return self.result
        cursor = Cursor()
        class Connection:
            def cursor(self): return cursor
            def commit(self): pass
        try:
            yield Connection()
        finally:
            with self.condition:
                if cursor.mode == 'read':self.readers-=1
                if cursor.mode == 'write':self.writer=False
                self.condition.notify_all()


def test_ownership_reset_idempotency_restart_and_release():
    db=MemoryDatabase(); evaluation=EvaluationService(EvaluationRepository(db))
    assert evaluation.command('acquire','one')['maintenance']
    with pytest.raises(WorkflowConflictError): evaluation.command('acquire','two')
    with pytest.raises(WorkflowConflictError): evaluation.command('reset','two')
    evaluation.command('reset','one')
    EvaluationService(EvaluationRepository(db)).command('reset','one')
    assert db.reset_count==1
    evaluation.command('resume','one')
    with pytest.raises(WorkflowConflictError): evaluation.command('reset','one')
    with pytest.raises(WorkflowConflictError): evaluation.command('release','one')
    evaluation.command('pause','one')
    evaluation.command('release','one')
    assert evaluation.state()['maintenance'] is True
    evaluation.command('acquire','two')
    evaluation.command('reset','two')
    assert db.reset_count==2


def test_maintenance_waits_for_inflight_dispatch_and_blocks_future_work():
    db=MemoryDatabase(); evaluation=EvaluationService(EvaluationRepository(db))
    started, finished = Event(), Event()
    def pause():
        started.set()
        evaluation.command('acquire','one')
        finished.set()
    with MaintenanceGate(db).running():
        thread=Thread(target=pause); thread.start()
        assert started.wait(1)
        assert not finished.wait(0.05)
    thread.join(1)
    assert finished.is_set()
    with pytest.raises(WorkflowConflictError):
        with MaintenanceGate(db).running():
            pytest.fail('maintenance allowed new work')


def test_export_is_consistent_and_requires_ownership_in_maintenance():
    db=MemoryDatabase(); evaluation=EvaluationService(EvaluationRepository(db))
    evaluation.command('acquire','one')
    with pytest.raises(WorkflowConflictError):evaluation.export('two')
    result=evaluation.export('one')
    assert set(result['sessions'])=={'anomaly','rca_session','remediation_run','remediation_session','learning_session','workflow'}
    assert all(value==[] for value in result['sessions'].values())
    assert any('REPEATABLE READ, READ ONLY' in query for query in db.queries)
    lock_index = next(i for i,q in enumerate(db.queries) if 'pg_advisory_lock_shared' in q)
    snapshot_index = next(i for i,q in enumerate(db.queries) if 'REPEATABLE READ' in q)
    assert lock_index < snapshot_index


def test_control_auth_and_paused_api_gates():
    db=MemoryDatabase()
    class Store(FakeStore):
        def connection(self):return db.connection()
    store=Store()
    app=create_app(settings(),start_loops=False,store=store,database=db,rca=FakeClient(),remediator=FakeClient(),learning=FakeClient())
    with TestClient(app) as client:
        endpoint='/api/v1/evaluation/acquire'
        assert client.post(endpoint,json={'run_id':'one'}).status_code==401
        assert client.post(endpoint,headers={'Authorization':'Bearer store'},json={'run_id':'one'}).status_code==401
        assert client.post(endpoint,headers={'Authorization':'Bearer control'},json={'run_id':'one'}).status_code==200
        for endpoint,token,payload in [('/api/v1/anomalies','ingest',{'anomalies':[]}),('/api/v1/internal/rca/jobs','store',{'anomalies':[]})]:
            assert client.post(endpoint,headers={'Authorization':'Bearer '+token},json=payload).status_code==409
        assert client.post('/api/v1/anomalies',json={'anomalies':[]}).status_code==401
        assert client.get('/health').status_code==200
