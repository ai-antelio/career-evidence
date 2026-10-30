"""Candidate-owned reviewed answers and immutable interview practice records."""
import time
from sqlalchemy import String, Text, Float, Integer, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base
from .models import uid

class ReviewedAnswer(Base):
    __tablename__='reviewed_answers'
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    owner_id:Mapped[str]=mapped_column(ForeignKey('users.id'),index=True)
    opportunity_id:Mapped[str]=mapped_column(ForeignKey('opportunities.id'),index=True)
    workflow_id:Mapped[str]=mapped_column(ForeignKey('career_workflows.id'),unique=True)
    question:Mapped[str]=mapped_column(Text)
    claims:Mapped[list]=mapped_column(JSON)
    input_json:Mapped[dict]=mapped_column(JSON)
    input_hash:Mapped[str]=mapped_column(String(64))
    findings:Mapped[list]=mapped_column(JSON,default=list)
    status:Mapped[str]=mapped_column(String(30),default='draft')
    revision:Mapped[int]=mapped_column(Integer,default=0)
    approved_hash:Mapped[str]=mapped_column(String(64),default='')
    history:Mapped[list]=mapped_column(JSON,default=list)
    created_at:Mapped[float]=mapped_column(Float,default=time.time)

class InterviewSession(Base):
    __tablename__='interview_sessions'
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    owner_id:Mapped[str]=mapped_column(ForeignKey('users.id'),index=True)
    opportunity_id:Mapped[str]=mapped_column(ForeignKey('opportunities.id'),index=True)
    workflow_id:Mapped[str]=mapped_column(ForeignKey('career_workflows.id'),unique=True)
    input_hash:Mapped[str]=mapped_column(String(64))
    input_json:Mapped[dict]=mapped_column(JSON)
    questions:Mapped[list]=mapped_column(JSON)
    status:Mapped[str]=mapped_column(String(30),default='ready')
    created_at:Mapped[float]=mapped_column(Float,default=time.time)

class InterviewResponse(Base):
    __tablename__='interview_responses'
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    session_id:Mapped[str]=mapped_column(ForeignKey('interview_sessions.id'),index=True)
    question_id:Mapped[str]=mapped_column(String(36))
    text:Mapped[str]=mapped_column(Text)
    input_hash:Mapped[str]=mapped_column(String(64))
    workflow_id:Mapped[str|None]=mapped_column(ForeignKey('career_workflows.id'),nullable=True,unique=True)
    feedback:Mapped[dict]=mapped_column(JSON,default=dict)
    status:Mapped[str]=mapped_column(String(30),default='queued')
    created_at:Mapped[float]=mapped_column(Float,default=time.time)
