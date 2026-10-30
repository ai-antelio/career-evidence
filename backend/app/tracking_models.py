"""Candidate-owned tracking and privacy lifecycle records."""
import time
from sqlalchemy import String, Text, Float, Integer, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base
from .models import uid

class ApplicationTracking(Base):
    __tablename__='application_tracking'
    application_id:Mapped[str]=mapped_column(ForeignKey('applications.id'),primary_key=True)
    revision:Mapped[int]=mapped_column(Integer,default=0)
    status:Mapped[str]=mapped_column(String(30),default='drafting')
    notes:Mapped[str]=mapped_column(Text,default='')
    next_action:Mapped[str]=mapped_column(Text,default='')
    follow_up_at:Mapped[str|None]=mapped_column(String(40),nullable=True)
    submitted_snapshot:Mapped[dict|None]=mapped_column(JSON,nullable=True)

class ApplicationEvent(Base):
    __tablename__='application_events'
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    application_id:Mapped[str]=mapped_column(ForeignKey('applications.id'),index=True)
    kind:Mapped[str]=mapped_column(String(30))
    status:Mapped[str]=mapped_column(String(30))
    note:Mapped[str]=mapped_column(Text,default='')
    created_at:Mapped[float]=mapped_column(Float,default=time.time)

class AuditEvent(Base):
    __tablename__='audit_events'
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    owner_id:Mapped[str]=mapped_column(ForeignKey('users.id'),index=True)
    action:Mapped[str]=mapped_column(String(100))
    resource:Mapped[str]=mapped_column(String(250),default='')
    status_code:Mapped[int]=mapped_column(Integer,default=200)
    created_at:Mapped[float]=mapped_column(Float,default=time.time)

class AccountDeletion(Base):
    # No foreign key: retryable filesystem cleanup outlives the account rows.
    __tablename__='account_deletion_jobs'
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    owner_id:Mapped[str|None]=mapped_column(String(36),unique=True,nullable=True)
    status:Mapped[str]=mapped_column(String(30),default='queued',index=True)
    storage_keys:Mapped[list]=mapped_column(JSON,default=list)
    attempts:Mapped[int]=mapped_column(Integer,default=0)
    error:Mapped[str]=mapped_column(String(100),default='')
    created_at:Mapped[float]=mapped_column(Float,default=time.time)
    completed_at:Mapped[float|None]=mapped_column(Float,nullable=True)
