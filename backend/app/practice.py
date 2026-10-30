"""Reviewed reusable answers and grounded asynchronous interview practice."""
import time
from typing import Literal
from fastapi import Depends,HTTPException
from pydantic import BaseModel,Field
from sqlalchemy import select
from .models import Opportunity,Requirement,CareerWorkflow,Application,ArtifactApproval,ResumeArtifact,uid
from .practice_models import ReviewedAnswer,InterviewSession,InterviewResponse
from .career import snapshot,get_opp,enqueue,DraftClaim
from .career_gateway import digest,validate_claims
from .artifact_export import lock_owner

class AnswerRequest(BaseModel):
    question:str=Field(min_length=3,max_length=3000)
class AnswerReview(BaseModel):
    revision:int=Field(ge=0)
    action:Literal['approved','rejected','edited']
    claims:list[DraftClaim]|None=Field(default=None,max_length=20)
class PreparationReview(BaseModel):
    action:Literal['approved','rejected']

class ResponseRequest(BaseModel):
    question_id:str=Field(max_length=36)
    text:str=Field(min_length=1,max_length=10000)


def reviewed_snapshot(db,opp):
    reqs=list(db.scalars(select(Requirement).where(Requirement.opportunity_id==opp.id)))
    if not reqs or any(r.status in ('pending','deferred') for r in reqs):raise HTTPException(409,'Review all requirements before practice')
    data=snapshot(db,opp)
    if not data['requirements'] or not data['facts']:raise HTTPException(409,'Confirm facts and accept requirements before practice')
    return data

def materials_for(db,opp):
    record=db.scalar(select(Application).where(Application.opportunity_id==opp.id))
    if not record:return None
    from .tracking_models import ApplicationTracking
    tracking=db.get(ApplicationTracking,record.id)
    if tracking and tracking.submitted_snapshot:
        submitted=tracking.submitted_snapshot
        artifact=submitted.get('artifact',{})
        return {**artifact,'artifact_id':artifact.get('id'),'status':'submitted_application_materials','job_snapshot':submitted.get('job'),'recorded_at':submitted.get('recorded_at')}
    if not record.current_approval_id:return None
    approval=db.get(ArtifactApproval,record.current_approval_id)
    if not approval or approval.invalidated_reason:return None
    a=db.get(ResumeArtifact,approval.artifact_id)
    if not a:return None
    return {'artifact_id':a.id,'version':a.version,'content_hash':a.content_hash,'claims':a.claims,'evidence':a.input_json['facts'],'status':'approved_application_materials'}

def answer_view(a,key):
    stale=a.input_hash!=key
    return dict(id=a.id,question=a.question,claims=a.claims,evidence=a.input_json['facts'],revision=a.revision,status='needs_review' if stale and a.status=='approved' else a.status,findings=a.findings,stale=stale,history=a.history,approved_hash=a.approved_hash if not stale else '',created_at=a.created_at,generation=a.input_json.get('_generation',{}),validation_pending=any(f.get('code')=='validation_pending' for f in a.findings))

