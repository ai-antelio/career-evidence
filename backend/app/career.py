"""Owner-scoped job requirements, matching snapshots and reviewable artifacts."""
import time
from typing import Literal
from fastapi import Depends,HTTPException
from pydantic import BaseModel,Field
from sqlalchemy import select,func
from .models import Opportunity,Requirement,CareerWorkflow,MatchRun,ResumeArtifact,Proposal,FactVersion,Application
from .career_gateway import digest,validate_claims,adapter
from .artifact_export import application_for,lock_owner,save_approval,invalidate,artifact_view

def snapshot(db,opp):
    requirements=[dict(id=r.id,text=r.text,kind=r.kind,revision=r.revision,source=r.source) for r in db.scalars(select(Requirement).where(Requirement.opportunity_id==opp.id,Requirement.status.in_(['accepted','corrected'])).order_by(Requirement.start,Requirement.id))]
    rows=db.execute(select(Proposal,FactVersion).join(FactVersion,(FactVersion.proposal_id==Proposal.id)&(FactVersion.version==Proposal.revision)).where(Proposal.owner_id==opp.owner_id,Proposal.status.in_(['accepted','corrected'])).order_by(FactVersion.id)).all()
    facts=[dict(fact_id=f.id,value=f.value,source=p.source,provenance=f.provenance,document_id=p.document_id,start=p.start,end=p.end) for p,f in rows]
    return dict(opportunity_id=opp.id,description=opp.description,revision=opp.revision,requirements=requirements,facts=facts,generation_policy='grounded-v2',generation_adapter=adapter())

def get_opp(db,oid,owner):
    opp=db.scalar(select(Opportunity).where(Opportunity.id==oid,Opportunity.owner_id==owner).with_for_update())
    if not opp: raise HTTPException(404,'Job not found')
    return opp

def enqueue(db,opp,kind,data):
    key=digest(data)
    existing=db.scalar(select(CareerWorkflow).where(CareerWorkflow.opportunity_id==opp.id,CareerWorkflow.kind==kind,CareerWorkflow.input_hash==key))
    if existing:return existing
    w=CareerWorkflow(opportunity_id=opp.id,kind=kind,input_hash=key,input_json=data); db.add(w); db.flush();return w

class NewOpportunity(BaseModel):
    title:str=Field(min_length=1,max_length=200)
    description:str=Field(min_length=3,max_length=30000)
class ReviewRequirement(BaseModel):
    action:Literal['accepted','corrected','rejected','deferred']
    revision:int=Field(ge=0)
    text:str|None=Field(default=None,max_length=3000)
    kind:Literal['required','preferred']|None=None
class DraftClaim(BaseModel):
    text:str=Field(max_length=3000)
    fact_ids:list[str]=Field(max_length=10)
class ArtifactEdit(BaseModel):
    version:int=Field(ge=1)
    claims:list[DraftClaim]=Field(max_length=100)
class Approval(BaseModel):version:int=Field(ge=1)

