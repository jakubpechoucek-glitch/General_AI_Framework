"""Administration: framework, scale, teams & roles (requirement matrix), employees, cycles,
imports, assessments and the audit log."""
from datetime import date

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import Response as HTTPResponse
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth import admin_user, hash_password, temp_password
from ..db import get_db
from ..importer import (import_employees, import_framework, import_role_matrix, import_scale,
                        load_workbook)
from ..models import (AREA_TYPES, ROLE_VALIDATION, Area, Assessment, AuditLog, Cycle,
                      EvidenceGuide, Response, Role, RoleRequirement, ScaleLevel, Team, User)
from ..reporting import export_employee_template, export_role_matrix
from ..services import active_areas, audit
from ..web import flash, redirect, render

router = APIRouter(prefix="/admin")
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _xlsx(data: bytes, name: str):
    return HTTPResponse(data, media_type=XLSX,
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})


def _page(request, name, me, **ctx):
    return render(request, name, me=me, me_is_manager=True, **ctx)


def _bool(v) -> bool:
    return v in ("on", "true", "1", "yes")


# --- dashboard --------------------------------------------------------------------

@router.get("")
def dashboard(request: Request, me: User = Depends(admin_user), db: Session = Depends(get_db)):
    by_status = dict(db.query(Assessment.status, func.count()).group_by(Assessment.status).all())
    mismatches = (db.query(AuditLog).filter(AuditLog.action == "role.mismatch")
                  .order_by(AuditLog.id.desc()).limit(20).all())
    teams = db.query(Team).order_by(Team.name).all()
    stats = []
    for t in teams:
        roles = [r for r in t.roles if r.active]
        stats.append({"team": t, "roles": len(roles),
                      "validated": sum(r.is_validated for r in roles),
                      "employees": db.query(User).filter_by(team_id=t.id, active=True).count()})
    no_role = db.query(User).filter(User.active.is_(True), User.role_id.is_(None)).count()
    return _page(request, "admin/dashboard.html", me, by_status=by_status, mismatches=mismatches,
                 stats=stats, no_role=no_role, areas=len(active_areas(db)),
                 cycles=db.query(Cycle).filter_by(active=True).all())


# --- framework areas ----------------------------------------------------------------

@router.get("/areas")
def areas(request: Request, me: User = Depends(admin_user), db: Session = Depends(get_db)):
    return _page(request, "admin/areas.html", me,
                 areas=db.query(Area).order_by(Area.sort_order, Area.code).all(),
                 types=AREA_TYPES, guides={g.type: g.prompt for g in db.query(EvidenceGuide)})


def _area_from_form(area: Area, form):
    area.code = form["code"].strip().upper()
    area.type = form["type"] if form["type"] in AREA_TYPES else "Knowledge"
    area.name = form["name"].strip()
    area.definition = form.get("definition", "").strip()
    area.observable = form.get("observable", "").strip()
    area.evidence_example = form.get("evidence_example", "").strip()
    area.critical_control = _bool(form.get("critical_control"))
    area.active = _bool(form.get("active"))
    try:
        area.sort_order = int(form.get("sort_order") or 0)
    except ValueError:
        pass


@router.post("/areas")
async def area_create(request: Request, me: User = Depends(admin_user),
                      db: Session = Depends(get_db)):
    form = await request.form()
    a = Area()
    _area_from_form(a, form)
    if not a.code or not a.name:
        flash(request, "Code and name are required.", "error")
        return redirect("/admin/areas")
    if not a.sort_order:
        a.sort_order = (db.query(func.max(Area.sort_order)).scalar() or 0) + 1
    db.add(a)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        flash(request, f"Area code {a.code} already exists.", "error")
        return redirect("/admin/areas")
    audit(db, me, "area.create", a.code, a.name)
    db.commit()
    flash(request, f"Area {a.code} added. Set its required level per role in Teams & roles.",
          "success")
    return redirect("/admin/areas")


@router.get("/areas/{area_id}")
def area_edit(area_id: int, request: Request, me: User = Depends(admin_user),
              db: Session = Depends(get_db)):
    return _page(request, "admin/area_edit.html", me, area=db.get(Area, area_id), types=AREA_TYPES)


