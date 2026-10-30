import pytest
from sqlalchemy import select,func
from test_profile import env,client
from test_career import confirmed,opportunity,accept_requirements,draft
from app import worker,practice_gateway
from app.models import CareerWorkflow,ReviewedAnswer,InterviewSession,InterviewResponse
from app.ai_gateway import GatewayError

def setup(c):
    confirmed(c);oid=opportunity(c);accept_requirements(c,oid);return oid

def practice(c,oid):return c.get(f'/opportunities/{oid}/practice').json()

def test_answer_review_reuse_and_invalidation(env):
    c=client();oid=setup(c)
    first=c.post(f'/opportunities/{oid}/answers',json={'question':'Describe your Python experience'}).json()
    assert c.post(f'/opportunities/{oid}/answers',json={'question':'Describe your Python experience'}).json()['id']==first['id']
    worker.run_once();a=practice(c,oid)['answers'][0]
    assert a['evidence'] and not a['findings']
    assert c.post(f"/answers/{a['id']}/review",json={'revision':0,'action':'approved'}).status_code==200
    assert c.get('/answers').json()[0]['status']=='approved'
    claims=a['claims'];claims[0]['text']='Invented qualification'
    assert c.post(f"/answers/{a['id']}/review",json={'revision':1,'action':'edited','claims':claims}).status_code==200
    a=practice(c,oid)['answers'][0]
    assert not a['approved_hash'] and a['history'][0]['status']=='approved'
    assert c.post(f"/answers/{a['id']}/review",json={'revision':2,'action':'approved'}).status_code==422
    assert c.post(f"/answers/{a['id']}/review",json={'revision':0,'action':'rejected'}).status_code==409

def test_interview_response_feedback_history(env):
    c=client();oid=setup(c)
    r=c.post(f'/opportunities/{oid}/interviews');assert r.status_code==200
    worker.run_once();s=practice(c,oid)['sessions'][0];assert s['questions'] and s['evidence']
    body={'question_id':s['questions'][0]['id'],'text':'I would explain a real example and clearly distinguish my contribution.'}
    r=c.post(f"/interviews/{s['id']}/responses",json=body);assert r.status_code==200
    assert c.post(f"/interviews/{s['id']}/responses",json=body).json()['duplicate']
    worker.run_once();s=practice(c,oid)['sessions'][0];response=s['responses'][0]
    assert response['status']=='completed' and response['feedback']['observations'][0]['quote'] in body['text']
    assert response['feedback']['adapter']=='deterministic'
    before=len(c.get('/profile').json())
    assert c.post(f"/interviews/{s['id']}/responses",json={'question_id':s['questions'][0]['id'],'text':'I invented 10 qualifications'}).status_code==200
    worker.run_once();assert len(c.get('/profile').json())==before

def test_practice_isolation_and_stale_inputs(env):
    c=client();oid=setup(c);c.post(f'/opportunities/{oid}/interviews');worker.run_once()
    c.post(f'/opportunities/{oid}/answers',json={'question':'Describe experience'});worker.run_once()
    p=practice(c,oid);a=p['answers'][0];s=p['sessions'][0]
    b=client('other-practice@example.test')
    assert b.get(f'/opportunities/{oid}/practice').status_code==404
    assert b.get('/answers').json()==[]
    assert b.post(f"/answers/{a['id']}/review",json={'revision':0,'action':'approved'}).status_code==404
    assert b.post(f"/interviews/{s['id']}/responses",json={'question_id':s['questions'][0]['id'],'text':'foreign'}).status_code==404
    f=c.get('/proposals').json()[0]
    c.post(f"/proposals/{f['id']}/review",json={'revision':f['revision'],'action':'rejected'})
    assert practice(c,oid)['sessions'][0]['stale']
    assert c.post(f"/answers/{a['id']}/review",json={'revision':0,'action':'approved'}).status_code==409
    assert c.post(f"/interviews/{s['id']}/responses",json={'question_id':s['questions'][0]['id'],'text':'Response'}).status_code==409

def test_practice_requires_reviewed_profile(env):
    c=client();oid=opportunity(c)
    assert c.post(f'/opportunities/{oid}/interviews').status_code==409
    accept_requirements(c,oid)
    assert c.post(f'/opportunities/{oid}/answers',json={'question':'Experience?'}).status_code==409

