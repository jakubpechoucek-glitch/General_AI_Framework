"""Normalized data model.

Principle (Gap Rules R20): Required Level belongs to a ROLE, Current Level belongs
to an EMPLOYEE. One response record per Assessment + KSC Code.
"""
from datetime import date, datetime, timezone

from sqlalchemy import (Boolean, Date, DateTime, ForeignKey, Integer, String, Text,
                        UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

AREA_TYPES = ("Knowledge", "Skill", "Competency")
WORKFLOW = ("Draft", "Submitted", "Manager Review", "Calibration", "Finalized")
CONFIDENCE = ("Low", "Medium", "High")
ROLE_VALIDATION = ("Draft — title-based proposal", "In review with management", "Validated")


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Area(Base):
    """One of the framework areas (K01-K08, S01-S11, C01-C10 initially)."""
    __tablename__ = "areas"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(10), unique=True)
    type: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(200))
    definition: Mapped[str] = mapped_column(Text, default="")
    observable: Mapped[str] = mapped_column(Text, default="")
    evidence_example: Mapped[str] = mapped_column(Text, default="")
    critical_control: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class ScaleLevel(Base):
    """Shared 0-4 proficiency scale with type-specific anchors."""
    __tablename__ = "scale_levels"
    level: Mapped[int] = mapped_column(Integer, primary_key=True)
    label: Mapped[str] = mapped_column(String(50))
    knowledge: Mapped[str] = mapped_column(Text, default="")
    skill: Mapped[str] = mapped_column(Text, default="")
    competency: Mapped[str] = mapped_column(Text, default="")
    jd_wording: Mapped[str] = mapped_column(Text, default="")

    def anchor(self, area_type: str) -> str:
        return {"Knowledge": self.knowledge, "Skill": self.skill,
                "Competency": self.competency}.get(area_type, "")


class EvidenceGuide(Base):
    """Type-specific evidence guidance (Gap Rules R05)."""
    __tablename__ = "evidence_guides"
    type: Mapped[str] = mapped_column(String(20), primary_key=True)
    prompt: Mapped[str] = mapped_column(Text)


class Team(Base):
    """An onboarded organisational unit (e.g. CRM)."""
    __tablename__ = "teams"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    roles: Mapped[list["Role"]] = relationship(back_populates="team", order_by="Role.sort_order")


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("team_id", "title"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    family: Mapped[str] = mapped_column(String(100), default="")
    title: Mapped[str] = mapped_column(String(200))
    validation_status: Mapped[str] = mapped_column(String(60), default=ROLE_VALIDATION[0])
    validated_by: Mapped[str] = mapped_column(String(200), default="")
    validated_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    rationale: Mapped[str] = mapped_column(Text, default="")
    reviewer_comment: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    team: Mapped[Team] = relationship(back_populates="roles")
    requirements: Mapped[list["RoleRequirement"]] = relationship(
        back_populates="role", cascade="all, delete-orphan")

    @property
    def is_validated(self) -> bool:
        return self.validation_status == "Validated"

    def required_map(self) -> dict[int, int]:
        return {r.area_id: r.level for r in self.requirements}


class RoleRequirement(Base):
    __tablename__ = "role_requirements"
    __table_args__ = (UniqueConstraint("role_id", "area_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"))
    area_id: Mapped[int] = mapped_column(ForeignKey("areas.id"))
    level: Mapped[int] = mapped_column(Integer, default=0)
    role: Mapped[Role] = relationship(back_populates="requirements")
    area: Mapped[Area] = relationship()


class User(Base):
    """Employee record + application login."""
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(200), unique=True)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    role_id: Mapped[int | None] = mapped_column(ForeignKey("roles.id"), nullable=True)
    manager_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_calibrator: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    password_hash: Mapped[str] = mapped_column(String(300), default="")
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True)
    team: Mapped[Team | None] = relationship()
    role: Mapped[Role | None] = relationship()
    manager: Mapped["User | None"] = relationship(remote_side="User.id")


class Cycle(Base):
    __tablename__ = "cycles"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Assessment(Base):
    """One assessment per employee per cycle (Assessment ID)."""
    __tablename__ = "assessments"
    __table_args__ = (UniqueConstraint("cycle_id", "employee_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    cycle_id: Mapped[int] = mapped_column(ForeignKey("cycles.id"))
    employee_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"))
    manager_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="Draft")
    role_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    role_mismatch_note: Mapped[str] = mapped_column(Text, default="")
    assessment_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    validation_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_review_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    validated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    cycle: Mapped[Cycle] = relationship()
    employee: Mapped[User] = relationship(foreign_keys=[employee_id])
    manager: Mapped[User | None] = relationship(foreign_keys=[manager_id])
    validated_by: Mapped[User | None] = relationship(foreign_keys=[validated_by_id])
    role: Mapped[Role] = relationship()
    responses: Mapped[list["Response"]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan")


class Response(Base):
    """One record per Assessment + KSC area."""
    __tablename__ = "responses"
    __table_args__ = (UniqueConstraint("assessment_id", "area_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id", ondelete="CASCADE"))
    area_id: Mapped[int] = mapped_column(ForeignKey("areas.id"))
    required_level: Mapped[int] = mapped_column(Integer, default=0)
    self_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    self_evidence: Mapped[str] = mapped_column(Text, default="")
    evidence_link: Mapped[str] = mapped_column(String(1000), default="")
    confidence: Mapped[str] = mapped_column(String(10), default="")
    manager_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    manager_comment: Mapped[str] = mapped_column(Text, default="")
    validated_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    assessment: Mapped[Assessment] = relationship(back_populates="responses")
    area: Mapped[Area] = relationship()


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    user_email: Mapped[str] = mapped_column(String(200), default="")
    action: Mapped[str] = mapped_column(String(100))
    entity: Mapped[str] = mapped_column(String(100), default="")
    detail: Mapped[str] = mapped_column(Text, default="")
