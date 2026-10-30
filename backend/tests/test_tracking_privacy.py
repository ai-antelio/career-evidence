import io,json,zipfile,os
from pathlib import Path
from sqlalchemy import select,func
from test_profile import env,client
from test_artifact_export import setup,export
from app import tracking
from app.models import User,Document,Application
from app.tracking_models import AccountDeletion

def test_tracking_history_conflicts_and_submitted_snapshot(env):
 c=client();oid,a,approval=setup(c);path='/applications/'+approval['application_id']+'/tracking'
 assert c.get(path).json()['revision']==0
 r=c.post(path,json={'revision':0,'status':'submitted','notes':'Applied on employer website','next_action':'Prepare interview','follow_up_at':'2026-11-03T12:00:00-06:00'})
 assert r.status_code==200,r.text
 t=r.json();assert t['submitted_snapshot']['artifact']['id']==a['id'];assert t['follow_up_at']=='2026-11-03T18:00:00+00:00'
 assert c.post(path,json={'revision':0,'status':'offer'}).status_code==409
 c.post('/artifacts/'+a['id']+'/edit',json={'version':1,'claims':list(reversed(a['claims']))})
 t2=c.post(path,json={'revision':1,'status':'interview','notes':'Interview scheduled'}).json()
 assert t2['submitted_snapshot']==t['submitted_snapshot'];assert len(t2['history'])==2
 detail=c.get('/applications/'+approval['application_id']).json();assert detail['status']=='interview' and detail['artifact_status']=='needs_review'
 assert c.get('/applications').json()[0]['status']=='interview'
 b=client('other@example.test');assert b.get(path).status_code==404;assert b.post(path,json={'revision':2,'status':'offer'}).status_code==404
 assert c.post(path,json={'revision':2,'follow_up_at':'2026-11-03T12:00:00'}).status_code==422

def test_account_export_excludes_secrets_isolation_and_includes_files(env):
 c=client();oid,a,approval=setup(c);export(c,a);other=client('other@example.test')
 r=c.get('/account/export');assert r.status_code==200
 with zipfile.ZipFile(io.BytesIO(r.content)) as z:
  data=z.read('account.json').decode();j=json.loads(data)
  assert 'password_hash' not in data and 'token_hash' not in data and 'lease_token' not in data
  assert 'other@example.test' not in data
  assert len(j['users'])==1 and j['users'][0]['email']=='alex@example.test'
  assert any(p.startswith('documents/') for p in z.namelist());assert any(p.endswith('.docx') and p.startswith('exports/') for p in z.namelist())
 audits=c.get('/account/audit').json();assert any(x['action']=='GET /account/export' for x in audits)
 assert all('synthetic-passphrase' not in str(x) for x in audits)
 assert all(x['action']=='POST /auth/signup' for x in other.get('/account/audit').json())

def test_delete_revokes_access_purges_files_and_data_and_retries(env):
 c=client();oid,a,approval=setup(c);export(c,a);b=client('other@example.test')
 with env() as db:owner=db.scalar(select(User).where(User.email=='alex@example.test')).id;keys=list(db.scalars(select(Document.storage_key).where(Document.owner_id==owner)))
 assert c.post('/account/delete',json={'confirmation':'yes'}).status_code==422
 r=c.post('/account/delete',json={'confirmation':'DELETE MY ACCOUNT'});assert r.status_code==202,r.text
 assert c.get('/me').status_code==401
 assert c.post('/auth/signin',json={'email':'alex@example.test','password':'synthetic-passphrase-2026'}).status_code==403
 jid=r.json()['id'];assert tracking.process_deletion_job(jid,env);assert tracking.process_deletion_job(jid,env)
 with env() as db:
  assert db.get(User,owner) is None;job=db.get(AccountDeletion,jid);assert job.status=='completed' and job.owner_id is None and job.storage_keys==[]
  assert db.scalar(select(func.count()).select_from(Application))==0
  assert db.scalar(select(func.count()).select_from(User))==1
 assert all(not (Path(os.environ['STORAGE_ROOT'])/k).exists() for k in keys)
 assert b.get('/me').status_code==200

def test_delete_filesystem_failure_is_durable_and_retryable(env,monkeypatch):
 c=client();setup(c);jid=c.post('/account/delete',json={'confirmation':'DELETE MY ACCOUNT'}).json()['id'];unlink=Path.unlink
 def fail(*args,**kwargs):raise OSError('synthetic failure')
 monkeypatch.setattr(Path,'unlink',fail)
 import pytest
 with pytest.raises(RuntimeError):tracking.process_deletion_job(jid,env)
 with env() as db:
  job=db.get(AccountDeletion,jid);assert job.status=='files_pending' and job.storage_keys
  assert db.scalar(select(func.count()).select_from(User))==0
 monkeypatch.setattr(Path,'unlink',unlink);assert tracking.process_deletion_job(jid,env)

