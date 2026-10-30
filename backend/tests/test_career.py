import time
import pytest
from sqlalchemy import select,func
from test_profile import env,client,upload
from app import worker,career_worker
from app.models import CareerWorkflow,Requirement,MatchRun,ResumeArtifact
from app.career_gateway import validate_claims,assess,extract_requirements
from app.ai_gateway import GatewayError

def confirmed(c):
    upload(c);assert worker.run_once()
    for p in c.get('/proposals').json():
        assert c.post(f"/proposals/{p['id']}/review",json={'action':'accepted','revision':0}).status_code==200

def opportunity(c,text='Python\nSQL\nFive years of experience with Python'):
    r=c.post('/opportunities',json={'title':'Data analyst','description':text});assert r.status_code==201
    oid=r.json()['id'];assert worker.run_once();return oid

def accept_requirements(c,oid):
    for r in c.get(f'/opportunities/{oid}').json()['requirements']:
        assert c.post(f"/requirements/{r['id']}/review",json={'action':'accepted','revision':r['revision']}).status_code==200

def draft(c,oid):
    accept_requirements(c,oid)
    assert c.post(f'/opportunities/{oid}/match').status_code==200;assert worker.run_once()
    assert c.post(f'/opportunities/{oid}/draft').status_code==200;assert worker.run_once()
    return c.get(f'/opportunities/{oid}').json()['artifact']

def test_end_to_end(env):
    c=client();confirmed(c);oid=opportunity(c)
    assert c.post(f'/opportunities/{oid}/match').status_code==409
    a=draft(c,oid);detail=c.get(f'/opportunities/{oid}').json()
    assert [x['status'] for x in detail['match']['items']]==['supported','unknown','partial']
    assert detail['match']['items'][0]['evidence'][0]['source']
    assert not a['findings'] and a['evidence']
    assert c.post(f"/artifacts/{a['id']}/approve",json={'version':a['version']}).status_code==200

def test_requirement_correction_defer_and_source(env):
    c=client();oid=opportunity(c,'Python required')
    req=c.get(f'/opportunities/{oid}').json()['requirements'][0]
    assert c.post(f"/requirements/{req['id']}/review",json={'action':'deferred','revision':0}).status_code==200
    assert c.post(f'/opportunities/{oid}/match').status_code==409
    assert c.post(f"/requirements/{req['id']}/review",json={'action':'accepted','revision':0}).status_code==409
    assert c.post(f"/requirements/{req['id']}/review",json={'action':'corrected','revision':1,'text':'SQL','kind':'preferred'}).status_code==200
    after=c.get(f'/opportunities/{oid}').json()['requirements'][0]
    assert after['source']=='Python required' and after['text']=='SQL' and after['kind']=='preferred'

def test_cross_account_routes_and_fact_injection(env):
    a=client();confirmed(a);oid=opportunity(a);art=draft(a,oid)
    b=client('b@example.test')
    assert b.get('/opportunities').json()==[]
    assert b.get(f'/opportunities/{oid}').status_code==404
    assert b.post(f'/opportunities/{oid}/match').status_code==404
    assert b.post(f"/artifacts/{art['id']}/approve",json={'version':1}).status_code==404
    req=a.get(f'/opportunities/{oid}').json()['requirements'][0]
    assert b.post(f"/requirements/{req['id']}/review",json={'revision':1,'action':'accepted'}).status_code==404
    claims=[{'text':'Invented claim','fact_ids':['foreign-fact-id']}]
    edited=a.post(f"/artifacts/{art['id']}/edit",json={'version':1,'claims':claims}).json()
    assert edited['findings'][0]['code']=='invalid_citation'
    assert a.post(f"/artifacts/{edited['id']}/approve",json={'version':2}).status_code==422

