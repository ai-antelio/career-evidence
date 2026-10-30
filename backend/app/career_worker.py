"""Fenced career job executor, invoked by Celery delivery."""
import time,uuid
from sqlalchemy import select,update,or_,and_,func
from .models import Opportunity,Requirement,CareerWorkflow,MatchRun,ResumeArtifact
from .career_gateway import extract_requirements,match_requirements,draft_resume,digest,verify_claims
from .ai_gateway import GatewayError

def run_once(Session,job_id=None):
    now=time.time();token=str(uuid.uuid4())
    eligible=or_(and_(CareerWorkflow.status=='queued',CareerWorkflow.available_at<=now),and_(CareerWorkflow.status=='running',CareerWorkflow.lease_until<now))
    with Session.begin() as db:
        query=select(CareerWorkflow).where(eligible)
        if job_id:query=query.where(CareerWorkflow.id==job_id)
        w=db.scalar(query.order_by(CareerWorkflow.available_at).with_for_update(skip_locked=True).limit(1))
        if not w:return False
        if w.attempts>=3:w.status='failed';w.error='Worker recovery limit reached; retry processing';return True
        changed=db.execute(update(CareerWorkflow).where(CareerWorkflow.id==w.id,eligible).values(status='running',attempts=CareerWorkflow.attempts+1,lease_token=token,lease_until=now+600))
        if changed.rowcount!=1:return False
        wid,kind,data=w.id,w.kind,w.input_json
    try:
        from .queue_lease import renew_lease
        with renew_lease(Session,CareerWorkflow,wid,token):
            if kind=='requirements':result,audit=extract_requirements(data['description'])
            elif kind=='match':result,audit=match_requirements(data)
            elif kind=='resume_validate':
                certificate,findings,audit=verify_claims(data['claims'],data['facts']);result={'certificate':certificate,'findings':findings}
            elif kind=='draft':
                claims,findings,audit=draft_resume(data);result={'claims':claims,'findings':findings}
            else:
                from .practice_worker import execute
                result,audit=execute(kind,data)
        with Session.begin() as db:
            w=db.scalar(select(CareerWorkflow).where(CareerWorkflow.id==wid).with_for_update())
            if not w or w.status!='running' or w.lease_token!=token:return True
            opp=db.scalar(select(Opportunity).where(Opportunity.id==w.opportunity_id).with_for_update())
            from .tracking import deletion_pending
            if not opp or deletion_pending(db,opp.owner_id):return True
            if kind=='requirements':
                if not db.scalar(select(Requirement.id).where(Requirement.opportunity_id==opp.id).limit(1)):
                    db.add_all(Requirement(opportunity_id=opp.id,**r) for r in result)
                opp.status='ready'
            elif kind=='match':
                if not db.scalar(select(MatchRun.id).where(MatchRun.workflow_id==wid)):
                    db.add(MatchRun(opportunity_id=opp.id,workflow_id=wid,input_hash=w.input_hash,items=result))
            elif kind=='draft':
                version=(db.scalar(select(func.max(ResumeArtifact.version)).where(ResumeArtifact.opportunity_id==opp.id)) or 0)+1
                # Results are committed atomically with the completed job, so duplicate
                # delivery cannot create a second version for the same job.
                db.add(ResumeArtifact(opportunity_id=opp.id,version=version,input_hash=w.input_hash,input_json={**data,'_claim_validation':audit.pop('claim_certificate',None),'_generation_audit':{k:v for k,v in audit.items() if k!='claim_certificate'}},claims=result['claims'],findings=result['findings'],content_hash=digest(result['claims'])))
            elif kind=='resume_validate':
                a=db.get(ResumeArtifact,data['artifact_id'])
                if a and a.opportunity_id==opp.id and a.version==data['artifact_version'] and a.content_hash==digest(data['claims']):
                    a.input_json={**a.input_json,'_claim_validation':result['certificate']};a.findings=result['findings']
            else:
                from .practice_worker import commit_result
                commit_result(db,w,result)
            w.status='completed';w.error='';w.audit=audit
    except Exception as exc:
        with Session.begin() as db:
            w=db.scalar(select(CareerWorkflow).where(CareerWorkflow.id==wid).with_for_update())
            if not w or w.status!='running' or w.lease_token!=token:return True
            permanent=isinstance(exc,ValueError) or isinstance(exc,GatewayError) and not exc.retryable
            w.status='failed' if permanent or w.attempts>=3 else 'queued'
            w.error=str(exc)[:250] if isinstance(exc,(ValueError,GatewayError)) else 'Processing failed; retry safely'
            w.available_at=time.time()+min(60,2**w.attempts)
            if kind=='requirements':db.get(Opportunity,w.opportunity_id).status=w.status
    return True
