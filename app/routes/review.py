"""Manager review, calibration, finalisation and reports."""
from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import Response as HTTPResponse
from sqlalchemy.orm import Session

from .. import logic
from ..auth import (Forbidden, can_calibrate, can_review, can_view, current_user, is_manager,
                    reporting_scope)
from ..db import get_db
from ..models import Assessment, Cycle, Team, User
from ..reporting import employee_summaries, export_report, team_summary
from ..services import (active_cycle, audit, finalize, reopen, rows_for, scale, sorted_responses,
                        sync_requirements)
from ..web import flash, redirect, render

router = APIRouter()


def _int(v):
    try:
        return int(v) if v not in (None, "") else None
    except ValueError:
        return None


@router.get("/team")
def team(request: Request, cycle_id: int | None = None, me: User = Depends(current_user),
         db: Session = Depends(get_db)):
    users = reporting_scope(db, me).filter(User.id != me.id).all()
    if not users:
        raise Forbidden()
    cycles = db.query(Cycle).order_by(Cycle.id.desc()).all()
    cycle = db.get(Cycle, cycle_id) if cycle_id else active_cycle(db)
    data = employee_summaries(db, users, cycle)
    return render(request, "team.html", me=me, me_is_manager=is_manager(db, me), cycle=cycle,
                  cycles=cycles, data=data)


def _load(db, me, aid) -> Assessment:
    a = db.get(Assessment, aid)
    if not a or not can_view(me, a) or a.employee_id == me.id and not me.is_admin:
        raise Forbidden()
    return a


@router.get("/review/{aid}")
def review(aid: int, request: Request, me: User = Depends(current_user),
           db: Session = Depends(get_db)):
    a = _load(db, me, aid)
    sync_requirements(db, a)
    db.commit()
    return render(request, "review.html", me=me, me_is_manager=is_manager(db, me), a=a,
                  responses=sorted_responses(a), scale=scale(db),
                  may_review=can_review(me, a), may_calibrate=can_calibrate(me, a),
                  summary=logic.summarize(rows_for(a)),
                  errors=request.session.pop("form_errors", {}),
                  default_next=logic.next_review(date.today()))


@router.post("/review/{aid}")
async def review_save(aid: int, request: Request, me: User = Depends(current_user),
                      db: Session = Depends(get_db)):
    a = _load(db, me, aid)
    form = await request.form()
    action = form.get("action", "save")
    errors: dict[str, list[str]] = {}

    if action in ("save_review", "complete_review"):
        if not can_review(me, a) or a.status not in ("Submitted", "Manager Review"):
            raise Forbidden()
        for r in a.responses:
            if r.required_level == 0:
                continue
            if f"mlevel_{r.id}" in form:
                lvl = _int(form.get(f"mlevel_{r.id}"))
                r.manager_level = lvl if lvl is None or 0 <= lvl <= 4 else None
            r.manager_comment = (form.get(f"mcomment_{r.id}") or "").strip()
        a.status = "Manager Review"
        if action == "complete_review":
            for r in a.responses:
                e = logic.validate_manager_response(r.required_level, r.self_level,
                                                    r.manager_level, r.manager_comment)
                if e:
                    errors[str(r.id)] = e
            if not errors:
                a.status = "Calibration"
                audit(db, me, "assessment.review_complete", a.code)
                db.commit()
                flash(request, "Manager review completed. Set the validated levels to finalise.",
                      "success")
                return redirect(f"/review/{aid}")

    elif action in ("save_validated", "copy_manager", "finalize"):
        if not can_calibrate(me, a) or a.status != "Calibration":
            raise Forbidden()
        for r in a.responses:
            if r.required_level == 0:
                continue
            if action == "copy_manager":
                if r.validated_level is None:
                    r.validated_level = r.manager_level
            elif f"vlevel_{r.id}" in form:
                lvl = _int(form.get(f"vlevel_{r.id}"))
                r.validated_level = lvl if lvl is None or 0 <= lvl <= 4 else None
        if action == "finalize":
            for r in a.responses:
                e = logic.validate_validated_response(r.required_level, r.validated_level)
                if e:
                    errors[str(r.id)] = e
            if not errors:
                nr = form.get("next_review_date")
                try:
                    nrd = date.fromisoformat(nr) if nr else None
                except ValueError:
                    nrd = None
                finalize(db, a, me, nrd)
                audit(db, me, "assessment.finalize", a.code, f"version {a.version}")
                db.commit()
                flash(request, "Assessment finalised. The official development gap is now "
                               "available.", "success")
                return redirect(f"/assessment/{aid}/results")

    elif action == "reopen":
        if not (can_calibrate(me, a) or me.is_admin) or a.status == "Draft":
            raise Forbidden()
        reopen(db, a, me, (form.get("reason") or "").strip())
        db.commit()
        flash(request, f"Assessment returned to the employee as Draft (version {a.version}).",
              "success")
        return redirect(f"/review/{aid}")
    else:
        raise Forbidden()

    db.commit()
    if errors:
        request.session["form_errors"] = errors
        flash(request, f"Please fix {len(errors)} item(s).", "error")
    else:
        flash(request, "Saved.", "success")
    return redirect(f"/review/{aid}")


# --- reports ----------------------------------------------------------------------

def _report_scope(db, me, team_id, cycle_id):
    q = reporting_scope(db, me)
    if team_id:
        q = q.filter(User.team_id == team_id)
    users = q.all()
    if not users and not me.is_admin:
        raise Forbidden()
    cycle = db.get(Cycle, cycle_id) if cycle_id else active_cycle(db)
    teams = db.query(Team).order_by(Team.name).all() if me.is_admin else []
    return users, cycle, teams


@router.get("/reports")
def reports(request: Request, team_id: int | None = None, cycle_id: int | None = None,
            me: User = Depends(current_user), db: Session = Depends(get_db)):
    users, cycle, teams = _report_scope(db, me, team_id, cycle_id)
    return render(request, "reports.html", me=me, me_is_manager=is_manager(db, me),
                  cycle=cycle, cycles=db.query(Cycle).order_by(Cycle.id.desc()).all(),
                  teams=teams, team_id=team_id, emp=employee_summaries(db, users, cycle),
                  t=team_summary(db, users, cycle))


@router.get("/reports/export.xlsx")
def reports_export(team_id: int | None = None, cycle_id: int | None = None,
                   me: User = Depends(current_user), db: Session = Depends(get_db)):
    users, cycle, _ = _report_scope(db, me, team_id, cycle_id)
    audit(db, me, "report.export", cycle.name if cycle else "")
    db.commit()
    name = f"AI_KSC_Gap_Report_{(cycle.name if cycle else 'none').replace(' ', '_')}.xlsx"
    return HTTPResponse(export_report(db, users, cycle),
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})
