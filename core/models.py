"""Database models (SQLAlchemy 2.0). Schema changes go through Alembic migrations in core/migrations."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


ROLES = ("viewer", "analyst", "admin")


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    disabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)
    last_login: Mapped[Optional[float]] = mapped_column(Float)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    csrf_token: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)
    expires_at: Mapped[float] = mapped_column(Float, nullable=False)
    ip: Mapped[Optional[str]] = mapped_column(String(64))
    user_agent: Mapped[Optional[str]] = mapped_column(String(255))
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class AuditEvent(Base):
    """Append-only, hash-chained record of every state-changing action (who, what, when, from where)."""
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    t: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer)
    username: Mapped[Optional[str]] = mapped_column(String(64))
    role: Mapped[Optional[str]] = mapped_column(String(16))
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target: Mapped[Optional[str]] = mapped_column(String(255))
    result: Mapped[str] = mapped_column(String(16), nullable=False)  # success | denied | failed
    ip: Mapped[Optional[str]] = mapped_column(String(64))
    user_agent: Mapped[Optional[str]] = mapped_column(String(255))
    details: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    hash: Mapped[str] = mapped_column(String(64), nullable=False)


class Switch(Base):
    __tablename__ = "switches"
    dpid: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[Optional[str]] = mapped_column(String(64))
    first_seen: Mapped[float] = mapped_column(Float, nullable=False)
    last_seen: Mapped[float] = mapped_column(Float, nullable=False)
    connected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    monitor_up: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class RuleSnapshot(Base):
    """Latest per-rule integrity view of one table, as published by the engine after a verification pass."""
    __tablename__ = "rule_snapshots"
    __table_args__ = (UniqueConstraint("dpid", "table_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dpid: Mapped[str] = mapped_column(String(16), nullable=False)
    table_id: Mapped[int] = mapped_column(Integer, nullable=False)
    t: Mapped[float] = mapped_column(Float, nullable=False)
    epoch: Mapped[Optional[int]] = mapped_column(Integer)
    rules_json: Mapped[str] = mapped_column(Text, nullable=False)


class Incident(Base):
    __tablename__ = "incidents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")  # open | acknowledged | closed
    dpid: Mapped[Optional[str]] = mapped_column(String(16))
    slot_key: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    assignee: Mapped[Optional[str]] = mapped_column(String(64))
    alert_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[float] = mapped_column(Float, nullable=False)
    closed_at: Mapped[Optional[float]] = mapped_column(Float)


class IncidentNote(Base):
    __tablename__ = "incident_notes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False, index=True)
    t: Mapped[float] = mapped_column(Float, nullable=False)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (Index("ix_alerts_t", "t"), Index("ix_alerts_kind", "kind"))
    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # engine-generated uuid hex
    seq: Mapped[Optional[int]] = mapped_column(Integer, unique=True)  # engine spool sequence
    t: Mapped[float] = mapped_column(Float, nullable=False)
    kind: Mapped[str] = mapped_column(String(48), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    layer: Mapped[str] = mapped_column(String(8), nullable=False, default="L1")
    dpid: Mapped[Optional[str]] = mapped_column(String(16))
    table_id: Mapped[Optional[int]] = mapped_column(Integer)
    priority: Mapped[Optional[int]] = mapped_column(Integer)
    action: Mapped[Optional[str]] = mapped_column(String(32))
    detected_by: Mapped[Optional[str]] = mapped_column(String(32))
    summary: Mapped[Optional[str]] = mapped_column(Text)
    detect_latency_ms: Mapped[Optional[float]] = mapped_column(Float)
    time_to_restore_ms: Mapped[Optional[float]] = mapped_column(Float)
    restored_at: Mapped[Optional[float]] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="new")  # new | acknowledged
    acknowledged_by: Mapped[Optional[str]] = mapped_column(String(64))
    acknowledged_at: Mapped[Optional[float]] = mapped_column(Float)
    incident_id: Mapped[Optional[int]] = mapped_column(ForeignKey("incidents.id", ondelete="SET NULL"), index=True)
    payload: Mapped[str] = mapped_column(Text, nullable=False)  # the full engine record (JSON)


class EngineEvent(Base):
    __tablename__ = "engine_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    t: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(48), nullable=False)
    dpid: Mapped[Optional[str]] = mapped_column(String(16))
    payload: Mapped[str] = mapped_column(Text, nullable=False)


class PolicyDoc(Base):
    """The single current policy document (risk weights, thresholds, response, dry run). Versioned in PolicyHistory."""
    __tablename__ = "policy_doc"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    data: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[float] = mapped_column(Float, nullable=False)
    updated_by: Mapped[Optional[str]] = mapped_column(String(64))


class PolicyHistory(Base):
    __tablename__ = "policy_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    data: Mapped[str] = mapped_column(Text, nullable=False)
    t: Mapped[float] = mapped_column(Float, nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String(64))


class Recording(Base):
    """A recorded live session: every ingested record appended to data/sessions/<id>.jsonl."""
    __tablename__ = "recordings"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    started_at: Mapped[float] = mapped_column(Float, nullable=False)
    stopped_at: Mapped[Optional[float]] = mapped_column(Float)
    started_by: Mapped[Optional[str]] = mapped_column(String(64))
    path: Mapped[str] = mapped_column(String(512), nullable=False)
    records: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ProbeResult(Base):
    """L2 canary results (filled from Phase 5; the table exists so the API contract is stable)."""
    __tablename__ = "probe_results"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    t: Mapped[float] = mapped_column(Float, nullable=False)
    dpid: Mapped[Optional[str]] = mapped_column(String(16))
    payload: Mapped[str] = mapped_column(Text, nullable=False)


class MlScore(Base):
    """L3 anomaly scores (filled from Phase 5)."""
    __tablename__ = "ml_scores"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    t: Mapped[float] = mapped_column(Float, nullable=False)
    dpid: Mapped[Optional[str]] = mapped_column(String(16))
    score: Mapped[float] = mapped_column(Float, nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)


class Meta(Base):
    __tablename__ = "meta"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
