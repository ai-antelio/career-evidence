"""Document job executor. Production delivery is through Celery, not DB polling."""
import os, time, uuid
from pathlib import Path
from sqlalchemy import select, update, or_, and_
from .db import Session
from .models import Job, Document, Proposal, GenerationRun
from .ai_gateway import extract_facts, GatewayError
import subprocess, sys, json

def parse(data, filename):
    try:
        result = subprocess.run([sys.executable, "-m", "app.parse_runner", filename], input=data, capture_output=True, timeout=40, check=True)
        response = json.loads(result.stdout)
    except (subprocess.SubprocessError, ValueError):
        raise ValueError("Document parser exceeded its limits or could not read the file")
    if "error" in response: raise ValueError(response["error"])
    return response["text"]

def run_once(job_id=None):
    now = time.time(); token = str(uuid.uuid4())
    eligible = or_(and_(Job.status == 'queued', Job.available_at <= now), and_(Job.status == 'running', Job.lease_until < now))
    with Session.begin() as db:
        query = select(Job).where(eligible)
        if job_id: query=query.where(Job.id==job_id)
        row = db.scalar(query.order_by(Job.available_at).with_for_update(skip_locked=True).limit(1))
        if not row:
            if job_id:return False
            from .career_worker import run_once as career_run_once
            return career_run_once(Session)
        if row.attempts >= 3:
            row.status = 'failed'; row.error = 'Worker recovery limit reached; retry processing'
            db.get(Document, row.document_id).status = 'failed'
            return True
        job_id = row.id
        changed = db.execute(update(Job).where(Job.id == job_id, eligible).values(status='running', attempts=Job.attempts+1, lease_token=token, lease_until=now+600))
        if changed.rowcount != 1: return False
        doc = db.get(Document, row.document_id)
        filename, key = doc.filename, doc.storage_key
        doc.status = 'processing'
    try:
        from .queue_lease import renew_lease
        with renew_lease(Session,Job,job_id,token):
            text = parse((Path(os.getenv('STORAGE_ROOT', './private-storage')) / key).read_bytes(), filename)
            extraction = extract_facts(text)
            proposals = extraction.proposals
            if not proposals: raise ValueError('No reviewable passages found')
        with Session.begin() as db:
            job = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
            if not job or job.lease_token != token or job.status != 'running': return True
            doc = db.get(Document, job.document_id)
            from .tracking import deletion_pending
            if not doc or deletion_pending(db,doc.owner_id):return True
            if not db.scalar(select(Proposal.id).where(Proposal.document_id == doc.id).limit(1)):
                db.add_all(Proposal(owner_id=doc.owner_id, document_id=doc.id, **p) for p in proposals)
            db.add(GenerationRun(document_id=doc.id, owner_id=doc.owner_id, job_id=job.id, status='completed', metadata_json=extraction.audit))
            doc.text = text; doc.status = 'ready'; job.status = 'completed'; job.error = ''
    except Exception as exc:
        with Session.begin() as db:
            job = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
            if not job or job.lease_token != token or job.status != 'running': return True
            if isinstance(exc, GatewayError):
                doc = db.get(Document, job.document_id)
                db.add(GenerationRun(document_id=doc.id, owner_id=doc.owner_id, job_id=job.id, status='failed', error_code=exc.code, metadata_json=exc.audit))
            job.error = str(exc)[:300] if isinstance(exc, (ValueError, GatewayError)) else 'Document processing failed'
            job.status = 'failed' if job.attempts >= 3 or isinstance(exc, ValueError) or (isinstance(exc, GatewayError) and not exc.retryable) else 'queued'
            job.available_at = time.time() + min(60, 2 ** job.attempts)
            db.get(Document, job.document_id).status = job.status
    return True

if __name__ == '__main__':
    raise SystemExit("Use celery -A app.celery_app:celery worker; run the relay with python -m app.outbox")
