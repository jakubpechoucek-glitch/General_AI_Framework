"""Login, home, framework reference and the employee self-assessment."""
from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session

from .. import logic
from ..auth import Forbidden, LoginRequired, can_view, current_user, hash_password, is_manager, verify_password
from ..db import get_db
from ..models import CONFIDENCE, Assessment, User, utcnow
from ..services import (EDITABLE_BY_EMPLOYEE, active_cycle, audit, evidence_guides, rows_for,
                        scale, sorted_responses, start_assessment, sync_requirements)
from ..web import flash, redirect, render

router = APIRouter()


def _int(v):
    try:
        return int(v) if v not in (None, "") else None
    except ValueError:
        return None


# --- auth -------------------------------------------------------------------------

@router.get("/login")
def login_form(request: Request):
    return render(request, "login.html")


@router.post("/login")
def login(request: Request, email: str = Form(...), password: str = Form(...),
          db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == email.strip().lower()).one_or_none()
    if not user or not user.active or not verify_password(password, user.password_hash):
        flash(request, "Invalid email or password.", "error")
        return render(request, "login.html", status_code=401, email=email)
    request.session.clear()
    request.session["uid"] = user.id
    audit(db, user, "login")
    db.commit()
    return redirect("/password" if user.must_change_password else "/")


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return redirect("/login")


@router.get("/password")
def password_form(request: Request, db: Session = Depends(get_db)):
    uid = request.session.get("uid")
    if not uid:
        raise LoginRequired()
    return render(request, "password.html", me=db.get(User, uid))


@router.post("/password")
def password_change(request: Request, current: str = Form(""), new: str = Form(...),
                    confirm: str = Form(...), db: Session = Depends(get_db)):
    uid = request.session.get("uid")
    user = db.get(User, uid) if uid else None
    if not user:
        raise LoginRequired()
    err = None
    if not user.must_change_password and not verify_password(current, user.password_hash):
        err = "Current password is incorrect."
    elif len(new) < 10:
        err = "Use at least 10 characters."
    elif new != confirm:
        err = "The passwords do not match."
    if err:
        flash(request, err, "error")
        return render(request, "password.html", me=user, status_code=400)
    user.password_hash = hash_password(new)
    user.must_change_password = False
    audit(db, user, "password.change")
    db.commit()
    flash(request, "Password updated.", "success")
    return redirect("/")


# --- home -------------------------------------------------------------------------

@router.get("/")
def home(request: Request, me: User = Depends(current_user), db: Session = Depends(get_db)):
    cycle = active_cycle(db)
    mine = (db.query(Assessment).filter_by(employee_id=me.id).order_by(Assessment.id.desc()).all())
    current = next((a for a in mine if cycle and a.cycle_id == cycle.id), None)
    reports = db.query(User).filter(User.manager_id == me.id, User.active.is_(True)).all()
    pending = []
    if reports and cycle:
        pending = (db.query(Assessment)
                   .filter(Assessment.cycle_id == cycle.id,
                           Assessment.employee_id.in_([u.id for u in reports]),
                           Assessment.status.in_(["Submitted", "Manager Review", "Calibration"]))
                   .all())
    return render(request, "home.html", me=me, cycle=cycle, current=current, history=mine,
                  reports=reports, pending=pending, me_is_manager=bool(reports))


@router.get("/framework")
def framework(request: Request, me: User = Depends(current_user), db: Session = Depends(get_db)):
    from ..services import active_areas
    return render(request, "framework.html", me=me, me_is_manager=is_manager(db, me),
                  areas=active_areas(db), scale=scale(db), guides=evidence_guides(db))


# --- self-assessment ----------------------------------------------------------------

@router.get("/assessment")
def my_assessment(request: Request, me: User = Depends(current_user), db: Session = Depends(get_db)):
    cycle = active_cycle(db)
    if cycle:
        a = db.query(Assessment).filter_by(cycle_id=cycle.id, employee_id=me.id).one_or_none()
        if a:
            return redirect(f"/assessment/{a.id}")
    return render(request, "assessment_start.html", me=me, cycle=cycle,
                  me_is_manager=is_manager(db, me))