@router.post("/areas/{area_id}")
async def area_update(area_id: int, request: Request, me: User = Depends(admin_user),
                      db: Session = Depends(get_db)):
    a = db.get(Area, area_id)
    form = await request.form()
    if form.get("action") == "delete":
        used = db.query(Response).filter(Response.area_id == a.id,
                                         (Response.self_level.isnot(None))
                                         | (Response.validated_level.isnot(None))).count()
        if used:
            flash(request, f"{a.code} has assessment data and cannot be deleted. Deactivate it "
                           "instead (history is kept).", "error")
            return redirect(f"/admin/areas/{area_id}")
        db.query(Response).filter_by(area_id=a.id).delete()
        db.query(RoleRequirement).filter_by(area_id=a.id).delete()
        audit(db, me, "area.delete", a.code)
        db.delete(a)
        db.commit()
        flash(request, "Area deleted.", "success")
        return redirect("/admin/areas")
    _area_from_form(a, form)
    try:
        audit(db, me, "area.update", a.code)
        db.commit()
    except IntegrityError:
        db.rollback()
        flash(request, "That code is already used.", "error")
        return redirect(f"/admin/areas/{area_id}")
    flash(request, f"{a.code} saved.", "success")
    return redirect("/admin/areas")


@router.post("/evidence")
async def evidence_update(request: Request, me: User = Depends(admin_user),
                          db: Session = Depends(get_db)):
    form = await request.form()
    for t in AREA_TYPES:
        g = db.get(EvidenceGuide, t) or EvidenceGuide(type=t, prompt="")
        g.prompt = (form.get(f"guide_{t}") or "").strip()
        db.add(g)
    audit(db, me, "evidence.update")
    db.commit()
    flash(request, "Evidence guidance saved.", "success")
    return redirect("/admin/areas")


# --- proficiency scale --------------------------------------------------------------

@router.get("/scale")
def scale_form(request: Request, me: User = Depends(admin_user), db: Session = Depends(get_db)):
    levels = {s.level: s for s in db.query(ScaleLevel)}
    return _page(request, "admin/scale.html", me,
                 levels=[levels.get(i) or ScaleLevel(level=i, label="") for i in range(5)])


@router.post("/scale")
async def scale_save(request: Request, me: User = Depends(admin_user),
                     db: Session = Depends(get_db)):
    form = await request.form()
    for i in range(5):
        s = db.get(ScaleLevel, i) or ScaleLevel(level=i)
        s.label = form.get(f"label_{i}", "").strip()
        s.knowledge = form.get(f"knowledge_{i}", "").strip()
        s.skill = form.get(f"skill_{i}", "").strip()
        s.competency = form.get(f"competency_{i}", "").strip()
        s.jd_wording = form.get(f"jd_{i}", "").strip()
        db.add(s)
    audit(db, me, "scale.update")
    db.commit()
    flash(request, "Proficiency scale saved.", "success")
    return redirect("/admin/scale")


# --- teams & roles ------------------------------------------------------------------

@router.get("/teams")
def teams(request: Request, me: User = Depends(admin_user), db: Session = Depends(get_db)):
    return _page(request, "admin/teams.html", me, teams=db.query(Team).order_by(Team.name).all())


@router.post("/teams")
def team_create(request: Request, name: str = Form(...), description: str = Form(""),
                me: User = Depends(admin_user), db: Session = Depends(get_db)):
    if db.query(Team).filter_by(name=name.strip()).first():
        flash(request, "A team with that name already exists.", "error")
        return redirect("/admin/teams")
    t = Team(name=name.strip(), description=description.strip())
    db.add(t)
    audit(db, me, "team.create", t.name)
    db.commit()
    flash(request, f"Team {t.name} created. Next: add roles (or import a role matrix), then "
                   "import employees.", "success")
    return redirect(f"/admin/teams/{t.id}")


