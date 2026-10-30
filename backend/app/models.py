import time, uuid
from sqlalchemy import String, Text, Float, Integer, ForeignKey, UniqueConstraint, JSON, LargeBinary
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

def uid(): return str(uuid.uuid4())
class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
class SessionToken(Base):
    __tablename__ = 'sessions'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    expires: Mapped[float] = mapped_column(Float)
class Document(Base):
    __tablename__ = 'documents'
    __table_args__ = (UniqueConstraint('owner_id','digest'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    filename: Mapped[str] = mapped_column(Text)
    digest: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default='queued')
    parser_version: Mapped[str] = mapped_column(String(40), default='paragraph-v1')
    text: Mapped[str] = mapped_column(Text, default='')
class Job(Base):
    __tablename__ = 'outbox_jobs'
    __table_args__ = (UniqueConstraint('document_id'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    document_id: Mapped[str] = mapped_column(ForeignKey('documents.id'))
    status: Mapped[str] = mapped_column(String(30), default='queued')
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[float] = mapped_column(Float, default=time.time)
    lease_until: Mapped[float] = mapped_column(Float, default=0)
    lease_token: Mapped[str] = mapped_column(String(36), default='')
    error: Mapped[str] = mapped_column(Text, default='')
class Proposal(Base):
    __tablename__ = 'fact_proposals'
    __table_args__ = (UniqueConstraint('document_id','start'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    document_id: Mapped[str] = mapped_column(ForeignKey('documents.id'))
    value: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(40))
    structured_fields: Mapped[list] = mapped_column(JSON, default=list)
    extraction_adapter: Mapped[str] = mapped_column(String(30), default='deterministic')
    source: Mapped[str] = mapped_column(Text)
    start: Mapped[int] = mapped_column(Integer)
    end: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default='pending')
    revision: Mapped[int] = mapped_column(Integer, default=0)
class FactVersion(Base):
    __tablename__ = 'fact_versions'
    __table_args__ = (UniqueConstraint('proposal_id','version'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    proposal_id: Mapped[str] = mapped_column(ForeignKey('fact_proposals.id'))
    version: Mapped[int] = mapped_column(Integer)
    value: Mapped[str] = mapped_column(Text)
    provenance: Mapped[str] = mapped_column(String(40))
    confirmed_by: Mapped[str] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
class ReviewEvent(Base):
    __tablename__ = 'review_events'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    proposal_id: Mapped[str] = mapped_column(ForeignKey('fact_proposals.id'))
    actor_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    action: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[float] = mapped_column(Float, default=time.time)

class GenerationRun(Base):
    __tablename__ = 'generation_runs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    document_id: Mapped[str] = mapped_column(ForeignKey('documents.id'), index=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    job_id: Mapped[str] = mapped_column(ForeignKey('outbox_jobs.id'))
    status: Mapped[str] = mapped_column(String(30))
    error_code: Mapped[str] = mapped_column(String(50), default='')
    metadata_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)

class Opportunity(Base):
    __tablename__ = 'opportunities'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default='queued')
    revision: Mapped[int] = mapped_column(Integer, default=0)
class Requirement(Base):
    __tablename__ = 'job_requirements'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey('opportunities.id'), index=True)
    text: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)
    start: Mapped[int] = mapped_column(Integer)
    end: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(20), default='required')
    status: Mapped[str] = mapped_column(String(20), default='pending')
    revision: Mapped[int] = mapped_column(Integer, default=0)
class CareerWorkflow(Base):
    __tablename__ = 'career_workflows'
    __table_args__ = (UniqueConstraint('opportunity_id','kind','input_hash'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey('opportunities.id'), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    input_hash: Mapped[str] = mapped_column(String(64))
    input_json: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30), default='queued', index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[float] = mapped_column(Float, default=time.time, index=True)
    lease_until: Mapped[float] = mapped_column(Float, default=0)
    lease_token: Mapped[str] = mapped_column(String(36), default='')
    error: Mapped[str] = mapped_column(Text, default='')
    audit: Mapped[dict] = mapped_column(JSON, default=dict)
class MatchRun(Base):
    __tablename__ = 'match_runs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey('opportunities.id'), index=True)
    workflow_id: Mapped[str] = mapped_column(ForeignKey('career_workflows.id'), unique=True)
    input_hash: Mapped[str] = mapped_column(String(64))
    items: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
class ResumeArtifact(Base):
    __tablename__ = 'resume_artifacts'
    __table_args__ = (UniqueConstraint('opportunity_id','version'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey('opportunities.id'), index=True)
    version: Mapped[int] = mapped_column(Integer)
    input_hash: Mapped[str] = mapped_column(String(64))
    input_json: Mapped[dict] = mapped_column(JSON)
    claims: Mapped[list] = mapped_column(JSON)
    findings: Mapped[list] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30), default='draft')
    content_hash: Mapped[str] = mapped_column(String(64))
    approved_hash: Mapped[str] = mapped_column(String(64), default='')
    created_at: Mapped[float] = mapped_column(Float, default=time.time)

class Application(Base):
    __tablename__ = 'applications'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey('opportunities.id'), unique=True)
    status: Mapped[str] = mapped_column(String(30), default='drafting')
    current_approval_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)

class ArtifactApproval(Base):
    __tablename__ = 'artifact_approvals'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    application_id: Mapped[str] = mapped_column(ForeignKey('applications.id'), index=True)
    artifact_id: Mapped[str] = mapped_column(ForeignKey('resume_artifacts.id'), unique=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    content_hash: Mapped[str] = mapped_column(String(64))
    input_hash: Mapped[str] = mapped_column(String(64))
    approved_at: Mapped[float] = mapped_column(Float, default=time.time)
    invalidated_reason: Mapped[str] = mapped_column(Text, default='')

class ArtifactExport(Base):
    __tablename__ = 'artifact_exports'
    __table_args__ = (UniqueConstraint('approval_id','format'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    approval_id: Mapped[str] = mapped_column(ForeignKey('artifact_approvals.id'))
    format: Mapped[str] = mapped_column(String(10), default='docx')
    renderer_version: Mapped[str] = mapped_column(String(30), default='docx-v1')
    content_hash: Mapped[str] = mapped_column(String(64))
    file_hash: Mapped[str] = mapped_column(String(64))
    file_bytes: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)

# Register dispatch metadata and transactional enqueue hooks for API and workers.
from .queue_models import DispatchEvent
from . import outbox as _outbox

# Register practice tables with Alembic and test metadata.
from .practice_models import ReviewedAnswer, InterviewSession, InterviewResponse

# Register tracking/privacy metadata for migrations and worker lifecycles.
from .tracking_models import ApplicationTracking,ApplicationEvent,AuditEvent,AccountDeletion
