"""Transactional dispatch records. Payloads contain identifiers, never user text/secrets."""
import time, uuid
from sqlalchemy import String, Float, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

class DispatchEvent(Base):
    __tablename__ = 'dispatch_events'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda:str(uuid.uuid4()))
    topic: Mapped[str] = mapped_column(String(40))
    target_id: Mapped[str] = mapped_column(String(36), index=True)
    status: Mapped[str] = mapped_column(String(20), default='pending', index=True)
    available_at: Mapped[float] = mapped_column(Float, default=time.time, index=True)
    published_at: Mapped[float] = mapped_column(Float, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default='')