def install(app,current_user,db_session):
    @app.get('/opportunities/{oid}/practice')
    def practice(oid:str,owner=Depends(current_user),db=Depends(db_session)):
        opp=get_opp(db,oid,owner);key=digest(snapshot(db,opp))
        answers=[answer_view(a,key) for a in db.scalars(select(ReviewedAnswer).where(ReviewedAnswer.owner_id==owner,ReviewedAnswer.opportunity_id==oid).order_by(ReviewedAnswer.created_at))]
        sessions=[]
        for s in db.scalars(select(InterviewSession).where(InterviewSession.owner_id==owner,InterviewSession.opportunity_id==oid).order_by(InterviewSession.created_at)):
            responses=[]
            for r in db.scalars(select(InterviewResponse).where(InterviewResponse.session_id==s.id).order_by(InterviewResponse.created_at)):
                w=db.get(CareerWorkflow,r.workflow_id) if r.workflow_id else None
                responses.append(dict(id=r.id,question_id=r.question_id,text=r.text,feedback=r.feedback,status=w.status if w and w.status!='completed' else r.status,created_at=r.created_at))
            sessions.append(dict(id=s.id,status=s.status,questions=s.questions,evidence=s.input_json['snapshot']['facts'],submitted_materials=s.input_json.get('materials'),stale=s.input_hash!=key,responses=responses,created_at=s.created_at,generation=s.input_json.get('generation',{})))
        works=[dict(id=w.id,kind=w.kind,status=w.status,error=w.error) for w in db.scalars(select(CareerWorkflow).where(CareerWorkflow.opportunity_id==oid,CareerWorkflow.kind.in_(['answer_draft','answer_validate','interview_prep','interview_feedback'])).order_by(CareerWorkflow.available_at.desc()))]
        return dict(answers=answers,sessions=sessions,workflows=works)

    @app.get('/answers')
    def all_answers(owner=Depends(current_user),db=Depends(db_session)):
        result=[]
        for a in db.scalars(select(ReviewedAnswer).where(ReviewedAnswer.owner_id==owner).order_by(ReviewedAnswer.created_at.desc())):
            opp=db.get(Opportunity,a.opportunity_id)
            result.append({**answer_view(a,digest(snapshot(db,opp))),'opportunity_id':a.opportunity_id})
        return result

    @app.post('/opportunities/{oid}/answers')
    def draft_answer(oid:str,body:AnswerRequest,owner=Depends(current_user),db=Depends(db_session)):
        lock_owner(db,owner);opp=get_opp(db,oid,owner);data=reviewed_snapshot(db,opp)
        if not body.question.strip():raise HTTPException(422,'Enter an application question')
        w=enqueue(db,opp,'answer_draft',{'snapshot':data,'question':body.question.strip()});db.commit();return {'id':w.id,'status':w.status}

    @app.post('/answers/{aid}/review')
    def review(aid:str,body:AnswerReview,owner=Depends(current_user),db=Depends(db_session)):
        lock_owner(db,owner)
        a=db.scalar(select(ReviewedAnswer).where(ReviewedAnswer.id==aid,ReviewedAnswer.owner_id==owner).with_for_update())
        if not a:raise HTTPException(404,'Answer not found')
        if body.revision!=a.revision:raise HTTPException(409,'Answer changed; refresh before review')
        opp=get_opp(db,a.opportunity_id,owner)
        if body.action=='approved':
            if any(f.get('code')=='validation_pending' for f in a.findings):raise HTTPException(409,'Evidence validation is still pending')
            if a.input_hash!=digest(snapshot(db,opp)):raise HTTPException(409,'Profile or requirements changed; generate a new answer')
            findings=validate_claims(a.claims,a.input_json['facts'],a.input_json.get('_claim_validation'))
            if findings:raise HTTPException(422,{'message':'Unsupported claims block approval','findings':findings})
            a.status='approved';a.approved_hash=digest(a.claims);a.findings=[]
        elif body.action=='edited':
            if body.claims is None:raise HTTPException(422,'Provide answer claims')
            a.history=[*a.history,dict(revision=a.revision,claims=a.claims,status=a.status,approved_hash=a.approved_hash,at=time.time())]
            a.claims=[c.model_dump() for c in body.claims];a.input_json={**a.input_json,'_claim_validation':None};a.findings=validate_claims(a.claims,a.input_json['facts']);a.status='draft';a.approved_hash=''
            from .career_gateway import adapter
            if adapter()=='openai' and a.claims:
                data={k:v for k,v in a.input_json.items() if not k.startswith('_')}
                enqueue(db,opp,'answer_validate',{'snapshot':data,'claims':a.claims,'answer_id':a.id,'revision':a.revision+1})
                a.findings=[{'code':'validation_pending','message':'Edited answer requires AI evidence validation before approval.'}]

        else:a.status='rejected';a.approved_hash=''
        a.revision+=1;db.commit();return {'ok':True,'revision':a.revision,'status':a.status,'findings':a.findings}

    @app.post('/opportunities/{oid}/interviews')
    def prepare(oid:str,owner=Depends(current_user),db=Depends(db_session)):
        lock_owner(db,owner);opp=get_opp(db,oid,owner);data=reviewed_snapshot(db,opp)
        w=enqueue(db,opp,'interview_prep',{'snapshot':data,'materials':materials_for(db,opp)});db.commit();return {'id':w.id,'status':w.status}

    @app.post('/interviews/{sid}/review')
    def review_preparation(sid:str,body:PreparationReview,owner=Depends(current_user),db=Depends(db_session)):
        lock_owner(db,owner)
        session=db.scalar(select(InterviewSession).where(InterviewSession.id==sid,InterviewSession.owner_id==owner).with_for_update())
        if not session:raise HTTPException(404,'Interview session not found')
        opp=get_opp(db,session.opportunity_id,owner)
        if session.input_hash!=digest(snapshot(db,opp)):raise HTTPException(409,'Profile or job changed; prepare a new interview')
        session.status='ready' if body.action=='approved' else 'rejected'
        db.commit();return {'status':session.status}

    @app.post('/interviews/{sid}/responses')
    def respond(sid:str,body:ResponseRequest,owner=Depends(current_user),db=Depends(db_session)):
        lock_owner(db,owner)
        session=db.scalar(select(InterviewSession).where(InterviewSession.id==sid,InterviewSession.owner_id==owner).with_for_update())
        if not session:raise HTTPException(404,'Interview session not found')
        if session.status!='ready':raise HTTPException(409,'Review and approve these questions before responding')
        question=next((q for q in session.questions if q['id']==body.question_id),None)
        if not question:raise HTTPException(422,'Question does not belong to this session')
        if not body.text.strip():raise HTTPException(422,'Enter a response')
        opp=get_opp(db,session.opportunity_id,owner)
        if session.input_hash!=digest(snapshot(db,opp)):raise HTTPException(409,'Profile or job changed; prepare a new interview')
        key=digest({'question_id':body.question_id,'text':body.text.strip()})
        old=db.scalar(select(InterviewResponse).where(InterviewResponse.session_id==sid,InterviewResponse.input_hash==key))
        if old:return {'id':old.id,'workflow_id':old.workflow_id,'duplicate':True}
        response=InterviewResponse(id=uid(),session_id=sid,question_id=body.question_id,text=body.text.strip(),input_hash=key)
        db.add(response);db.flush()
        w=enqueue(db,opp,'interview_feedback',{'snapshot':session.input_json['snapshot'],'session_id':sid,'response_id':response.id,'question':question,'response':response.text})
        response.workflow_id=w.id;db.commit();return {'id':response.id,'workflow_id':w.id,'duplicate':False}