@router.post("/assessment/start")
def assessment_start(request: Request, confirm: str = Form(...), note: str = Form(""),
                     me: User = Depends(current_user), db: Session = Depends(get_db)):
    cycle = active_cycle(db)
    if not cycle:
        flash(request, "There is no active assessment cycle.", "error")
        return redirect("/")
    existing = db.query(Assessment).filter_by(cycle_id=cycle.id, employee_id=me.id).one_or_none()
    if existing:
        return redirect(f"/assessment/{existing.id}")
    if confirm != "yes":
        if not note.strip():
            flash(request, "Please describe what is wrong with your role so the administrator "
                           "can correct it.", "error")
            return redirect("/assessment")
        audit(db, me, "role.mismatch", me.email, note)
        db.commit()
        flash(request, "Thank you. The administrator has been notified and will correct your "
                       "role before you start.", "success")
        return redirect("/")
    try:
        a = start_assessment(db, me, cycle)
    except ValueError as e:
        flash(request, str(e), "error")
        return redirect("/")
    a.role_confirmed = True
    db.commit()
    return redirect(f"/assessment/{a.id}")


def _own(db: Session, me: User, aid: int) -> Assessment:
    a = db.get(Assessment, aid)
    if not a or a.employee_id != me.id:
        raise Forbidden()
    return a


@router.get("/assessment/{aid}")
def assessment_form(aid: int, request: Request, me: User = Depends(current_user),
                    db: Session = Depends(get_db)):
    a = _own(db, me, aid)
    if a.status not in EDITABLE_BY_EMPLOYEE:
        return redirect(f"/assessment/{aid}/results")
    sync_requirements(db, a)
    db.commit()
    responses = [r for r in sorted_responses(a) if r.required_level > 0]  # R02
    return render(request, "assessment_form.html", me=me, a=a, responses=responses,
                  scale=scale(db), guides=evidence_guides(db), confidence=CONFIDENCE,
                  errors=request.session.pop("form_errors", {}),
                  me_is_manager=is_manager(db, me))


@router.post("/assessment/{aid}")
async def assessment_save(aid: int, request: Request, me: User = Depends(current_user),
                          db: Session = Depends(get_db)):
    a = _own(db, me, aid)
    if a.status not in EDITABLE_BY_EMPLOYEE:
        flash(request, "This assessment is locked after submission.", "error")
        return redirect(f"/assessment/{aid}/results")
    form = await request.form()
    for r in a.responses:
        if r.required_level == 0 or f"level_{r.id}" not in form and f"evidence_{r.id}" not in form:
            continue
        lvl = _int(form.get(f"level_{r.id}"))
        r.self_level = lvl if lvl is None or 0 <= lvl <= 4 else None
        r.self_evidence = (form.get(f"evidence_{r.id}") or "").strip()
        r.evidence_link = (form.get(f"link_{r.id}") or "").strip()
        conf = form.get(f"conf_{r.id}") or ""
        r.confidence = conf if conf in CONFIDENCE else ""
    action = form.get("action", "save")
    if action == "submit":
        errors = {}
        for r in a.responses:
            e = logic.validate_self_response(r.required_level, r.self_level, r.self_evidence,
                                             r.evidence_link, r.confidence)
            if e:
                errors[str(r.id)] = e
        if not form.get("confirm_accuracy"):
            errors["confirm"] = ["Please confirm that your self-assessment is accurate."]
        if errors:
            db.commit()  # keep the draft
            request.session["form_errors"] = errors
            flash(request, f"Please fix {len(errors)} item(s) before submitting.", "error")
            return redirect(f"/assessment/{aid}#errors")
        a.status = "Submitted"  # R15: locks employee edits
        a.assessment_date = utcnow()
        audit(db, me, "assessment.submit", a.code, f"version {a.version}")
        db.commit()
        flash(request, "Self-assessment submitted. Your manager will now review it.", "success")
        return redirect(f"/assessment/{aid}/results")
    db.commit()
    flash(request, "Draft saved.", "success")
    return redirect(f"/assessment/{aid}")


@router.get("/assessment/{aid}/results")
def assessment_results(aid: int, request: Request, me: User = Depends(current_user),
                       db: Session = Depends(get_db)):
    a = db.get(Assessment, aid)
    if not a or not can_view(me, a):
        raise Forbidden()
    if a.status == "Draft" and a.employee_id == me.id:
        return redirect(f"/assessment/{aid}")
    official = a.status == "Finalized"
    rows = rows_for(a, "validated" if official else "self")
    return render(request, "results.html", me=me, a=a, official=official,
                  responses=sorted_responses(a), summary=logic.summarize(rows),
                  me_is_manager=is_manager(db, me))

