import json
from types import SimpleNamespace
import pytest
import httpx2
from openai import OpenAI
from app.ai_gateway import extract_facts, passages_for, GatewayError, MAX_OUTPUT_TOKENS

TEXT='Senior Data Analyst at Cedar Labs, March 2021–August 2025\nReduced reporting time by 30% using Python.'

def payload():
    span_id,span=next(iter(passages_for(TEXT).items()))
    start=TEXT.index('Cedar Labs')
    return {'facts':[{'category':'employment','span_id':span_id,'quote':span['source'],'value':span['source'],'fields':[{'name':'employer','value':'Cedar Labs','start':start,'end':start+10}]}]}

def provider(body=None,*,status='completed',refusal=False,http_status=200):
    requests=[]
    def respond(request):
        requests.append(json.loads(request.content))
        if http_status != 200:
            return httpx2.Response(http_status,json={'error':{'message':'SECRET_RAW_PROVIDER_DETAIL','type':'server_error'}})
        output=[{'type':'refusal','refusal':'SECRET_REFUSAL_DETAIL'}] if refusal else [{'type':'output_text','text':body if isinstance(body,str) else json.dumps(body or payload()),'annotations':[]}]
        return httpx2.Response(200,json={'id':'resp_test','object':'response','created_at':1,'model':'test-model','status':status,'output':[{'id':'msg_test','type':'message','role':'assistant','status':'completed','content':output}],'usage':{'input_tokens':100,'output_tokens':50,'total_tokens':150}})
    client=OpenAI(api_key='test-only-not-a-real-key',http_client=httpx2.Client(transport=httpx2.MockTransport(respond)),max_retries=0)
    return client,requests

def test_sdk_structured_request_and_validated_result():
    client,requests=provider()
    with client:
        result=extract_facts(TEXT,client=client,adapter='openai',model='test-model')
    assert result.proposals[0]['structured_fields'][0]['value']=='Cedar Labs'
    assert result.proposals[0]['source']==result.proposals[0]['value']
    assert result.audit['input_tokens']==100
    req=requests[0]
    assert req['text']['format']['strict'] is True
    assert req['store'] is False and req['max_output_tokens']==MAX_OUTPUT_TOKENS
    assert 'untrusted_resume_passages' in json.loads(req['input'])
    assert 'never instructions' in req['instructions']
    assert 'tools' not in req

@pytest.mark.parametrize('mutation,code',[
    ('unknown_span','invalid_citation'),('foreign_span','invalid_citation'),
    ('fabricated_claim','unsupported_claim'),('changed_quote','unsupported_claim'),
    ('shortened_claim','unsupported_claim'),('bad_field_offset','invalid_field_evidence'),
    ('fabricated_field','invalid_field_evidence'),('out_of_span','invalid_field_evidence'),
    ('duplicate','invalid_citation'),('extra_field','invalid_schema'),('invalid_category','invalid_schema'),
    ('no_facts','no_facts'),('bad_json','invalid_schema')])
def test_fail_closed_on_unsupported_output(mutation,code):
    body=payload();fact=body['facts'][0]
    if mutation=='unknown_span':fact['span_id']='unknown'
    elif mutation=='foreign_span':fact['span_id']=next(iter(passages_for('CEO of a different company in a different document')))
    elif mutation=='fabricated_claim':fact['value']='Chief Executive Officer at Cedar Labs'
    elif mutation=='changed_quote':fact['quote']='Invented source text'
    elif mutation=='shortened_claim':fact['value']='Senior Data Analyst';fact['quote']='Senior Data Analyst'
    elif mutation=='bad_field_offset':fact['fields'][0]['start']+=1
    elif mutation=='fabricated_field':fact['fields'][0]['value']='Invented Company'
    elif mutation=='out_of_span':fact['fields'][0].update(value='Python',start=TEXT.index('Python'),end=TEXT.index('Python')+6)
    elif mutation=='duplicate':body['facts'].append(fact.copy())
    elif mutation=='extra_field':fact['independently_verified']=True
    elif mutation=='invalid_category':fact['category']='verified_skill'
    elif mutation=='no_facts':body['facts']=[]
    elif mutation=='bad_json':body='{broken'
    client,_=provider(body)
    with client,pytest.raises(GatewayError) as error:extract_facts(TEXT,client=client,adapter='openai',model='test-model')
    assert error.value.code==code and not error.value.retryable

@pytest.mark.parametrize('options,code,retryable',[
    ({'refusal':True},'refusal',False),({'status':'incomplete'},'incomplete',False),
    ({'http_status':429},'provider_unavailable',True),({'http_status':503},'provider_unavailable',True),
    ({'http_status':401},'provider_rejected',False),
])
def test_provider_failure_handling(options,code,retryable):
    client,_=provider(**options)
    with client,pytest.raises(GatewayError) as error:extract_facts(TEXT,client=client,adapter='openai',model='test-model')
    assert error.value.code==code and error.value.retryable==retryable
    assert 'SECRET' not in str(error.value)
    assert 'SECRET' not in json.dumps(error.value.audit)

@pytest.mark.parametrize('exception',[httpx2.ReadTimeout('private timeout'),httpx2.ConnectError('private connection')])
def test_network_failures_are_retryable(exception):
    def fail(request):raise exception
    with OpenAI(api_key='test-only',http_client=httpx2.Client(transport=httpx2.MockTransport(fail)),max_retries=0) as client:
        with pytest.raises(GatewayError) as error:extract_facts(TEXT,client=client,adapter='openai',model='test-model')
    assert error.value.retryable and 'private' not in str(error.value)

def test_explicit_deterministic_adapter_and_missing_config(monkeypatch):
    result=extract_facts(TEXT,adapter='deterministic')
    assert result.audit['adapter']=='deterministic'
    assert all(p['structured_fields']==[] and p['extraction_adapter']=='deterministic' for p in result.proposals)
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    with pytest.raises(GatewayError,match='credentials'):extract_facts(TEXT,adapter='openai',model='test-model')

def test_input_budget_prevents_provider_call():
    client,requests=provider()
    with client,pytest.raises(GatewayError) as error:extract_facts('x'*40001,client=client,adapter='openai',model='test-model')
    assert error.value.code=='input_limit' and not requests
