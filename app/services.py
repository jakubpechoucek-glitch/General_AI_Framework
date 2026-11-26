"""Domain services shared by the routes."""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from . import logic
from .models import Area, Assessment, AuditLog, Cycle, EvidenceGuide, Response, Role, ScaleLevel, User, utcnow

EDITABLE_BY_EMPLOYEE = ("Draft",)


def audit(db: Session, user: User | None, action: str, entity: str = "", detail: str = ""):
    db.add(AuditLog(user_email=user.email if user else "system", action=action,
                    entity=entity, detail=detail[:4000]))


def active_areas(db: Session) -> list[Area]:
    return db.query(Area).filter(Area.active.is_(True)).order_by(Area.sort_order, Area.code).all()


def scale(db: Session) -> list[ScaleLevel]:
    return db.query(ScaleLevel).order_by(ScaleLevel.level).all()


def evidence_guides(db: Session) -> dict[str, str]:
    return {g.type: g.prompt for g in db.query(EvidenceGuide).all()}


def active_cycle(db: Session) -> Cycle | None:
    return db.query(Cycle).filter(Cycle.active.is_(True)).order_by(Cycle.id.desc()).first()


def start_assessment(db: Session, user: User, cycle: Cycle) -> Assessment:
    """Create an assessment with one response per active area (R20)."""
    if not user.role_id:
        raise ValueError("No role is assigned to you yet. Please contact the administrator.")
    a = Assessment(code="tmp", cycle=cycle, employee=user, role_id=user.role_id,
                   manager_id=user.manager_id, status="Draft")
    db.add(a)
    db.flush()
    a.code = f"ASM-{cycle.id:02d}-{a.id:05d}"
    sync_requirements(db, a)
    audit(db, user, "assessment.create", a.code)
    return a


def sync_requirements(db: Session, a: Assessment) -> None:
    """R01: Required Level = lookup(Role, Area). Kept live until Finalized, then frozen.

    Adds responses for newly activated areas; removes untouched responses for areas
    that were deactivated.
    """
    if a.status == "Finalized":
        return
    role = db.get(Role, a.role_id)
    req = role.required_map() if role else {}
    areas = active_areas(db)
    active_ids = {ar.id for ar in areas}
    existing = {r.area_id: r for r in a.responses}
    for ar in areas:
        r = existing.get(ar.id)
        if r is None:
            r = Response(area_id=ar.id, area=ar)
            a.responses.append(r)
        r.required_level = req.get(ar.id, 0)
    for area_id, r in existing.items():
        if area_id not in active_ids and r.self_level is None and r.validated_level is None:
            a.responses.remove(r)


def sorted_responses(a: Assessment) -> list[Response]:
    order = {"Knowledge": 0, "Skill": 1, "Competency": 2}
    return sorted(a.responses, key=lambda r: (order.get(r.area.type, 9), r.area.sort_order,
                                              r.area.code))


def rows_for(a: Assessment, use: str = "validated") -> list[logic.Row]:
    rows = []
    for r in sorted_responses(a):
        level = r.validated_level if use == "validated" else r.self_level
        rows.append(logic.Row(r.area.code, r.area.name, r.area.type, r.required_level, level,
                              r.area.critical_control))
    return rows


def finalize(db: Session, a: Assessment, by: User, next_review: date | None = None):
    sync_requirements(db, a)  # last sync, then frozen
    now = utcnow()
    a.status = "Finalized"
    a.validation_date = now
    a.validated_by_id = by.id
    a.next_review_date = next_review or logic.next_review(now.date())


def reopen(db: Session, a: Assessment, by: User, reason: str = ""):
    a.status = "Draft"
    a.version += 1
    a.validation_date = None
    audit(db, by, "assessment.reopen", a.code, reason)
    sync_requirements(db, a)


def latest_assessment(db: Session, user: User, finalized_only: bool = False) -> Assessment | None:
    q = db.query(Assessment).filter(Assessment.employee_id == user.id)
    if finalized_only:
        q = q.filter(Assessment.status == "Finalized")
    return q.order_by(Assessment.id.desc()).first()
