"""Application tracking, minimal audit trail and retryable account deletion."""
import copy,hashlib,io,json,os,time,zipfile
from pathlib import Path
from datetime import datetime,timezone
from typing import Literal
from fastapi import Depends,HTTPException,Response,Request
from pydantic import BaseModel,Field,field_validator
from sqlalchemy import select,delete,or_
from .db import Base,Session
from .models import User,SessionToken,Document,Application,ArtifactApproval,ResumeArtifact,Opportunity
from .tracking_models import ApplicationTracking,ApplicationEvent,AuditEvent,AccountDeletion
from .artifact_export import lock_owner,approval_reason
from .career_gateway import digest

STATES=Literal['saved','drafting','ready','submitted','interview','offer','rejected','withdrawn']
class TrackingUpdate(BaseModel):
    revision:int=Field(ge=0)
    status:STATES|None=None
    notes:str|None=Field(default=None,max_length=20000)
    next_action:str|None=Field(default=None,max_length=2000)
    follow_up_at:datetime|None=None
    @field_validator('follow_up_at')
    @classmethod
    def aware(cls,v):
        if v is not None and v.tzinfo is None:raise ValueError('Use an ISO timestamp with timezone')
        return v
class DeleteRequest(BaseModel):
    confirmation:Literal['DELETE MY ACCOUNT']


def deletion_pending(db,owner):
    return db.scalar(select(AccountDeletion.id).where(AccountDeletion.owner_id==owner)) is not None

def account_rows(db,owner):
    """Traverse actual declared foreign keys; never select another account's rows."""
    rows={}; excluded={'account_deletion_jobs','dispatch_events'}
    for table in Base.metadata.sorted_tables:
        if table.name in excluded:continue
        clauses=[]
        if table.name=='users':clauses.append(table.c.id==owner)
        for col in table.c:
            if col.name in ('owner_id','actor_id','confirmed_by'):clauses.append(col==owner)
            for fk in col.foreign_keys:
                parents=rows.get(fk.column.table.name,[])
                vals=[r[fk.column.name] for r in parents if r.get(fk.column.name) is not None]
                if vals:clauses.append(col.in_(vals))
        if clauses:rows[table.name]=[dict(r) for r in db.execute(select(table).where(or_(*clauses))).mappings()]
    return rows

def process_deletion_job(job_id,session_factory=None):
    factory=session_factory or Session
    with factory.begin() as db:
        job=db.scalar(select(AccountDeletion).where(AccountDeletion.id==job_id).with_for_update())
        if not job or job.status=='completed':return True
        job.attempts+=1;job.status='running';owner=job.owner_id
        lock_owner(db,owner)
        rows=account_rows(db,owner)
        keys=set(job.storage_keys)
        keys.update(r['storage_key'] for r in rows.get('documents',[]))
        job.storage_keys=sorted(keys)
        # Remove broker work for the user's deleted documents/workflows.
        targets={r['id'] for name,records in rows.items() for r in records if 'id' in r}
        for table in reversed(Base.metadata.sorted_tables):
            if table.name in ('account_deletion_jobs',):continue
            if table.name=='dispatch_events' and 'target_id' in table.c:
                if targets:db.execute(delete(table).where(table.c.target_id.in_(targets)))
                continue
            records=rows.get(table.name,[])
            if not records:continue
            pks=list(table.primary_key.columns)
            # All current data entities have single-column primary keys.
            if len(pks)!=1:raise RuntimeError('Unsupported deletion key shape')
            db.execute(delete(table).where(pks[0].in_([r[pks[0].name] for r in records])))
        job.status='files_pending'
    try:
        root=Path(os.getenv('STORAGE_ROOT','./private-storage')).resolve()
        with factory() as db:keys=list(db.get(AccountDeletion,job_id).storage_keys)
        for key in keys:
            if Path(key).name!=key:raise ValueError('Invalid storage key')
            (root/key).unlink(missing_ok=True)
        with factory.begin() as db:
            job=db.get(AccountDeletion,job_id);job.status='completed';job.error='';job.storage_keys=[];job.owner_id=None;job.completed_at=time.time()
        return True
    except Exception:
        with factory.begin() as db:
            job=db.get(AccountDeletion,job_id);job.status='files_pending';job.error='Private file cleanup requires retry'
        raise RuntimeError('Private file cleanup requires retry') from None