@router.get("/teams/{team_id}")
def team_detail(team_id: int, request: Request, me: User = Depends(admin_user),
                db: Session = Depends(get_db)):
    t = db.get(Team, team_id)
    return _page(request, "admin/team.html", me, team=t, areas=active_areas(db),
                 roles=sorted(t.roles, key=lambda r: (r.sort_order, r.title)),
                 statuses=ROLE_VALIDATION,
                 employees=db.query(User).filter_by(team_id=t.id).count())


@router.post("/teams/{team_id}")
async def team_update(team_id: int, request: Request, me: User = Depends(admin_user),
                      db: Session = Depends(get_db)):
    t = db.get(Team, team_id)
    form = await request.form()
    action = form.get("action")
    if action == "matrix":
        areas = active_areas(db)
        changed = 0
        for role in t.roles:
            existing = {r.area_id: r for r in role.requirements}
            for a in areas:
                key = f"req_{role.id}_{a.id}"
                if key not in form:
                    continue
                try:
                    lvl = int(form[key])
                except ValueError:
                    continue
                if not 0 <= lvl <= 4:
                    continue
                if a.id in existing:
                    if existing[a.id].level != lvl:
                        existing[a.id].level = lvl
                        changed += 1
                else:
                    role.requirements.append(RoleRequirement(area_id=a.id, level=lvl))
                    changed += 1
        audit(db, me, "matrix.update", t.name, f"{changed} cells changed")
        db.commit()
        flash(request, f"Requirement matrix saved ({changed} change(s)). Open (non-finalised) "
                       "assessments pick up the new levels automatically.", "success")
        return redirect(f"/admin/teams/{team_id}#matrix")
    if action == "add_role":
        title = (form.get("title") or "").strip()
        if not title or db.query(Role).filter_by(team_id=t.id, title=title).first():
            flash(request, "Enter a unique role title.", "error")
            return redirect(f"/admin/teams/{team_id}")
        order = (db.query(func.max(Role.sort_order)).filter_by(team_id=t.id).scalar() or 0) + 1
        r = Role(team=t, title=title, family=(form.get("family") or "").strip(), sort_order=order)
        db.add(r)
        audit(db, me, "role.create", f"{t.name}/{title}")
        db.commit()
        flash(request, f"Role '{title}' added with all levels at 0. Set its levels in the "
                       "matrix below.", "success")
        return redirect(f"/admin/teams/{team_id}#matrix")
    t.name = (form.get("name") or t.name).strip()
    t.description = (form.get("description") or "").strip()
    t.active = _bool(form.get("active"))
    audit(db, me, "team.update", t.name)
    db.commit()
    flash(request, "Team saved.", "success")
    return redirect(f"/admin/teams/{team_id}")


@router.get("/teams/{team_id}/matrix.xlsx")
def team_matrix_export(team_id: int, me: User = Depends(admin_user),
                       db: Session = Depends(get_db)):
    t = db.get(Team, team_id)
    return _xlsx(export_role_matrix(db, t), f"{t.name}_Role_Requirements.xlsx")


@router.post("/teams/{team_id}/import-roles")
async def team_import_roles(team_id: int, request: Request, file: UploadFile = File(...),
                            me: User = Depends(admin_user), db: Session = Depends(get_db)):
    t = db.get(Team, team_id)
    try:
        rep = import_role_matrix(db, load_workbook(await file.read()), t)
    except Exception as e:  # noqa: BLE001 - surface parsing errors to the admin
        db.rollback()
        flash(request, f"Import failed: {e}", "error")
        return redirect(f"/admin/teams/{team_id}")
    audit(db, me, "roles.import", t.name, rep.summary())
    db.commit()
    flash(request, f"Roles imported: {rep.summary()}.", "success")
    for m in rep.messages[:10]:
        flash(request, m, "warning")
    return redirect(f"/admin/teams/{team_id}")


@router.get("/roles/{role_id}")
def role_edit(role_id: int, request: Request, me: User = Depends(admin_user),
              db: Session = Depends(get_db)):
    r = db.get(Role, role_id)
    return _page(request, "admin/role_edit.html", me, role=r, statuses=ROLE_VALIDATION,
                 holders=db.query(User).filter_by(role_id=r.id).all())


