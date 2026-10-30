"""Actual OpenAI SDK with mocked HTTP: never live API verification."""
import json
import pytest
import httpx2
from openai import OpenAI
from app import career_gateway,practice_gateway,worker
from app.ai_gateway import GatewayError
from test_profile import env,client
from test_career import confirmed,opportunity,accept_requirements

FACT={'fact_id':'fact-a','value':'Used Python to automate weekly reports.'}
SNAP={'facts':[FACT],'requirements':[{'id':'req-a','text':'Python experience','source':'Python experience'}]}
CLAIM={'text':'I automated weekly reports using Python.','fact_ids':['fact-a']}
QUESTION={'text':'How did you approach automating weekly reports with Python?','requirement_id':'req-a','fact_ids':['fact-a'],'material_claim_indices':[]}

def provider(monkeypatch,outputs):
    calls=[]
    def respond(request):
        body=json.loads(request.content);calls.append(body)
        task=body['text']['format']['name'];value=outputs[task]
        if isinstance(value,int):return httpx2.Response(value,json={'error':{'message':'SECRET_PROVIDER_MESSAGE'}})
        content=[{'type':'refusal','refusal':'SECRET_REFUSAL'}] if value=='refusal' else [{'type':'output_text','text':json.dumps(value),'annotations':[]}]
        return httpx2.Response(200,json={'id':'resp_test','object':'response','created_at':1,'model':'test-model','status':'completed','output':[{'id':'msg_test','type':'message','role':'assistant','status':'completed','content':content}],'usage':{'input_tokens':12,'output_tokens':8,'total_tokens':20}})
    monkeypatch.setenv('EXTRACTION_ADAPTER','openai');monkeypatch.setenv('OPENAI_MODEL','test-model')
    monkeypatch.setattr(career_gateway,'create_client',lambda factory:OpenAI(api_key='test-not-real',http_client=httpx2.Client(transport=httpx2.MockTransport(respond)),max_retries=0))
    return calls

def verdict(status='supported'):
    return {'verdicts':[{'claim_index':0,'status':status,'evidence':[FACT['value']],'reason':'Supported by supplied passage.' if status=='supported' else 'Inflates the supplied fact.'}]}

def test_sdk_answer_paraphrase_and_evidence_verification(monkeypatch):
    calls=provider(monkeypatch,{'application_answer':{'claims':[CLAIM]},'claim_support':verdict()})
    result,audit=practice_gateway.execute('answer_draft',{'snapshot':SNAP,'question':'Describe your reporting work.'})
    assert result['claims']==[CLAIM] and result['certificate']['method']=='openai_semantic'
    assert audit['adapter']=='openai' and audit['verification']['adapter']=='openai'
    assert [c['text']['format']['name'] for c in calls]==['application_answer','claim_support']
    assert all(c['store'] is False and 'tools' not in c and c['text']['format']['strict'] for c in calls)
    assert not career_gateway.validate_claims(result['claims'],SNAP['facts'],result['certificate'])

@pytest.mark.parametrize('claims,status', [([{'text':'Invented','fact_ids':['foreign']}],'supported'),([{'text':'Led global Python strategy.','fact_ids':['fact-a']}],'unsupported')])
def test_answer_invalid_citations_and_semantic_invention_block(monkeypatch,claims,status):
    provider(monkeypatch,{'application_answer':{'claims':claims},'claim_support':verdict(status)})
    with pytest.raises(GatewayError):practice_gateway.execute('answer_draft',{'snapshot':SNAP,'question':'Experience?'})

def test_sdk_generated_questions_reviewed_independently(monkeypatch):
    calls=provider(monkeypatch,{'interview_preparation':{'questions':[QUESTION]},'interview_question_verification':{'verdicts':[{'question_index':0,'grounded':True}]}})
    result,audit=practice_gateway.execute('interview_prep',{'snapshot':SNAP,'materials':None})
    assert result['questions'][0]['text']==QUESTION['text'] and result['review_required']
    assert len(calls)==2 and audit['verification']['adapter']=='openai'