def test_mocked_ai_invalid_citations_block_atomic_result(env,monkeypatch):
    c=client();oid=setup(c);monkeypatch.setenv('EXTRACTION_ADAPTER','openai')
    monkeypatch.setattr(practice_gateway,'structured_call',lambda *args:({'choices':[{'requirement_id':'foreign','fact_ids':[]}]},{'adapter':'openai'}))
    c.post(f'/opportunities/{oid}/interviews');worker.run_once()
    p=practice(c,oid);assert p['sessions']==[] and p['workflows'][0]['status']=='failed'
    monkeypatch.setattr(practice_gateway,'structured_call',lambda *args:({'claims':[{'text':'Invented','fact_ids':['foreign']}]},{'adapter':'openai'}))
    c.post(f'/opportunities/{oid}/answers',json={'question':'What experience?'});worker.run_once()
    assert practice(c,oid)['answers']==[]

def test_feedback_rejects_nonresponse_quotes_and_false_fact_links(env,monkeypatch):
    c=client();oid=setup(c);c.post(f'/opportunities/{oid}/interviews');worker.run_once()
    s=practice(c,oid)['sessions'][0];fid=s['evidence'][0]['fact_id']
    monkeypatch.setenv('EXTRACTION_ADAPTER','openai')
    # This fixture switches provider modes to isolate feedback validation; refresh
    # its stored policy snapshot explicitly rather than bypass production staleness.
    from app.career import snapshot
    from app.career_gateway import digest
    from app.models import Opportunity
    with env.begin() as db:
        session=db.get(InterviewSession,s['id']);snap=snapshot(db,db.get(Opportunity,oid))
        session.input_json={**session.input_json,'snapshot':snap};session.input_hash=digest(snap)
    monkeypatch.setattr(practice_gateway,'structured_call',lambda *args:({'observations':[{'code':'result','quote':'not in response','fact_ids':[]}]},{'adapter':'openai'}))
    c.post(f"/interviews/{s['id']}/responses",json={'question_id':s['questions'][0]['id'],'text':'A response'});worker.run_once()
    p=practice(c,oid);assert p['sessions'][0]['responses'][0]['feedback']=={}
    assert p['sessions'][0]['responses'][0]['status']=='failed'
    monkeypatch.setattr(practice_gateway,'structured_call',lambda *args:({'observations':[{'code':'result','quote':'A different response','fact_ids':[fid]}]},{'adapter':'openai'}))
    c.post(f"/interviews/{s['id']}/responses",json={'question_id':s['questions'][0]['id'],'text':'A different response'});worker.run_once()
    assert all(r['feedback']=={} for r in practice(c,oid)['sessions'][0]['responses'])

def test_practice_provider_failure_retry(env,monkeypatch):
    c=client();oid=setup(c);c.post(f'/opportunities/{oid}/interviews')
    original=practice_gateway.execute
    def fail(*args):raise GatewayError('refusal','Provider refused',retryable=False)
    monkeypatch.setattr('app.practice_worker.execute',fail);worker.run_once()
    p=practice(c,oid);assert not p['sessions'] and p['workflows'][0]['status']=='failed'
    monkeypatch.setattr('app.practice_worker.execute',original)
    assert c.post('/workflows/'+p['workflows'][0]['id']+'/retry').status_code==200
    worker.run_once();assert len(practice(c,oid)['sessions'])==1

def test_preparation_contains_approved_materials(env):
    c=client();confirmed(c);oid=opportunity(c);a=draft(c,oid)
    c.post(f"/artifacts/{a['id']}/approve",json={'version':a['version']})
    c.post(f'/opportunities/{oid}/interviews');worker.run_once()
    m=practice(c,oid)['sessions'][0]['submitted_materials']
    assert m['artifact_id']==a['id'] and m['claims']==a['claims'] and m['evidence']

def test_submitted_snapshot_precedes_later_approval(env):
    from app.tracking_models import ApplicationTracking
    from app.models import Application
    c=client();confirmed(c);oid=opportunity(c);a=draft(c,oid)
    c.post(f"/artifacts/{a['id']}/approve",json={'version':a['version']})
    with env.begin() as db:
        app=db.scalar(select(Application).where(Application.opportunity_id==oid))
        t=db.get(ApplicationTracking,app.id)
        if t is None:t=ApplicationTracking(application_id=app.id);db.add(t)
        t.submitted_snapshot={'artifact':{'id':a['id'],'version':1,'content_hash':a['content_hash'],'claims':a['claims'],'evidence':a['evidence']},'job':{'id':oid,'description':'Recorded job'},'recorded_at':123}
    c.post(f'/opportunities/{oid}/interviews');worker.run_once()
    m=practice(c,oid)['sessions'][0]['submitted_materials']
    assert m['status']=='submitted_application_materials' and m['recorded_at']==123
