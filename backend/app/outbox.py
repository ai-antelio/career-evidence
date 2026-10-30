"""Atomic database outbox -> confirmed persistent RabbitMQ messages.

A crash after publish but before commit repeats delivery. Target jobs are fenced and
idempotent, so delivery is explicitly at least once, never exactly once.
"""
import time, uuid
from sqlalchemy import event, inspect, select, or_, and_
from sqlalchemy.orm import Session as ORMSession
from .queue_models import DispatchEvent

def enqueue(db, topic, target_id, available_at=None):
    if topic not in {'document','career','deletion'}: raise ValueError('Unsupported dispatch topic')
    record=DispatchEvent(topic=topic,target_id=target_id,available_at=available_at or time.time())
    db.add(record)
    return record

@event.listens_for(ORMSession, 'before_flush')
def capture_work(db, flush_context, instances):
    from .models import Job, CareerWorkflow
    for obj in list(db.new)+list(db.dirty):
        if not isinstance(obj,(Job,CareerWorkflow)): continue
        status=obj.status or 'queued'
        if status!='queued': continue
        if obj not in db.new and not inspect(obj).attrs.status.history.has_changes(): continue
        if not obj.id: obj.id=str(uuid.uuid4())
        enqueue(db,'document' if isinstance(obj,Job) else 'career',obj.id,obj.available_at)

def publish_once(Session, publisher=None):
    if publisher is None:
        from .celery_app import celery
        def publisher(topic,target_id,event_id):
            queue='documents' if topic=='document' else 'maintenance' if topic=='deletion' else 'ai'
            celery.send_task('career.dispatch',args=[topic,target_id],task_id=event_id,queue=queue,delivery_mode=2)
    with Session.begin() as db:
        event_row=db.scalar(select(DispatchEvent).where(DispatchEvent.status=='pending',DispatchEvent.available_at<=time.time()).order_by(DispatchEvent.available_at).with_for_update(skip_locked=True).limit(1))
        if not event_row:return False
        event_row.attempts+=1
        try:
            publisher(event_row.topic,event_row.target_id,event_row.id)
        except Exception:
            # Broker URLs may contain credentials. Never persist exception strings.
            event_row.error='Broker publish failed';event_row.available_at=time.time()+min(60,2**min(event_row.attempts,6))
            return True
        event_row.status='published';event_row.published_at=time.time();event_row.error=''
    return True

def recover_stalled(Session, now=None):
    """Reconcile lost messages/expired workers. No work is executed by this relay."""
    from .models import Job,CareerWorkflow
    now=now or time.time(); count=0
    with Session.begin() as db:
        for cls,topic in [(Job,'document'),(CareerWorkflow,'career')]:
            eligible=or_(and_(cls.status=='queued',cls.available_at<=now),and_(cls.status=='running',cls.lease_until<now))
            for job in db.scalars(select(cls).where(eligible).with_for_update(skip_locked=True)):
                recent=db.scalar(select(DispatchEvent.id).where(DispatchEvent.topic==topic,DispatchEvent.target_id==job.id,or_(DispatchEvent.status=='pending',DispatchEvent.published_at>now-60)).limit(1))
                if not recent:enqueue(db,topic,job.id);count+=1
        from .tracking import recover_deletions
        recover_deletions(db,now)
    return count

def main():
    from .db import Session
    next_recovery=0
    while True:
        try:
            if time.time()>=next_recovery:
                recover_stalled(Session);next_recovery=time.time()+30
            if not publish_once(Session):time.sleep(1)
        except Exception:
            # Database/broker outage: retry without exposing connection strings.
            time.sleep(5)

if __name__=='__main__':main()