def test_unsupported_edits_empty_draft_and_approval_invalidation(env):
    c=client();confirmed(c);oid=opportunity(c);a=draft(c,oid)
    assert c.post(f"/artifacts/{a['id']}/approve",json={'version':1}).status_code==200
    claims=a['claims'];claims[0]['text']='Increased revenue by 300%'
    edit=c.post(f"/artifacts/{a['id']}/edit",json={'version':1,'claims':claims}).json()
    assert edit['findings'][0]['code']=='unsupported_claim'
    assert c.post(f"/artifacts/{a['id']}/approve",json={'version':1}).status_code==409
    assert c.post(f"/artifacts/{edit['id']}/approve",json={'version':2}).status_code==422
    empty=c.post(f"/artifacts/{edit['id']}/edit",json={'version':2,'claims':[]}).json()
    assert empty['findings'][0]['code']=='empty'

def test_fact_review_changes_make_snapshot_stale(env):
    c=client();confirmed(c);oid=opportunity(c);a=draft(c,oid)
    p=c.get('/proposals').json()[0]
    assert c.post(f"/proposals/{p['id']}/review",json={'action':'rejected','revision':p['revision']}).status_code==200
    detail=c.get(f'/opportunities/{oid}').json()
    assert detail['artifact']['stale'] and detail['match']['status']=='stale'
    assert c.post(f"/artifacts/{a['id']}/approve",json={'version':1}).status_code==409

def test_only_confirmed_current_facts_are_used(env):
    c=client();upload(c);worker.run_once()
    ps=c.get('/proposals').json()
    p=ps[0];c.post(f"/proposals/{p['id']}/review",json={'action':'corrected','value':'Candidate confirmed current wording','revision':0})
    oid=opportunity(c);a=draft(c,oid)
    assert a['claims']==[{'text':'Candidate confirmed current wording','fact_ids':[c.get('/profile').json()[0]['id']]}]
    assert a['evidence'][0]['provenance']=='candidate_correction'
    assert a['evidence'][0]['source']!=a['claims'][0]['text']

def test_duplicate_commands_and_processing(env):
    c=client();confirmed(c);oid=opportunity(c);accept_requirements(c,oid)
    first=c.post(f'/opportunities/{oid}/match').json();again=c.post(f'/opportunities/{oid}/match').json()
    assert first['id']==again['id'];worker.run_once();assert not worker.run_once()
    with env() as db:assert db.scalar(select(func.count()).select_from(MatchRun))==1
    c.post(f'/opportunities/{oid}/draft');c.post(f'/opportunities/{oid}/draft');worker.run_once()
    with env() as db:assert db.scalar(select(func.count()).select_from(ResumeArtifact))==1

def test_failure_retry_and_expired_lease(env,monkeypatch):
    c=client();r=c.post('/opportunities',json={'title':'Job','description':'Python'});oid=r.json()['id']
    original=career_worker.extract_requirements
    monkeypatch.setattr(career_worker,'extract_requirements',lambda _: (_ for _ in ()).throw(GatewayError('bad','Synthetic provider failure')))
    worker.run_once();d=c.get(f'/opportunities/{oid}').json();assert d['processing']['status']=='failed'
    b=client('other@example.test');assert b.post(f"/workflows/{d['processing']['id']}/retry").status_code==404
    assert c.post(f"/workflows/{d['processing']['id']}/retry").status_code==200
    monkeypatch.setattr(career_worker,'extract_requirements',original)
    with env.begin() as db:
        w=db.scalar(select(CareerWorkflow));w.status='running';w.lease_until=time.time()-1;w.lease_token='crashed'
    assert worker.run_once();assert len(c.get(f'/opportunities/{oid}').json()['requirements'])==1

def test_matching_conservative_statuses():
    req={'id':'r','text':'Python'}
    assert assess(req,[])['status']=='unknown'
    fact={'fact_id':'f','value':'I have no experience with Python','source':'','provenance':'candidate_correction'}
    assert assess(req,[fact])['status']=='not_met'
    positive={**fact,'fact_id':'g','value':'Used Python for reporting'}
    assert assess(req,[positive])['status']=='supported'
    assert assess(req,[fact,positive])['status']=='partial'
    assert assess({'id':'r','text':'Five years of Python management'},[positive])['status']=='partial'