@router.post("/roles/{role_id}")
async def role_update(role_id: int, request: Request, me: User = Depends(admin_user),
                      db: Session = Depends(get_db)):
    r = db.get(Role, role_id)
    form = await request.form()
    if form.get("action") == "delete":
        if db.query(User).filter_by(role_id=r.id).count() or \
                db.query(Assessment).filter_by(role_id=r.id).count():
            flash(request, "This role has employees or assessments. Deactivate it instead.",
                  "error")
            return redirect(f"/admin/roles/{role_id}")
        team_id = r.team_id
        audit(db, me, "role.delete", r.title)
        db.delete(r)
        db.commit()
        flash(request, "Role deleted.", "success")
        return redirect(f"/admin/teams/{team_id}")
    title = (form.get("title") or "").strip()
    if title:
        r.title = title
    r.family = (form.get("family") or "").strip()
    new_status = form.get("validation_status")
    if new_status in ROLE_VALIDATION:
        if new_status == "Validated" and not r.is_validated:
            r.validated_on = date.today()
        r.validation_status = new_status
    r.validated_by = (form.get("validated_by") or "").strip()
    r.rationale = (form.get("rationale") or "").strip()
    r.reviewer_comment = (form.get("reviewer_comment") or "").strip()
    r.active = _bool(form.get("active"))
    try:
        audit(db, me, "role.update", r.title, r.validation_status)
        db.commit()
    except IntegrityError:
        db.rollback()
        flash(request, "Another role in this team already has that title.", "error")
        return redirect(f"/admin/roles/{role_id}")
    flash(request, "Role saved.", "success")
    return redirect(f"/admin/teams/{r.team_id}")


@router.post("/teams/{team_id}/validate")
def team_bulk_validate(team_id: int, request: Request, validated_by: str = Form(...),
                       me: User = Depends(admin_user), db: Session = Depends(get_db)):
    """Record management sign-off for all roles of a team after the calibration workshop."""
    t = db.get(Team, team_id)
    n = 0
    for r in t.roles:
        if r.active and not r.is_validated:
            r.validation_status, r.validated_by, r.validated_on = "Validated", validated_by, date.today()
            n += 1
    audit(db, me, "roles.validate_all", t.name, f"{n} roles by {validated_by}")
    db.commit()
    flash(request, f"{n} role(s) marked as Validated by {validated_by}.", "success")
    return redirect(f"/admin/teams/{team_id}")


# --- employees ----------------------------------------------------------------------

@router.get("/users")
def users(request: Request, team_id: int | None = None, q: str = "",
          me: User = Depends(admin_user), db: Session = Depends(get_db)):
    query = db.query(User)
    if team_id:
        query = query.filter(User.team_id == team_id)
    if q:
        like = f"%{q.lower()}%"
        query = query.filter(func.lower(User.name).like(like) | func.lower(User.email).like(like))
    return _page(request, "admin/users.html", me, users=query.order_by(User.name).all(),
                 teams=db.query(Team).order_by(Team.name).all(), team_id=team_id, q=q,
                 credentials=request.session.pop("credentials", []))


def _user_form_ctx(db, user):
    return {"user": user, "teams": db.query(Team).order_by(Team.name).all(),
            "roles": db.query(Role).filter_by(active=True).order_by(Role.title).all(),
            "managers": db.query(User).filter_by(active=True).order_by(User.name).all()}


@router.get("/users/new")
def user_new(request: Request, me: User = Depends(admin_user), db: Session = Depends(get_db)):
    return _page(request, "admin/user_edit.html", me, **_user_form_ctx(db, None))


@router.get("/users/{user_id}")
def user_edit(user_id: int, request: Request, me: User = Depends(admin_user),
              db: Session = Depends(get_db)):
    return _page(request, "admin/user_edit.html", me, **_user_form_ctx(db, db.get(User, user_id)))


def _opt_int(v):
    try:
        return int(v) if v else None
    except ValueError:
        return None