def install(app,current_user,db_session):
    @app.get('/opportunities')
    def list_jobs(owner=Depends(current_user),db=Depends(db_session)):
        return [dict(id=o.id,title=o.title,status=o.status,revision=o.revision) for o in db.scalars(select(Opportunity).where(Opportunity.owner_id==owner))]

    @app.post('/opportunities',status_code=201)
    def create_job(body:NewOpportunity,owner=Depends(current_user),db=Depends(db_session)):
        if not body.title.strip() or not body.description.strip():raise HTTPException(422,'Title and job description cannot be empty')
        opp=Opportunity(owner_id=owner,title=body.title.strip(),description=body.description.strip());db.add(opp);db.flush()
        application_for(db,opp);enqueue(db,opp,'requirements',{'description':opp.description});db.commit();return {'id':opp.id}

    @app.get('/opportunities/{oid}')
    def detail(oid:str,owner=Depends(current_user),db=Depends(db_session)):
        opp=get_opp(db,oid,owner); current=snapshot(db,opp); key=digest(current)
        reqs=[dict(id=r.id,text=r.text,source=r.source,start=r.start,end=r.end,kind=r.kind,status=r.status,revision=r.revision,provenance='candidate_correction' if r.text!=r.source else 'source_supported') for r in db.scalars(select(Requirement).where(Requirement.opportunity_id==oid).order_by(Requirement.start))]
        workflows=list(db.scalars(select(CareerWorkflow).where(CareerWorkflow.opportunity_id==oid).order_by(CareerWorkflow.available_at.desc())))
        artifact=db.scalar(select(ResumeArtifact).where(ResumeArtifact.opportunity_id==oid).order_by(ResumeArtifact.version.desc()).limit(1))
        visible=[w for w in workflows if w.input_hash==key or (not reqs and w.kind=='requirements') or (w.kind=='resume_validate' and artifact and w.input_json.get('artifact_id')==artifact.id and w.status in ('queued','running','failed'))]
        work=next((w for w in visible if w.status in ('queued','running','failed')),visible[0] if visible else None)
        match=db.scalar(select(MatchRun).where(MatchRun.opportunity_id==oid).order_by(MatchRun.created_at.desc()).limit(1))
        result=dict(id=opp.id,title=opp.title,description=opp.description,status=opp.status,revision=opp.revision,requirements=reqs,
            processing=dict(id=work.id,status=work.status,error=work.error,kind=work.kind) if work else None,
            match=dict(id=match.id,status='stale' if match.input_hash!=key else 'completed',items=match.items,generation=(db.get(CareerWorkflow,match.workflow_id).audit or {})) if match else None,artifact=None)
        app_record=db.scalar(select(Application).where(Application.opportunity_id==opp.id))
        result['application']={'id':app_record.id,'status':app_record.status} if app_record else None
        if artifact:
            stale=artifact.input_hash!=key
            result['artifact']=artifact_view(db,artifact,key)
        return result

    @app.post('/requirements/{rid}/review')
    def review_requirement(rid:str,body:ReviewRequirement,owner=Depends(current_user),db=Depends(db_session)):
        lock_owner(db,owner)
        req=db.scalar(select(Requirement).join(Opportunity).where(Requirement.id==rid,Opportunity.owner_id==owner).with_for_update())
        if not req:raise HTTPException(404,'Requirement not found')
        opp=get_opp(db,req.opportunity_id,owner)
        if req.revision!=body.revision:raise HTTPException(409,'Requirement changed. Refresh before reviewing.')
        if body.action=='corrected':
            if not (body.text or '').strip():raise HTTPException(422,'Corrected requirement cannot be empty')
            req.text=body.text.strip()
        if body.kind is not None:req.kind=body.kind
        req.status=body.action;req.revision+=1;opp.revision+=1;db.commit();return {'ok':True}

    def reviewed(db,opp):
        reqs=list(db.scalars(select(Requirement).where(Requirement.opportunity_id==opp.id)))
        if not reqs or any(r.status in ('pending','deferred') for r in reqs):raise HTTPException(409,'Review all requirements before matching; accept, correct, or reject deferred items')
        data=snapshot(db,opp)
        if not data['requirements']:raise HTTPException(409,'Accept at least one requirement')
        return data

    @app.post('/opportunities/{oid}/match')
    def match_job(oid:str,owner=Depends(current_user),db=Depends(db_session)):
        opp=get_opp(db,oid,owner);data=reviewed(db,opp);work=enqueue(db,opp,'match',data);db.commit();return {'id':work.id,'status':work.status}

    @app.post('/opportunities/{oid}/draft')
    def draft(oid:str,owner=Depends(current_user),db=Depends(db_session)):
        opp=get_opp(db,oid,owner);data=reviewed(db,opp)
        if not data['facts']:raise HTTPException(409,'Confirm career facts before drafting')
        match=db.scalar(select(MatchRun).where(MatchRun.opportunity_id==oid,MatchRun.input_hash==digest(data)))
        if not match:raise HTTPException(409,'Run matching on the current profile and requirements first')
        work=enqueue(db,opp,'draft',data);db.commit();return {'id':work.id,'status':work.status}

    def artifact_for(db,aid,owner):
        lock_owner(db,owner)
        a=db.scalar(select(ResumeArtifact).join(Opportunity).where(ResumeArtifact.id==aid,Opportunity.owner_id==owner).with_for_update())
        if not a:raise HTTPException(404,'Artifact not found')
        opp=get_opp(db,a.opportunity_id,owner)
        latest=db.scalar(select(func.max(ResumeArtifact.version)).where(ResumeArtifact.opportunity_id==opp.id))
        if a.version!=latest:raise HTTPException(409,'A newer résumé version exists; refresh')
        return a,opp

    @app.post('/artifacts/{aid}/edit')
    def edit(aid:str,body:ArtifactEdit,owner=Depends(current_user),db=Depends(db_session)):
        old,opp=artifact_for(db,aid,owner)
        if old.version!=body.version:raise HTTPException(409,'Artifact changed')
        claims=[c.model_dump() for c in body.claims];findings=validate_claims(claims,old.input_json['facts'])
        invalidate(db,opp,'Résumé edited after approval')
        old.status='superseded';old.approved_hash=''
        a=ResumeArtifact(opportunity_id=opp.id,version=old.version+1,input_hash=old.input_hash,input_json={k:v for k,v in old.input_json.items() if k!='_claim_validation'},claims=claims,findings=findings,content_hash=digest(claims));db.add(a);db.flush()
        if findings:enqueue(db,opp,'resume_validate',{'artifact_id':a.id,'artifact_version':a.version,'claims':claims,'facts':a.input_json['facts']})
        db.commit();return {'id':a.id,'version':a.version,'findings':findings}

    @app.post('/artifacts/{aid}/approve')
    def approve(aid:str,body:Approval,owner=Depends(current_user),db=Depends(db_session)):
        a,opp=artifact_for(db,aid,owner)
        if a.version!=body.version:raise HTTPException(409,'Artifact changed')
        if a.input_hash!=digest(snapshot(db,opp)):raise HTTPException(409,'Profile or requirements changed; rerun matching and generate a new draft')
        findings=validate_claims(a.claims,a.input_json['facts'],a.input_json.get('_claim_validation'))
        if findings:raise HTTPException(422,{'message':'Unsupported claims block approval','findings':findings})
        a.findings=[];a.status='approved';a.approved_hash=digest(a.claims)
        record,approval=save_approval(db,opp,a,owner);db.commit();return {'ok':True,'content_hash':a.approved_hash,'application_id':record.id,'approval_id':approval.id}

    @app.post('/workflows/{wid}/retry')
    def retry(wid:str,owner=Depends(current_user),db=Depends(db_session)):
        w=db.scalar(select(CareerWorkflow).join(Opportunity).where(CareerWorkflow.id==wid,Opportunity.owner_id==owner).with_for_update())
        if not w:raise HTTPException(404,'Processing job not found')
        if w.status!='failed':raise HTTPException(409,'Only failed work can be retried')
        w.status='queued';w.attempts=0;w.error='';w.available_at=time.time();db.commit();return {'ok':True}

    from . import artifact_export
    artifact_export.install(app,current_user,db_session,snapshot,get_opp)