def install(app,current_user,db_session):
    from .career import snapshot
    def owned(db,appid,owner):
        row=db.scalar(select(Application).where(Application.id==appid,Application.owner_id==owner))
        if not row:raise HTTPException(404,'Application not found')
        return row
    def view(db,row):
        t=db.get(ApplicationTracking,row.id)
        return dict(application_id=row.id,revision=t.revision if t else 0,status=t.status if t else ('drafting' if row.status=='needs_review' else row.status),notes=t.notes if t else '',next_action=t.next_action if t else '',follow_up_at=t.follow_up_at if t else None,submitted_snapshot=t.submitted_snapshot if t else None,history=[dict(id=e.id,kind=e.kind,status=e.status,note=e.note,created_at=e.created_at) for e in db.scalars(select(ApplicationEvent).where(ApplicationEvent.application_id==row.id).order_by(ApplicationEvent.created_at,ApplicationEvent.id))])

    @app.get('/applications/{appid}/tracking')
    def get_tracking(appid:str,owner=Depends(current_user),db=Depends(db_session)):
        return view(db,owned(db,appid,owner))

    @app.post('/applications/{appid}/tracking')
    def update_tracking(appid:str,body:TrackingUpdate,owner=Depends(current_user),db=Depends(db_session)):
        lock_owner(db,owner);row=owned(db,appid,owner);t=db.get(ApplicationTracking,row.id)
        if not t:t=ApplicationTracking(application_id=row.id,status='drafting' if row.status=='needs_review' else row.status,revision=0);db.add(t);db.flush()
        if t.revision!=body.revision:raise HTTPException(409,'Application changed; refresh before saving')
        if body.status=='submitted' and t.submitted_snapshot is None:
            opp=db.get(Opportunity,row.opportunity_id);approval=db.get(ArtifactApproval,row.current_approval_id) if row.current_approval_id else None
            artifact=db.get(ResumeArtifact,approval.artifact_id) if approval else None
            reason=approval_reason(db,artifact,approval,digest(snapshot(db,opp))) if artifact else 'Approve a résumé before recording submission'
            if reason:raise HTTPException(409,reason)
            t.submitted_snapshot=copy.deepcopy(dict(job={'id':opp.id,'title':opp.title,'description':opp.description,'requirements':artifact.input_json.get('requirements',[])},artifact={'id':artifact.id,'version':artifact.version,'content_hash':artifact.content_hash,'claims':artifact.claims,'evidence':artifact.input_json['facts']},approval_id=approval.id,recorded_at=time.time()))
        if body.status is not None:t.status=body.status
        if body.notes is not None:t.notes=body.notes
        if body.next_action is not None:t.next_action=body.next_action
        if 'follow_up_at' in body.model_fields_set:t.follow_up_at=body.follow_up_at.astimezone(timezone.utc).isoformat() if body.follow_up_at else None
        t.revision+=1
        db.add(ApplicationEvent(application_id=row.id,kind='status' if body.status else 'update',status=t.status,note=body.notes or ''))
        db.flush();result=view(db,row);db.commit();return result

    @app.get('/account/audit')
    def get_audit(owner=Depends(current_user),db=Depends(db_session)):
        return [dict(id=e.id,action=e.action,resource=e.resource,status_code=e.status_code,created_at=e.created_at) for e in db.scalars(select(AuditEvent).where(AuditEvent.owner_id==owner).order_by(AuditEvent.created_at.desc()).limit(500))]

    @app.get('/account/export')
    def export_account(owner=Depends(current_user),db=Depends(db_session)):
        lock_owner(db,owner);rows=account_rows(db,owner);payload={};files={};root=Path(os.getenv('STORAGE_ROOT','./private-storage'))
        for name,records in rows.items():
            if name in ('sessions','broker_outbox','outbox_events'):continue
            payload[name]=[]
            for r in records:
                clean={k:v for k,v in r.items() if k not in ('password_hash','token_hash','lease_token','file_bytes','storage_key')}
                payload[name].append(clean)
                if name=='artifact_exports':files[f"exports/{r['id']}.{r['format']}"]=r['file_bytes']
                if name=='documents':
                    key=r['storage_key']
                    if Path(key).name!=key:raise HTTPException(409,'Invalid storage reference')
                    try:files[f"documents/{r['id']}/{Path(r['filename']).name}"]=(root/key).read_bytes()
                    except FileNotFoundError:raise HTTPException(409,'A source file is unavailable; export cannot be completed')
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:
            z.writestr('account.json',json.dumps(payload,ensure_ascii=False,indent=2))
            for name,data in files.items():z.writestr(name,data)
        return Response(stream.getvalue(),media_type='application/zip',headers={'Content-Disposition':'attachment; filename="career-account-export.zip"','Cache-Control':'private, no-store'})

    @app.post('/account/delete',status_code=202)
    def delete_account(body:DeleteRequest,response:Response,owner=Depends(current_user),db=Depends(db_session)):
        lock_owner(db,owner)
        job=db.scalar(select(AccountDeletion).where(AccountDeletion.owner_id==owner))
        if not job:
            job=AccountDeletion(owner_id=owner,storage_keys=list(db.scalars(select(Document.storage_key).where(Document.owner_id==owner))));db.add(job);db.flush()
            from .outbox import enqueue
            enqueue(db,'deletion',job.id)
        db.execute(delete(SessionToken).where(SessionToken.owner_id==owner));db.commit();response.delete_cookie('career_session')
        return {'id':job.id,'status':job.status,'message':'Signed out. Account and private-file deletion queued.'}

    @app.middleware('http')
    async def audit_mutations(request:Request,call_next):
        # Audit metadata only, never bodies, cookies, credentials or query strings.
        owner=None
        if request.method=='POST' or request.url.path=='/account/export':
            with __import__('app.main',fromlist=['Session']).Session() as db:
                token=request.cookies.get('career_session','')
                s=db.get(SessionToken,hashlib.sha256(token.encode()).hexdigest()) if token else None
                if s and s.expires>time.time():owner=s.owner_id
        response=await call_next(request)
        if owner:
            # Reuse the request transaction: an early-return endpoint may still
            # hold a User FOR UPDATE lock until yield-dependency cleanup. Opening
            # another transaction here deadlocks its audit FK against that lock.
            db=getattr(request.state,'database_session',None)
            if db is not None:
                # End any residual read/error transaction. Mutation endpoints
                # explicitly commit before returning; never commit their pending
                # changes merely as a side effect of recording audit metadata.
                db.rollback()
                if db.get(User,owner):
                    route=request.scope.get('route');path=getattr(route,'path','unknown')
                    db.add(AuditEvent(owner_id=owner,action=request.method+' '+path,resource=path,status_code=response.status_code))
                db.commit()
        return response


def recover_deletions(db,now):
    from .outbox import enqueue
    from .queue_models import DispatchEvent
    jobs=db.scalars(select(AccountDeletion).where(AccountDeletion.status.in_(['queued','running','files_pending'])).with_for_update(skip_locked=True)).all()
    count=0
    for job in jobs:
        backoff=max(60,min(3600,2**min(job.attempts,12)))
        recent=db.scalar(select(DispatchEvent.id).where(DispatchEvent.topic=='deletion',DispatchEvent.target_id==job.id,or_(DispatchEvent.status=='pending',DispatchEvent.published_at>now-backoff)).limit(1))
        if not recent:enqueue(db,'deletion',job.id);count+=1
    return count
