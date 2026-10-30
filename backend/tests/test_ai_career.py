"""Real SDK with mocked HTTP only. No live API claims."""
import json
import pytest
import httpx2
from openai import OpenAI
from app import career_gateway as g
from app.ai_gateway import GatewayError

FACTS=[{'fact_id':'fact-v1','value':'Used Python to automate monthly reports at Cedar Labs.','source':'Used Python to automate monthly reports at Cedar Labs.','provenance':'source','document_id':'doc','start':0,'end':56}]
CLAIMS=[{'text':'Automated monthly reporting with Python at Cedar Labs.','fact_ids':['fact-v1']}]
SNAP={'facts':FACTS,'requirements':[{'id':'req','text':'Python experience','source':'Python experience'}]}

def mocked(monkeypatch,bodies):
    pending=list(bodies);requests=[]
    def factory(_):
        def send(request):
            requests.append(json.loads(request.content));body=pending.pop(0)
            if isinstance(body,int):return httpx2.Response(body,json={'error':{'message':'PRIVATE_PROVIDER_DETAIL','type':'server_error'}})
            return httpx2.Response(200,json={'id':'resp_test','object':'response','created_at':1,'model':'test-model','status':'completed','output':[{'id':'m','type':'message','role':'assistant','status':'completed','content':[{'type':'output_text','text':json.dumps(body),'annotations':[]}]}],'usage':{'input_tokens':20,'output_tokens':10,'total_tokens':30}})
        return OpenAI(api_key='test-not-real',http_client=httpx2.Client(transport=httpx2.MockTransport(send)),max_retries=0)
    monkeypatch.setenv('EXTRACTION_ADAPTER','openai');monkeypatch.setenv('OPENAI_MODEL','test-model');monkeypatch.setattr(g,'create_client',factory)
    return requests

def verdict(status='supported',quote=None):return {'verdicts':[{'claim_index':0,'status':status,'evidence':[quote or FACTS[0]['value']],'reason':'Meaning preserved.' if status=='supported' else 'Not entailed.'}]}

def test_sdk_paraphrase_verification_and_hash_binding(monkeypatch):
    requests=mocked(monkeypatch,[{'claims':CLAIMS},verdict()])
    claims,findings,audit=g.draft_resume(SNAP)
    cert=audit['claim_certificate']
    assert not findings and not g.validate_claims(claims,FACTS,cert)
    assert g.validate_claims([dict(CLAIMS[0],text='Led a team of engineers.')],FACTS,cert)
    assert g.validate_claims(claims,[dict(FACTS[0],value='Unrelated')],cert)
    assert len(requests)==2 and all(r['store'] is False and 'tools' not in r for r in requests)
    assert requests[1]['text']['format']['name']=='claim_support'

@pytest.mark.parametrize('status',['unsupported','uncertain'])
def test_valid_ids_do_not_mean_supported(monkeypatch,status):
    mocked(monkeypatch,[{'claims':CLAIMS},verdict(status)])
    claims,findings,audit=g.draft_resume(SNAP)
    assert findings and g.validate_claims(claims,FACTS,audit['claim_certificate'])

def test_fabricated_verifier_evidence_fails(monkeypatch):
    mocked(monkeypatch,[verdict(quote='Managed 50 people')])
    with pytest.raises(GatewayError,match='exact cited'):g.verify_claims(CLAIMS,FACTS)

def test_foreign_citation_and_metrics_fail_before_provider(monkeypatch):
    requests=mocked(monkeypatch,[])
    for claim in [{'text':'Python','fact_ids':['foreign']},{'text':'Improved revenue by 80%','fact_ids':['fact-v1']}]:
        cert,findings,_=g.verify_claims([claim],FACTS);assert cert is None and findings
    assert not requests

def test_matching_sdk_and_uncertainty(monkeypatch):
    rows={'items':[{'requirement_id':'req','status':'supported','explanation':'Python use is confirmed.','fact_ids':['fact-v1']}]}
    checked={'items':[{'requirement_id':'req','status':'unknown','explanation':'Evidence does not establish all conditions.','fact_ids':[]}]}
    requests=mocked(monkeypatch,[rows,checked]);items,audit=g.match_requirements(SNAP)
    assert items[0]['status']=='unknown' and audit['adapter']=='openai' and len(requests)==2

@pytest.mark.parametrize('change',['foreign','missing','no_evidence'])
def test_bad_match_output_blocks(monkeypatch,change):
    row={'requirement_id':'req','status':'not_met','explanation':'Claim','fact_ids':['fact-v1']}
    if change=='foreign':row['fact_ids']=['foreign']
    if change=='missing':row['requirement_id']='other'
    if change=='no_evidence':row['fact_ids']=[]
    mocked(monkeypatch,[{'items':[row]},{'items':[row]}])
    with pytest.raises(GatewayError):g.match_requirements(SNAP)

def test_provider_failure_never_falls_back(monkeypatch):
    mocked(monkeypatch,[503])
    with pytest.raises(GatewayError) as error:g.match_requirements(SNAP)
    assert error.value.retryable and 'PRIVATE' not in str(error.value)

def test_edit_revalidation_is_async_and_version_bound(env,monkeypatch):
    from test_profile import client
    from test_career import confirmed,opportunity,draft
    from app import worker
    c=client();confirmed(c);oid=opportunity(c);a=draft(c,oid)
    c.post(f"/artifacts/{a['id']}/approve",json={'version':a['version']})
    original=a['claims'][0];text='Candidate experience: '+original['text']
    edited=c.post(f"/artifacts/{a['id']}/edit",json={'version':a['version'],'claims':[dict(original,text=text)]}).json()
    assert c.post(f"/artifacts/{edited['id']}/approve",json={'version':edited['version']}).status_code==422
    mocked(monkeypatch,[{'verdicts':[{'claim_index':0,'status':'supported','evidence':[original['text']],'reason':'Same factual content.'}]}])
    monkeypatch.setenv('EXTRACTION_ADAPTER','deterministic') # retain fixture snapshot; verifier still uses mocked SDK
    assert worker.run_once()
    assert c.post(f"/artifacts/{edited['id']}/approve",json={'version':edited['version']}).status_code==200
    newer=c.post(f"/artifacts/{edited['id']}/edit",json={'version':edited['version'],'claims':[dict(original,text='Led an engineering team')]}).json()
    assert c.post(f"/artifacts/{newer['id']}/approve",json={'version':newer['version']}).status_code==422
    assert c.post(f"/artifacts/{edited['id']}/approve",json={'version':edited['version']}).status_code==409

from test_profile import env
