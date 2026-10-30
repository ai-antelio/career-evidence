from sqlalchemy import select
from .models import Opportunity
from .practice_models import ReviewedAnswer,InterviewSession,InterviewResponse
from .practice_gateway import execute
from .career_gateway import digest

def commit_result(db,w,result):
    data=w.input_json;opp=db.get(Opportunity,w.opportunity_id)
    if opp is None:return
    if w.kind=='answer_draft':
        if not db.scalar(select(ReviewedAnswer.id).where(ReviewedAnswer.workflow_id==w.id)):
            db.add(ReviewedAnswer(owner_id=opp.owner_id,opportunity_id=opp.id,workflow_id=w.id,question=data['question'],claims=result['claims'],input_json={**data['snapshot'],'_claim_validation':result.get('certificate'),'_generation':result.get('generation',{})},input_hash=digest(data['snapshot'])))
    elif w.kind=='answer_validate':
        a=db.get(ReviewedAnswer,data['answer_id'])
        if a and a.owner_id==opp.owner_id and a.revision==data['revision'] and a.claims==data['claims']:
            a.input_json={**a.input_json,'_claim_validation':result.get('certificate')}
            a.findings=result.get('findings',[])
    elif w.kind=='interview_prep':
        if not db.scalar(select(InterviewSession.id).where(InterviewSession.workflow_id==w.id)):
            db.add(InterviewSession(owner_id=opp.owner_id,opportunity_id=opp.id,workflow_id=w.id,input_hash=digest(data['snapshot']),input_json={**data,'generation':result.get('generation',{'adapter':result.get('adapter','deterministic')})},questions=result['questions'],status='needs_review' if result.get('review_required') else 'ready'))
    elif w.kind=='interview_feedback':
        r=db.get(InterviewResponse,data['response_id'])
        if r and r.workflow_id==w.id:r.feedback=result;r.status='completed'
