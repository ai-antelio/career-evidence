"""Renew a fenced execution lease during slow provider/parser operations."""
import threading,time
from contextlib import contextmanager
from sqlalchemy import update

@contextmanager
def renew_lease(Session, model, job_id, token):
    stopped=threading.Event()
    def heartbeat():
        while not stopped.wait(30):
            try:
                with Session.begin() as db:
                    changed=db.execute(update(model).where(model.id==job_id,model.status=='running',model.lease_token==token).values(lease_until=time.time()+600))
                    if changed.rowcount!=1:return
            except Exception:
                # Commit fencing remains authoritative if connectivity is lost.
                pass
    thread=threading.Thread(target=heartbeat,daemon=True);thread.start()
    try:yield
    finally:stopped.set();thread.join(timeout=1)
