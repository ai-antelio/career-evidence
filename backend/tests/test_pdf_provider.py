import hashlib, io, logging
import pytest
from sqlalchemy import select, func
from pypdf import PdfReader
from test_profile import env, client
from test_artifact_export import setup
from app.models import ArtifactExport
from app.pdf_export import render_pdf, normalized_text
from app import artifact_export, ai_gateway, career_gateway, provider_config

def pdf(c,a):
    return c.post('/artifacts/'+a['id']+'/export',json={'version':a['version'],'content_hash':a['content_hash'],'format':'pdf'})

def test_pdf_export_selectable_approved_text_isolated_and_repeatable(env):
    c=client();oid,a,approval=setup(c)
    r=pdf(c,a);assert r.status_code==200 and r.headers['content-type']=='application/pdf'
    text='\n'.join(p.extract_text() for p in PdfReader(io.BytesIO(r.content)).pages)
    assert normalized_text(text)==normalized_text('\n'.join(x['text'] for x in a['claims']))
    assert r.headers['x-artifact-content-hash']==a['content_hash']
    assert r.headers['x-file-sha256']==hashlib.sha256(r.content).hexdigest()
    assert pdf(c,a).content==r.content
    assert pdf(client('foreign@example.test'),a).status_code==404
    c.post('/artifacts/'+a['id']+'/edit',json={'version':a['version'],'claims':list(reversed(a['claims']))})
    assert pdf(c,a).status_code==409

def test_pdf_and_docx_separate_cache_and_invalid_format(env):
    c=client();oid,a,approval=setup(c)
    assert pdf(c,a).status_code==200
    assert c.post('/artifacts/'+a['id']+'/export',json={'version':1,'content_hash':a['content_hash']}).status_code==200
    assert c.post('/artifacts/'+a['id']+'/export',json={'version':1,'content_hash':a['content_hash'],'format':'html'}).status_code==422
    with env() as db:assert db.scalar(select(func.count()).select_from(ArtifactExport))==2

def test_pdf_failure_rolls_back_and_recovers(env,monkeypatch):
    c=client();oid,a,approval=setup(c);real=artifact_export.render_pdf
    monkeypatch.setattr(artifact_export,'render_pdf',lambda _: (_ for _ in ()).throw(ValueError('bad renderer')))
    assert pdf(c,a).status_code==503
    with env() as db:assert db.scalar(select(func.count()).select_from(ArtifactExport))==0
    monkeypatch.setattr(artifact_export,'render_pdf',real);assert pdf(c,a).status_code==200

def test_pdf_unicode_markup_wrapping_and_missing_glyph():
    claims=[{'text':'José García — Engineer <Python> & SQL. Improved delivery by 12%.'}, {'text':'Worked with PostgreSQL and FastAPI. '*120}]
    data=render_pdf(claims);pages=PdfReader(io.BytesIO(data)).pages
    assert len(pages)>1
    assert normalized_text('\n'.join(p.extract_text() for p in pages))==normalized_text('\n'.join(c['text'] for c in claims))
    with pytest.raises(ValueError):render_pdf([{'text':'unsupported \U0001F9D1'}])

def test_provider_secret_file_and_fixed_endpoint(tmp_path,monkeypatch,caplog):
    key='sk-synthetic-never-real';path=tmp_path/'secret';path.write_text(key)
    monkeypatch.setenv('OPENAI_API_KEY_FILE',str(path));monkeypatch.setenv('OPENAI_BASE_URL','https://not-allowed.example')
    seen={}
    def factory(**kwargs):seen.update(kwargs);return object()
    provider_config.create_client(factory)
    assert seen['api_key']==key and seen['base_url']=='https://api.openai.com/v1'
    assert not any(key in rec.message for rec in caplog.records)
    assert logging.getLogger('openai').disabled

def test_invalid_configuration_never_copied_to_audit(monkeypatch):
    key='sk-synthetic-secret';monkeypatch.setenv('OPENAI_MODEL',key)
    with pytest.raises(ai_gateway.GatewayError) as e:ai_gateway.extract_facts('Used Python',adapter='openai')
    assert key not in str(e.value) and key not in str(e.value.audit)

def test_missing_secret_file_has_safe_error(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY_FILE','/tmp/nonexistent-career-provider-key')
    monkeypatch.setenv('OPENAI_MODEL','test-model')
    with pytest.raises(ai_gateway.GatewayError) as e:career_gateway.structured_call('test',career_gateway.ResumeOutput,{},'test')
    assert e.value.code=='configuration' and '/tmp/' not in str(e.value)
