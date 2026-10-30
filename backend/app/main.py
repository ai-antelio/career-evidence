import hashlib, os, secrets, time
from pathlib import Path
from typing import Literal
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from fastapi import FastAPI, Request, Response, HTTPException, UploadFile, Depends
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from .db import Session
from .models import User, SessionToken, Document, Job, Proposal, FactVersion, ReviewEvent, uid
from .extraction import inspect_file

from .limits import RequestLimit
from difflib import SequenceMatcher

if os.getenv('APP_ENV', 'development') != 'development':
    raise RuntimeError('This slice uses local auth and storage. Production mode is intentionally disabled pending managed identity, object storage and scanning integration.')

app = FastAPI(title='Career Evidence API', version='0.1.0')
app.add_middleware(RequestLimit)
ORIGIN = os.getenv('WEB_ORIGIN', 'http://localhost:3000')
app.add_middleware(CORSMiddleware, allow_origins=[ORIGIN], allow_credentials=True, allow_methods=['GET','POST'], allow_headers=['Content-Type'])
hasher = PasswordHasher()

def db_session(request: Request):
    with Session() as db:
        request.state.database_session=db
        yield db

def current_user(request: Request, db=Depends(db_session)):
    token = request.cookies.get('career_session', '')
    session = db.get(SessionToken, hashlib.sha256(token.encode()).hexdigest())
    if not session or session.expires <= time.time(): raise HTTPException(401, 'Sign in required')
    from .tracking import deletion_pending
    if deletion_pending(db,session.owner_id): raise HTTPException(401, 'Account deletion is pending')
    return session.owner_id

@app.middleware('http')
async def same_origin(request, call_next):
    if request.method not in ('GET','HEAD','OPTIONS') and request.headers.get('origin') != ORIGIN:
        return JSONResponse({'detail':'Origin not allowed'}, status_code=403)
    return await call_next(request)

class Credentials(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=12, max_length=128)

@app.post('/auth/{action}')
def auth(action: Literal['signup','signin'], body: Credentials, response: Response, db=Depends(db_session)):
    if os.getenv('AUTH_MODE', 'local') != 'local': raise HTTPException(503, 'Managed identity adapter is not configured')
    email = body.email.strip().lower()
    if '@' not in email or ' ' in email: raise HTTPException(422, 'Enter a valid email')
    user = db.scalar(select(User).where(User.email == email))
    if action == 'signup':
        if user: raise HTTPException(409, 'Account cannot be created with these details')
        user = User(email=email, password_hash=hasher.hash(body.password)); db.add(user)
        try: db.flush()
        except IntegrityError: db.rollback(); raise HTTPException(409, 'Account cannot be created with these details')
    else:
        try:
            if not user or not hasher.verify(user.password_hash, body.password): raise HTTPException(401, 'Invalid credentials')
        except (VerifyMismatchError, InvalidHashError): raise HTTPException(401, 'Invalid credentials')
    from .tracking import deletion_pending
    if deletion_pending(db,user.id): raise HTTPException(403, 'Account deletion is pending')
    token = secrets.token_urlsafe(32)
    db.add(SessionToken(token_hash=hashlib.sha256(token.encode()).hexdigest(), owner_id=user.id, expires=time.time()+86400))
    from .tracking_models import AuditEvent
    db.add(AuditEvent(owner_id=user.id,action='POST /auth/'+action,resource='account',status_code=200))
    db.commit()
    response.set_cookie('career_session', token, httponly=True, secure=os.getenv('COOKIE_SECURE','false') == 'true', samesite='lax', max_age=86400)
    return {'id':user.id,'email':user.email}

@app.get('/me')
def me(owner=Depends(current_user), db=Depends(db_session)):
    user = db.get(User, owner); return {'id':owner,'email':user.email}

@app.post('/logout')
def logout(request: Request, response: Response, owner=Depends(current_user), db=Depends(db_session)):
    token = db.get(SessionToken, hashlib.sha256(request.cookies['career_session'].encode()).hexdigest())
    db.delete(token); db.commit(); response.delete_cookie('career_session'); return {'ok':True}

@app.post('/documents', status_code=201)
async def upload(file: UploadFile, owner=Depends(current_user), db=Depends(db_session)):
    data = await file.read(5*1024*1024+1)
    if len(data) > 5*1024*1024: raise HTTPException(413, 'Maximum upload size is 5 MB')
    filename = Path(file.filename or '').name[:200]
    try: inspect_file(data, filename)
    except Exception: raise HTTPException(422, 'Upload a valid text-based PDF or DOCX under the expansion limit')
    digest = hashlib.sha256(data).hexdigest()
    existing = db.scalar(select(Document).where(Document.owner_id == owner, Document.digest == digest))
    if existing: return {'id':existing.id,'duplicate':True}
    root = Path(os.getenv('STORAGE_ROOT','./private-storage')); root.mkdir(parents=True, exist_ok=True, mode=0o700)
    key = uid(); path = root / key
    try:
        with path.open('xb') as f:
            os.chmod(path,0o600); f.write(data)
        doc = Document(owner_id=owner, filename=filename, digest=digest, storage_key=key)
        db.add(doc); db.flush(); db.add(Job(document_id=doc.id)); db.commit()
    except IntegrityError:
        db.rollback(); path.unlink(missing_ok=True)
        existing = db.scalar(select(Document).where(Document.owner_id == owner, Document.digest == digest))
        if not existing: raise HTTPException(503, 'Upload could not be saved; retry')
        return {'id':existing.id,'duplicate':True}
    except Exception:
        db.rollback(); path.unlink(missing_ok=True); raise HTTPException(503, 'Upload could not be saved; retry')
    return {'id':doc.id,'duplicate':False}