def test_openai_requirement_citation_validation(monkeypatch):
    from app import career_gateway
    monkeypatch.setenv('EXTRACTION_ADAPTER','openai')
    monkeypatch.setattr(career_gateway,'structured_call',lambda *a:({'requirements':[{'text':'Python','source':'Python','start':0,'end':6,'kind':'required'}]},{}))
    assert extract_requirements('Python')[0][0]['text']=='Python'
    monkeypatch.setattr(career_gateway,'structured_call',lambda *a:({'requirements':[{'text':'Kubernetes','source':'Python','start':0,'end':6,'kind':'required'}]},{}))
    with pytest.raises(GatewayError):extract_requirements('Python')

def test_skill_mentions_and_unrelated_negatives_do_not_overclaim():
    base={'fact_id':'f','source':'','provenance':'source_supported'}
    assert assess({'id':'r','text':'Python'},[{**base,'value':'Attended a Python conference'}])['status']=='partial'
    assert assess({'id':'r','text':'Python'},[{**base,'value':'No experience in Excel; used Python daily'}])['status']=='partial'
    assert assess({'id':'r','text':'Proficiency in Python'},[{**base,'value':'Used Python once'}])['status']=='partial'

def test_openai_draft_unsupported_output_stays_blocked(monkeypatch):
    from app import career_gateway
    monkeypatch.setenv('EXTRACTION_ADAPTER','openai')
    snapshot={'facts':[{'fact_id':'f','value':'Used Python','source':'Used Python','provenance':'source_supported'}],'requirements':[]}
    monkeypatch.setattr(career_gateway,'structured_call',lambda *a:({'claims':[{'text':'Managed 100 engineers','fact_ids':['f']}]},{}))
    claims,findings,audit=career_gateway.draft_resume(snapshot)
    assert findings[0]['code']=='unsupported_claim'

def test_corrected_requirement_keeps_attribution_after_accept(env):
    c=client();oid=opportunity(c,'Python')
    r=c.get(f'/opportunities/{oid}').json()['requirements'][0]
    for action,revision,extra in [('corrected',0,{'text':'SQL'}),('deferred',1,{}),('accepted',2,{})]:
        assert c.post(f"/requirements/{r['id']}/review",json={'action':action,'revision':revision,**extra}).status_code==200
    r=c.get(f'/opportunities/{oid}').json()['requirements'][0]
    assert r['provenance']=='candidate_correction' and r['source']=='Python' and r['text']=='SQL'

def test_plans_and_recruiting_mentions_are_not_skill_evidence():
    base={'fact_id':'f','source':'','provenance':'source_supported'}
    for value in ['I plan to learn Python','Managed recruitment of Python developers','I want to use Python','Looking for a role using Python']:
        assert assess({'id':'r','text':'Python'},[{**base,'value':value}])['status']=='partial'

def test_concurrent_workflow_claims_on_postgres(env,monkeypatch):
    import os,threading
    if not os.getenv('TEST_DATABASE_URL'):pytest.skip('PostgreSQL row-lock concurrency check')
    c=client();oid=c.post('/opportunities',json={'title':'Role','description':'Python'}).json()['id']
    started=threading.Event();release=threading.Event();original=career_worker.extract_requirements
    def blocked(text):
        started.set();assert release.wait(5);return original(text)
    monkeypatch.setattr(career_worker,'extract_requirements',blocked)
    results=[]
    t=threading.Thread(target=lambda:results.append(career_worker.run_once(env)));t.start();assert started.wait(5)
    assert not career_worker.run_once(env)
    release.set();t.join(5);assert results==[True]
    assert len(c.get(f'/opportunities/{oid}').json()['requirements'])==1

def test_stale_workflow_completion_cannot_overwrite_new_lease(env,monkeypatch):
    c=client();oid=c.post('/opportunities',json={'title':'Role','description':'Python'}).json()['id']
    original=career_worker.extract_requirements
    def superseded(text):
        with env.begin() as db:
            w=db.scalar(select(CareerWorkflow));w.lease_token='replacement';w.status='queued';w.available_at=time.time()-1
        return original(text)
    monkeypatch.setattr(career_worker,'extract_requirements',superseded)
    assert career_worker.run_once(env)
    with env() as db:assert db.scalar(select(func.count()).select_from(Requirement))==0
    monkeypatch.setattr(career_worker,'extract_requirements',original)
    assert career_worker.run_once(env)
    assert len(c.get(f'/opportunities/{oid}').json()['requirements'])==1
