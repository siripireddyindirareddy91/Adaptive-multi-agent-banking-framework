"""Relational persistence. PostgreSQL in production; SQLite for a portable demo."""
import os
import uuid
from datetime import datetime, timezone
from sqlalchemy import create_engine, String, Float, Integer, ForeignKey, JSON, DateTime, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

def now(): return datetime.now(timezone.utc)
def uid(): return str(uuid.uuid4())
url = os.getenv('DATABASE_URL') or ('sqlite:////tmp/nexora.db' if os.getenv('VERCEL') else 'sqlite:///./nexora.db')
if url.startswith('postgres://'): url = url.replace('postgres://', 'postgresql+psycopg://', 1)
if url.startswith('postgresql://'): url = url.replace('postgresql://', 'postgresql+psycopg://', 1)
engine = create_engine(url, connect_args={'check_same_thread':False} if url.startswith('sqlite') else {}, pool_pre_ping=True)
Session = sessionmaker(engine, expire_on_commit=False)
class Base(DeclarativeBase): pass
class Entity(Base):
    __abstract__ = True
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
class User(Entity):
    __tablename__='users'
    email: Mapped[str] = mapped_column(String(200), unique=True)
    name: Mapped[str] = mapped_column(String(150))
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(60))
class Customer(Entity):
    __tablename__='customers'
    name: Mapped[str] = mapped_column(String(150), index=True)
    email: Mapped[str] = mapped_column(String(200), unique=True)
    country: Mapped[str] = mapped_column(String(80), default='India')
    status: Mapped[str] = mapped_column(String(50), default='Submitted', index=True)
    risk: Mapped[float] = mapped_column(Float, default=0)
    profile: Mapped[dict] = mapped_column(JSON, default=dict)
    creator_id: Mapped[str | None] = mapped_column(ForeignKey('users.id'), nullable=True)
class Application(Entity):
    __tablename__='onboarding_applications'
    customer_id: Mapped[str] = mapped_column(ForeignKey('customers.id'), index=True)
    status: Mapped[str] = mapped_column(String(50), default='Submitted')
    data: Mapped[dict] = mapped_column(JSON, default=dict)
class Document(Entity):
    __tablename__='identity_documents'
    customer_id: Mapped[str] = mapped_column(ForeignKey('customers.id'), index=True)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(50))
    digest: Mapped[str] = mapped_column(String(64), index=True)
    content: Mapped[str] = mapped_column(Text)
    mime: Mapped[str] = mapped_column(String(80))
    findings: Mapped[dict] = mapped_column(JSON, default=dict)
class Transaction(Entity):
    __tablename__='transactions'
    customer_id: Mapped[str] = mapped_column(ForeignKey('customers.id'), index=True)
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(4), default='INR')
    type: Mapped[str] = mapped_column(String(50), default='Transfer')
    destination: Mapped[str] = mapped_column(String(150))
    risk: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(50))
class Alert(Entity):
    __tablename__='fraud_alerts'
    customer_id: Mapped[str] = mapped_column(ForeignKey('customers.id'), index=True)
    category: Mapped[str] = mapped_column(String(80))
    severity: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(50), default='New')
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
class Case(Entity):
    __tablename__='investigation_cases'
    customer_id: Mapped[str] = mapped_column(ForeignKey('customers.id'), index=True)
    title: Mapped[str] = mapped_column(String(200))
    type: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(50), default='New')
    priority: Mapped[str] = mapped_column(String(30), default='Medium')
    assignee: Mapped[str] = mapped_column(String(150), default='Unassigned')
    notes: Mapped[list] = mapped_column(JSON, default=list)
class Rule(Entity):
    __tablename__='compliance_rules'
    name: Mapped[str] = mapped_column(String(150))
    jurisdiction: Mapped[str] = mapped_column(String(100), default='India • synthetic policy')
    version: Mapped[str] = mapped_column(String(50), default='demo-1.0')
    condition: Mapped[str] = mapped_column(String(80))
    threshold: Mapped[float] = mapped_column(Float, default=60)
    enabled: Mapped[int] = mapped_column(Integer, default=1)
class Workflow(Entity):
    __tablename__='workflow_runs'
    customer_id: Mapped[str] = mapped_column(ForeignKey('customers.id'), index=True)
    status: Mapped[str] = mapped_column(String(50), default='Running')
    state: Mapped[dict] = mapped_column(JSON, default=dict)
    executions: Mapped[list] = mapped_column(JSON, default=list)
class Approval(Entity):
    __tablename__='human_approvals'
    customer_id: Mapped[str] = mapped_column(ForeignKey('customers.id'), index=True)
    workflow_id: Mapped[str | None] = mapped_column(ForeignKey('workflow_runs.id'), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default='Pending')
    required: Mapped[int] = mapped_column(Integer, default=1)
    decisions: Mapped[list] = mapped_column(JSON, default=list)
class Audit(Entity):
    __tablename__='audit_logs'
    actor: Mapped[str] = mapped_column(String(150))
    action: Mapped[str] = mapped_column(String(150))
    target: Mapped[str] = mapped_column(String(150))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
class Setting(Base):
    __tablename__='system_settings'
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)
class Refresh(Entity):
    __tablename__='refresh_tokens'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    digest: Mapped[str] = mapped_column(String(64), unique=True)
    expires: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used: Mapped[int] = mapped_column(Integer, default=0)

def serialize(obj):
    result = {c.name:getattr(obj,c.name) for c in obj.__table__.columns}
    for k,v in result.items():
        if isinstance(v,datetime): result[k]=v.isoformat()
    result.pop('password_hash',None)
    result.pop('content',None)
    return result