@app.get('/documents')
def documents(owner=Depends(current_user), db=Depends(db_session)):
    rows = db.execute(select(Document, Job).join(Job, Job.document_id == Document.id).where(Document.owner_id == owner)).all()
    return [dict(id=d.id, filename=d.filename, status=d.status, error=j.error, attempts=j.attempts) for d,j in rows]

@app.post('/documents/{document_id}/retry')
def retry(document_id: str, owner=Depends(current_user), db=Depends(db_session)):
    doc = db.scalar(select(Document).where(Document.id == document_id, Document.owner_id == owner).with_for_update())
    if not doc: raise HTTPException(404, 'Document not found')
    job = db.scalar(select(Job).where(Job.document_id == doc.id).with_for_update())
    if job.status != 'failed': raise HTTPException(409, 'Only failed processing can be retried')
    job.status = 'queued'; job.attempts = 0; job.available_at = time.time(); job.error = ''; doc.status = 'queued'; db.commit()
    return {'ok':True}

@app.get('/proposals')
def proposals(owner=Depends(current_user), db=Depends(db_session)):
    items = db.scalars(select(Proposal).where(Proposal.owner_id == owner).order_by(Proposal.document_id, Proposal.start)).all()
    result = []
    for p in items:
        # Singleton fields conflict; free-text statements are never automatically reconciled.
        conflicts = [q.id for q in items if q.id != p.id and q.category == p.category and q.value.casefold() != p.value.casefold() and (p.category == 'email' or SequenceMatcher(None, p.value.casefold(), q.value.casefold()).ratio() > 0.82) and q.status != 'rejected']
        latest = db.scalar(select(FactVersion).where(FactVersion.proposal_id == p.id).order_by(FactVersion.version.desc()).limit(1))
        result.append(dict(id=p.id, document_id=p.document_id, value=p.value, category=p.category, source=p.source, start=p.start, end=p.end, status=p.status, revision=p.revision, conflicts=conflicts, structured_fields=p.structured_fields, extraction_adapter=p.extraction_adapter, current_value=latest.value if latest else None, provenance=latest.provenance if latest else None))
    return result

class Review(BaseModel):
    action: Literal['accepted','corrected','rejected','deferred']
    value: str | None = Field(default=None, max_length=3000)
    revision: int = Field(ge=0)

@app.post('/proposals/{proposal_id}/review')
def review(proposal_id: str, body: Review, owner=Depends(current_user), db=Depends(db_session)):
    from .artifact_export import lock_owner
    lock_owner(db,owner)
    p = db.scalar(select(Proposal).where(Proposal.id == proposal_id, Proposal.owner_id == owner).with_for_update())
    if not p: raise HTTPException(404, 'Proposal not found')
    if p.revision != body.revision: raise HTTPException(409, 'This proposal changed. Refresh before reviewing.')
    if body.action == 'corrected' and not (body.value or '').strip(): raise HTTPException(422, 'A correction cannot be empty')
    value = body.value.strip() if body.action == 'corrected' else p.value
    changed = db.execute(update(Proposal).where(Proposal.id == p.id, Proposal.revision == body.revision).values(status=body.action, revision=body.revision+1))
    if changed.rowcount != 1: db.rollback(); raise HTTPException(409, 'Proposal changed')
    if body.action in ('accepted','corrected'):
        db.add(FactVersion(owner_id=owner, proposal_id=p.id, version=body.revision+1, value=value, provenance='candidate_correction' if body.action == 'corrected' else 'source_supported', confirmed_by=owner))
    db.add(ReviewEvent(proposal_id=p.id, actor_id=owner, action=body.action)); db.commit()
    return {'ok':True}

@app.get('/profile')
def profile(owner=Depends(current_user), db=Depends(db_session)):
    rows = db.execute(select(Proposal, FactVersion).join(FactVersion, (FactVersion.proposal_id == Proposal.id) & (FactVersion.version == Proposal.revision)).where(Proposal.owner_id == owner, Proposal.status.in_(['accepted','corrected']))).all()
    return [dict(id=f.id, value=f.value, provenance=f.provenance, independently_verified=False, proposal_id=p.id, version=f.version) for p,f in rows]

from .career import install as install_career
install_career(app,current_user,db_session)

from .practice import install as install_practice
install_practice(app,current_user,db_session)

from .tracking import install as install_tracking
install_tracking(app,current_user,db_session)