@router.post("/users/{user_id}")
async def user_save(user_id: str, request: Request, me: User = Depends(admin_user),
                    db: Session = Depends(get_db)):
    form = await request.form()
    new = user_id == "new"
    u = User() if new else db.get(User, int(user_id))
    action = form.get("action", "save")
    if action == "reset" and not new:
        pwd = temp_password()
        u.password_hash, u.must_change_password = hash_password(pwd), True
        audit(db, me, "user.reset_password", u.email)
        db.commit()
        request.session["credentials"] = [[u.email, pwd]]
        flash(request, "Temporary password generated (shown once below).", "success")
        return redirect("/admin/users")
    u.employee_id = (form.get("employee_id") or "").strip()
    u.name = (form.get("name") or "").strip()
    u.email = (form.get("email") or "").strip().lower()
    u.team_id = _opt_int(form.get("team_id"))
    u.role_id = _opt_int(form.get("role_id"))
    mid = _opt_int(form.get("manager_id"))
    u.manager_id = mid if mid != u.id else None
    if u.role_id and u.team_id and db.get(Role, u.role_id).team_id != u.team_id:
        flash(request, "The selected role belongs to another team.", "error")
        db.rollback()
        return redirect(f"/admin/users/{user_id}")
    u.is_admin = _bool(form.get("is_admin")) or (u.id == me.id)  # cannot remove own admin
    u.is_calibrator = _bool(form.get("is_calibrator"))
    u.active = _bool(form.get("active")) or (u.id == me.id)
    if not (u.employee_id and u.name and u.email):
        flash(request, "Employee ID, name and email are required.", "error")
        db.rollback()
        return redirect(f"/admin/users/{user_id}")
    creds = []
    if new:
        pwd = temp_password()
        u.password_hash, u.must_change_password = hash_password(pwd), True
        creds = [[u.email, pwd]]
        db.add(u)
    try:
        db.flush()
        audit(db, me, "user.create" if new else "user.update", u.email)
        db.commit()
    except IntegrityError:
        db.rollback()
        flash(request, "Employee ID or email is already used.", "error")
        return redirect(f"/admin/users/{user_id}")
    if creds:
        request.session["credentials"] = creds
    flash(request, f"{u.name} saved.", "success")
    return redirect("/admin/users")


@router.post("/users-import")
async def users_import(request: Request, team_id: int = Form(...), file: UploadFile = File(...),
                       me: User = Depends(admin_user), db: Session = Depends(get_db)):
    t = db.get(Team, team_id)
    try:
        rep = import_employees(db, t, file.filename or "", await file.read())
    except Exception as e:  # noqa: BLE001
        db.rollback()
        flash(request, f"Import failed: {e}", "error")
        return redirect("/admin/users")
    audit(db, me, "users.import", t.name, rep.summary())
    db.commit()
    request.session["credentials"] = [list(c) for c in rep.credentials]
    flash(request, f"Employees imported into {t.name}: {rep.summary()}.", "success")
    for m in rep.messages[:10]:
        flash(request, m, "warning")
    return redirect(f"/admin/users?team_id={team_id}")


@router.get("/templates/employees.xlsx")
def tpl_employees(me: User = Depends(admin_user)):
    return _xlsx(export_employee_template(), "Employee_Import_Template.xlsx")


@router.get("/templates/roles.xlsx")
def tpl_roles(me: User = Depends(admin_user), db: Session = Depends(get_db)):
    return _xlsx(export_role_matrix(db, None), "Role_Requirements_Template.xlsx")


# --- cycles -------------------------------------------------------------------------

@router.get("/cycles")
def cycles(request: Request, me: User = Depends(admin_user), db: Session = Depends(get_db)):
    data = []
    for c in db.query(Cycle).order_by(Cycle.id.desc()):
        counts = dict(db.query(Assessment.status, func.count()).filter_by(cycle_id=c.id)
                      .group_by(Assessment.status).all())
        data.append((c, counts))
    return _page(request, "admin/cycles.html", me, cycles=data)


