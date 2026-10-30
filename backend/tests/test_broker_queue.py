import time
import pytest
from sqlalchemy import select,func
from test_profile import env,client,upload
from app.models import Job,Document,DispatchEvent
from app import worker
from app.outbox import enqueue,publish_once,recover_stalled

def test_upload_atomically_enqueues_identifier_only(env):
    c=client();upload(c)
    with worker.Session() as db:
        row=db.scalar(select(DispatchEvent));job=db.scalar(select(Job))
        assert row.topic=='document' and row.target_id==job.id and row.status=='pending'
        assert not hasattr(row,'payload')

def test_transaction_rollback_drops_outbox(env):
    with pytest.raises(RuntimeError):
        with worker.Session.begin() as db:
            enqueue(db,'career','rolled-back')
            raise RuntimeError()
    with worker.Session() as db:assert db.scalar(select(func.count()).select_from(DispatchEvent))==0

def test_publish_failure_retains_pending_and_redacts_error(env):
    c=client();upload(c)
    def fail(*args):raise RuntimeError('amqp://user:secret@host and résumé content')
    assert publish_once(worker.Session,fail)
    with worker.Session.begin() as db:
        row=db.scalar(select(DispatchEvent));assert row.status=='pending' and row.attempts==1
        assert row.error=='Broker publish failed';row.available_at=0
    sent=[];assert publish_once(worker.Session,lambda *args:sent.append(args))
    with worker.Session() as db:assert db.scalar(select(DispatchEvent)).status=='published'
    assert len(sent)==1 and sent[0][0]=='document'

def test_celery_duplicate_dispatch_is_idempotent(env):
    from app.celery_app import dispatch
    c=client();upload(c)
    with worker.Session() as db:jid=db.scalar(select(Job.id))
    assert dispatch.run('document',jid)
    assert not dispatch.run('document',jid)
    assert len(c.get('/proposals').json())>0
    with worker.Session() as db:assert db.get(Job,jid).attempts==1

def test_recovery_republishes_lost_delivery_not_pending(env):
    c=client();upload(c)
    assert recover_stalled(worker.Session)==0
    publish_once(worker.Session,lambda *args:None)
    with worker.Session.begin() as db:db.scalar(select(DispatchEvent)).published_at=time.time()-90
    assert recover_stalled(worker.Session)==1
    assert recover_stalled(worker.Session)==0

def test_retry_enqueues_new_dispatch(env,monkeypatch):
    c=client();upload(c)
    monkeypatch.setattr(worker,'parse',lambda *args: (_ for _ in ()).throw(OSError('temporary')))
    assert worker.run_once()
    with worker.Session() as db:
        assert db.scalar(select(func.count()).select_from(DispatchEvent))==2
        assert db.scalar(select(Job)).status=='queued'

def test_celery_durable_security_configuration():
    from app.celery_app import celery
    assert celery.conf.task_acks_late and celery.conf.task_reject_on_worker_lost
    assert celery.conf.accept_content==['json']
    assert celery.conf.broker_transport_options['confirm_publish']
    assert all(q.durable for q in celery.conf.task_queues)
    assert celery.conf.task_ignore_result

def test_live_rabbitmq_worker_round_trip(env,monkeypatch):
    """Opt in with LIVE_BROKER_URL against a disposable local RabbitMQ broker."""
    import os
    if not os.getenv('LIVE_BROKER_URL'):pytest.skip('Real RabbitMQ not configured')
    from celery.contrib.testing.worker import start_worker
    from app.celery_app import celery
    from app import db as database
    monkeypatch.setattr(database,'Session',env)
    celery.conf.broker_url=os.environ['LIVE_BROKER_URL']
    # Fixture data only, actual Celery consumer and persistent AMQP publish.
    c=client('broker@example.test');upload(c)
    with start_worker(celery,perform_ping_check=False,pool='solo',concurrency=1,queues=['documents'],shutdown_timeout=15):
        assert publish_once(env)
        deadline=time.time()+20
        while time.time()<deadline:
            with env() as db:
                row=db.scalar(select(Job))
                if row.status=='completed':break
            time.sleep(.1)
        with env() as db:assert db.scalar(select(Job)).status=='completed'
        assert len(c.get('/proposals').json())>0