@pytest.mark.parametrize('question,verdicts', [({**QUESTION,'fact_ids':['foreign']},[]),({**QUESTION,'text':'How did you lead a 100-person team?'},[{'question_index':0,'grounded':False}]),(QUESTION,[{'question_index':1,'grounded':True}])])
def test_questions_fail_closed_on_invented_premise_or_refs(monkeypatch,question,verdicts):
    provider(monkeypatch,{'interview_preparation':{'questions':[question]},'interview_question_verification':{'verdicts':verdicts}})
    with pytest.raises(GatewayError):practice_gateway.execute('interview_prep',{'snapshot':SNAP,'materials':None})

@pytest.mark.parametrize('value,code',[('refusal','refusal'),(503,'provider_error')])
def test_sdk_failures_are_safe_no_fallback(monkeypatch,value,code):
    provider(monkeypatch,{'application_answer':value})
    with pytest.raises(GatewayError) as err:practice_gateway.execute('answer_draft',{'snapshot':SNAP,'question':'Experience?'})
    assert err.value.code==code and 'SECRET' not in str(err.value)

def test_prep_requires_candidate_review_before_response(env,monkeypatch):
    c=client();confirmed(c);oid=opportunity(c);accept_requirements(c,oid)
    monkeypatch.setattr(practice_gateway,'execute',practice_gateway.execute)
    # Use actual task and persistence but deterministic provider stub; explicitly not live.
    original=practice_gateway.execute
    def generate(kind,data):
        result,audit=original(kind,data)
        if kind=='interview_prep':result['review_required']=True;result['generation']={'adapter':'mocked_openai'}
        return result,audit
    monkeypatch.setattr('app.practice_worker.execute',generate)
    c.post(f'/opportunities/{oid}/interviews');worker.run_once()
    s=c.get(f'/opportunities/{oid}/practice').json()['sessions'][0]
    assert s['status']=='needs_review'
    body={'question_id':s['questions'][0]['id'],'text':'My response'}
    assert c.post(f"/interviews/{s['id']}/responses",json=body).status_code==409
    other=client('other-prep@example.test')
    assert other.post(f"/interviews/{s['id']}/review",json={'action':'approved'}).status_code==404
    assert c.post(f"/interviews/{s['id']}/review",json={'action':'approved'}).status_code==200
    assert c.post(f"/interviews/{s['id']}/responses",json=body).status_code==200

def test_answer_edit_revalidates_and_stale_result_cannot_restore_approval(env,monkeypatch):
    from sqlalchemy import select
    from app.models import ReviewedAnswer,CareerWorkflow
    from app.practice_worker import commit_result
    c=client();confirmed(c);oid=opportunity(c);accept_requirements(c,oid)
    c.post(f'/opportunities/{oid}/answers',json={'question':'Describe experience'});worker.run_once()
    a=c.get('/answers').json()[0]
    assert c.post(f"/answers/{a['id']}/review",json={'revision':0,'action':'approved'}).status_code==200
    monkeypatch.setenv('EXTRACTION_ADAPTER','openai')
    edited=[{'text':'Rephrased candidate work','fact_ids':a['claims'][0]['fact_ids']}]
    assert c.post(f"/answers/{a['id']}/review",json={'revision':1,'action':'edited','claims':edited}).status_code==200
    assert c.get('/answers').json()[0]['validation_pending']
    assert c.post(f"/answers/{a['id']}/review",json={'revision':2,'action':'approved'}).status_code==409
    with env() as db:
        task=db.scalar(select(CareerWorkflow).where(CareerWorkflow.kind=='answer_validate'))
        task_id=task.id
    # Change again before old job completes: old proof must not attach.
    newer=[{'text':'Another edit','fact_ids':a['claims'][0]['fact_ids']}]
    assert c.post(f"/answers/{a['id']}/review",json={'revision':2,'action':'edited','claims':newer}).status_code==200
    with env.begin() as db:
        task=db.get(CareerWorkflow,task_id)
        commit_result(db,task,{'claims':edited,'certificate':{'test':'stale'},'findings':[]})
        record=db.get(ReviewedAnswer,a['id'])
        assert record.input_json['_claim_validation'] is None and record.findings
        assert not record.approved_hash
