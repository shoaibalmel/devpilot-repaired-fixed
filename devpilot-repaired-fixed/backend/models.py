from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, DateTime, Float
from .database import Base

def utcnow(): return datetime.now(timezone.utc)
class AgentAction(Base):
    __tablename__='agent_actions'
    id=Column(Integer,primary_key=True); request=Column(Text,nullable=False); intent=Column(String(80),nullable=False); tool=Column(String(120),nullable=False); status=Column(String(30),default='planned'); output=Column(Text,default=''); created_at=Column(DateTime(timezone=True),default=utcnow)
class Deployment(Base):
    __tablename__='deployments'
    id=Column(Integer,primary_key=True); name=Column(String(160),nullable=False); repo_url=Column(String(500),default=''); branch=Column(String(120),default='main'); status=Column(String(30),default='PENDING'); progress=Column(Integer,default=0); message=Column(Text,default=''); created_at=Column(DateTime(timezone=True),default=utcnow); updated_at=Column(DateTime(timezone=True),default=utcnow,onupdate=utcnow); command_id=Column(String(100),default=''); artifact_key=Column(String(500),default='')
class Incident(Base):
    __tablename__='incidents'
    id=Column(Integer,primary_key=True); title=Column(String(220),nullable=False); severity=Column(String(30),default='medium'); status=Column(String(30),default='OPEN'); evidence=Column(Text,default=''); probable_cause=Column(Text,default=''); recommendation=Column(Text,default=''); created_at=Column(DateTime(timezone=True),default=utcnow)
class StoredFile(Base):
    __tablename__='stored_files'
    id=Column(Integer,primary_key=True); name=Column(String(500),nullable=False); object_key=Column(String(1000),nullable=False,unique=True); content_type=Column(String(200),default='application/octet-stream'); size=Column(Float,default=0); storage=Column(String(20),default='local'); created_at=Column(DateTime(timezone=True),default=utcnow)