@router.post("/cycles")
def cycle_create(request: Request, name: str = Form(...), start_date: str = Form(""),
                 end_date: str = Form(""), me: User = Depends(admin_user),
                 db: Session = Depends(get_db)):
    if db.query(Cycle).filter_by(name=name.strip()).first():
        flash(request, "A cycle with that name exists.", "error")
        return redirect("/admin/cycles")
    for c in db.query(Cycle).filter_by(active=True):
        c.active = False
    c = Cycle(name=name.strip(), active=True,
              start_date=date.fromisoformat(start_date) if start_date else None,
              end_date=date.fromisoformat(end_date) if end_date else None)
    db.add(c)
    audit(db, me, "cycle.create", c.name)
    db.commit()
    flash(request, f"Cycle '{c.name}' created and set as the active cycle.", "success")
    return redirect("/admin/cycles")


@router.post("/cycles/{cycle_id}")
def cycle_toggle(cycle_id: int, request: Request, me: User = Depends(admin_user),
                 db: Session = Depends(get_db)):
    c = db.get(Cycle, cycle_id)
    if not c.active:
        for other in db.query(Cycle).filter_by(active=True):
            other.active = False
    c.active = not c.active
    audit(db, me, "cycle.toggle", c.name, str(c.active))
    db.commit()
    return redirect("/admin/cycles")


# --- workbook import ------------------------------------------------------------------

@router.get("/import")
def import_form(request: Request, me: User = Depends(admin_user), db: Session = Depends(get_db)):
    return _page(request, "admin/import.html", me, teams=db.query(Team).order_by(Team.name).all())


@router.post("/import")
async def import_workbook(request: Request, file: UploadFile = File(...),
                          parts: list[str] = Form([]), team_id: str = Form(""),
                          new_team: str = Form(""), me: User = Depends(admin_user),
                          db: Session = Depends(get_db)):
    try:
        wb = load_workbook(await file.read())
    except Exception as e:  # noqa: BLE001
        flash(request, f"Could not read the workbook: {e}", "error")
        return redirect("/admin/import")
    msgs = []
    if "framework" in parts:
        msgs.append(f"Framework areas: {import_framework(db, wb).summary()}")
    if "scale" in parts:
        msgs.append(f"Proficiency scale: {import_scale(db, wb).summary()}")
    if "roles" in parts:
        team = db.get(Team, int(team_id)) if team_id else None
        if not team and new_team.strip():
            team = db.query(Team).filter_by(name=new_team.strip()).first() or Team(name=new_team.strip())
            db.add(team)
            db.flush()
        if not team:
            db.rollback()
            flash(request, "Select or name the team for the role matrix.", "error")
            return redirect("/admin/import")
        rep = import_role_matrix(db, wb, team)
        msgs.append(f"Roles for {team.name}: {rep.summary()}")
        msgs += rep.messages
    audit(db, me, "workbook.import", file.filename or "", "; ".join(msgs))
    db.commit()
    for m in msgs:
        flash(request, m, "success")
    return redirect("/admin")


# --- assessments & audit ------------------------------------------------------------

@router.get("/assessments")
def assessments(request: Request, cycle_id: int | None = None, status: str = "",
                me: User = Depends(admin_user), db: Session = Depends(get_db)):
    q = db.query(Assessment)
    if cycle_id:
        q = q.filter(Assessment.cycle_id == cycle_id)
    if status:
        q = q.filter(Assessment.status == status)
    return _page(request, "admin/assessments.html", me,
                 items=q.order_by(Assessment.id.desc()).limit(500).all(),
                 cycles=db.query(Cycle).order_by(Cycle.id.desc()).all(),
                 cycle_id=cycle_id, status=status)


@router.post("/assessments/{aid}/delete")
def assessment_delete(aid: int, request: Request, me: User = Depends(admin_user),
                      db: Session = Depends(get_db)):
    a = db.get(Assessment, aid)
    audit(db, me, "assessment.delete", a.code, a.employee.email)
    db.delete(a)
    db.commit()
    flash(request, f"Assessment {a.code} deleted.", "success")
    return redirect("/admin/assessments")


@router.get("/audit")
def audit_log(request: Request, me: User = Depends(admin_user), db: Session = Depends(get_db)):
    return _page(request, "admin/audit.html", me,
                 items=db.query(AuditLog).order_by(AuditLog.id.desc()).limit(500).all())