def test_deletion_recovery_deduplicates_pending_dispatch(env):
 from app.queue_models import DispatchEvent
 import time
 c=client();setup(c);jid=c.post('/account/delete',json={'confirmation':'DELETE MY ACCOUNT'}).json()['id']
 with env.begin() as db:
  assert tracking.recover_deletions(db,time.time())==0
  event=db.scalar(select(DispatchEvent).where(DispatchEvent.topic=='deletion'));event.status='published';event.published_at=time.time()-3601
 with env.begin() as db:
  assert tracking.recover_deletions(db,time.time())==1
 with env.begin() as db:assert tracking.recover_deletions(db,time.time())==0

def test_submission_requires_valid_approval_and_privacy_requires_auth(env):
 from fastapi.testclient import TestClient
 from app.main import app
 from test_career import confirmed,opportunity,draft
 c=client();confirmed(c);oid=opportunity(c);a=draft(c,oid)
 apps=c.get('/applications').json();path='/applications/'+apps[0]['id']+'/tracking'
 assert c.post(path,json={'revision':0,'status':'submitted'}).status_code==409
 anonymous=TestClient(app,headers={'Origin':'http://localhost:3000'})
 assert anonymous.get('/account/export').status_code==401
 assert anonymous.get('/account/audit').status_code==401
 assert anonymous.post('/account/delete',json={'confirmation':'DELETE MY ACCOUNT'}).status_code==401
 assert c.post('/account/delete',headers={'Origin':'https://evil.example'},json={'confirmation':'DELETE MY ACCOUNT'}).status_code==403

def test_privacy_covers_practice_and_pending_work(env):
 from app import worker
 from app.models import InterviewSession,InterviewResponse,ReviewedAnswer,CareerWorkflow
 from app.queue_models import DispatchEvent
 from test_practice import practice
 c=client();oid,a,approval=setup(c)
 c.post(f'/opportunities/{oid}/interviews');worker.run_once()
 s=practice(c,oid)['sessions'][0]
 c.post(f"/interviews/{s['id']}/responses",json={'question_id':s['questions'][0]['id'],'text':'I describe my own contribution.'});worker.run_once()
 c.post(f'/opportunities/{oid}/answers',json={'question':'Experience?'});worker.run_once()
 r=c.get('/account/export')
 with zipfile.ZipFile(io.BytesIO(r.content)) as z:
  rows=json.loads(z.read('account.json'));assert rows['interview_sessions'] and rows['interview_responses'] and rows['reviewed_answers']
 jid=c.post('/account/delete',json={'confirmation':'DELETE MY ACCOUNT'}).json()['id'];tracking.process_deletion_job(jid,env)
 with env() as db:
  for cls in [InterviewSession,InterviewResponse,ReviewedAnswer,CareerWorkflow]:assert db.scalar(select(func.count()).select_from(cls))==0
  assert all(x.topic=='deletion' for x in db.scalars(select(DispatchEvent)))
 assert not worker.run_once()

def test_tracking_conflicting_edits_postgres(env):
 import pytest,threading
 if not os.getenv('TEST_DATABASE_URL'):pytest.skip('PostgreSQL concurrency')
 c=client();oid,a,approval=setup(c);path='/applications/'+approval['application_id']+'/tracking';results=[]
 threads=[threading.Thread(target=lambda s=s:results.append(c.post(path,json={'revision':0,'status':s}))) for s in ['interview','withdrawn']]
 for t in threads:t.start()
 for t in threads:t.join(10)
 assert sorted(r.status_code for r in results)==[200,409]
 assert len(c.get(path).json()['history'])==1

def test_audit_error_rolls_back_pending_write_and_releases_owner_lock(env):
 from fastapi import Depends,HTTPException
 from app import main
 # A regression endpoint emulates an error after a locked uncommitted change.
 # Audit must not open a second transaction blocked by that lock, or commit it.
 path='/_test/audit-rollback'
 if not any(getattr(r,'path',None)==path for r in main.app.routes):
  @main.app.post(path)
  def rollback_probe(owner=Depends(main.current_user),db=Depends(main.db_session)):
   user=db.scalar(select(User).where(User.id==owner).with_for_update())
   user.email='must-not-persist@example.test'
   db.flush()
   raise HTTPException(409,'Synthetic conflict')
 c=client();result=c.post(path);assert result.status_code==409
 assert c.get('/me').json()['email']=='alex@example.test'
 events=c.get('/account/audit').json()
 assert any(e['action']=='POST '+path and e['status_code']==409 for e in events)
