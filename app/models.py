"""SQLAlchemy ORM models for crux.

Column types use SQLAlchemy's portable forms (String, Enum) so they work
against both Neon Postgres (production) and SQLite in-memory (tests).
"""
import uuid

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    Enum,
    ForeignKey,
    Integer,
    Text,
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.types import TIMESTAMP, String, JSON

Base = declarative_base()

_STAGE = ("sharpened", "bake_off", "gather", "weigh", "probe", "verdict")
_PLAN_LABEL = ("A", "B", "C")
_SOURCE_KIND = ("book", "article", "youtube")
_SUPPORT_STATUS = ("supports", "contradicts", "neutral", "inconclusive")
_PROBE_TYPE = ("measurement", "lab-test", "behaviour-experiment", "prototype")
_PROBE_STATUS = ("designed", "running", "confirmed", "killed", "inconclusive")
_VERDICT_OUTCOME = ("confirmed", "killed", "inconclusive")


def _uuid():
    return str(uuid.uuid4())


class Case(Base):
    __tablename__ = "case"

    id = Column(String(36), primary_key=True, default=_uuid)
    raw_problem = Column(Text, nullable=False)
    sharpened = Column(Text)
    not_investigating = Column(Text)
    stage = Column(Enum(*_STAGE, name="stage_enum"), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True))
    weigh_context = Column(Text)

    summary = Column(Text)

    plans = relationship("Plan", back_populates="case", cascade="all, delete-orphan")
    probes = relationship("Probe", back_populates="case", cascade="all, delete-orphan")


class Plan(Base):
    __tablename__ = "plan"

    id = Column(String(36), primary_key=True, default=_uuid)
    case_id = Column(String(36), ForeignKey("case.id", ondelete="CASCADE"), nullable=False)
    label = Column(Enum(*_PLAN_LABEL, name="plan_label_enum"), nullable=False)
    name = Column(Text)
    mechanism = Column(Text)
    prior = Column(Text)
    current_rank = Column(Integer)
    standing = Column(Text)

    case = relationship("Case", back_populates="plans")
    sources = relationship("Source", back_populates="plan", cascade="all, delete-orphan")


class Source(Base):
    __tablename__ = "source"

    id = Column(String(36), primary_key=True, default=_uuid)
    plan_id = Column(String(36), ForeignKey("plan.id", ondelete="CASCADE"), nullable=False)
    kind = Column(Enum(*_SOURCE_KIND, name="source_kind_enum"), nullable=False)
    title = Column(Text)
    url = Column(Text)
    claim = Column(Text)
    citation = Column(Text)
    support_status = Column(Enum(*_SUPPORT_STATUS, name="support_status_enum"), nullable=True)
    rationale = Column(Text, nullable=True)
    manually_overridden = Column(Boolean, nullable=False, default=False)

    plan = relationship("Plan", back_populates="sources")
    verifications = relationship(
        "SourceVerification", back_populates="source", cascade="all, delete-orphan"
    )


class SourceVerification(Base):
    """Result of a fetch → Claude analysis → DB write pipeline run for one source."""

    __tablename__ = "source_verification"

    id = Column(String(36), primary_key=True, default=_uuid)
    source_id = Column(
        String(36), ForeignKey("source.id", ondelete="CASCADE"), nullable=False
    )
    verdict = Column(String(32), nullable=False)  # 'supports' | 'contradicts' | 'unverified'
    summary = Column(Text, nullable=True)   # non-null when verdict in ('supports', 'contradicts')
    reason = Column(Text, nullable=True)    # non-null when verdict == 'unverified'
    created_at = Column(TIMESTAMP(timezone=True), nullable=True)

    source = relationship("Source", back_populates="verifications")


class Probe(Base):
    __tablename__ = "probe"

    id = Column(String(36), primary_key=True, default=_uuid)
    case_id = Column(String(36), ForeignKey("case.id", ondelete="CASCADE"), nullable=False)
    type = Column(Enum(*_PROBE_TYPE, name="probe_type_enum"), nullable=False)
    target_metric = Column(Text)
    cost = Column(Text)
    time = Column(Text)
    note = Column(Text)
    steps = Column(JSON)
    duration = Column(Text)
    decision_rule = Column(Text)
    status = Column(
        Enum(*_PROBE_STATUS, name="probe_status_enum"),
        nullable=False,
        default="designed",
    )
    due_date = Column(Date)
    commander_spec = Column(Text)
    created_at = Column(TIMESTAMP(timezone=True))

    case = relationship("Case", back_populates="probes")
    verdicts = relationship("Verdict", back_populates="probe")


class Verdict(Base):
    __tablename__ = "verdict"

    id = Column(String(36), primary_key=True, default=_uuid)
    probe_id = Column(String(36), ForeignKey("probe.id", ondelete="RESTRICT"), nullable=False)
    outcome = Column(Enum(*_VERDICT_OUTCOME, name="verdict_outcome_enum"), nullable=False)
    notes = Column(Text)
    decided_at = Column(TIMESTAMP(timezone=True))

    probe = relationship("Probe", back_populates="verdicts")


class CaseEmbedding(Base):
    __tablename__ = "case_embedding"

    case_id = Column(String(36), ForeignKey("case.id", ondelete="CASCADE"), primary_key=True)
    embedding = Column(Text, nullable=False)  # JSON-serialized float array
    model_version = Column(String(128), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False)

    case = relationship("Case")
