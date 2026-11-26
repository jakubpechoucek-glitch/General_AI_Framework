"""Employee Gap Summary, Team Gap Summary and Excel exports."""
from __future__ import annotations

import io
from collections import defaultdict

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy.orm import Session

from . import logic
from .importer import EMPLOYEE_COLUMNS
from .models import Area, Assessment, Cycle, Role, Team, User
from .services import active_areas, rows_for, sorted_responses

FILL = {logic.CRITICAL: "F8D7DA", logic.DEVELOPMENT: "FFE5CC", logic.MEETS: "D4EDDA",
        logic.EXCEEDS: "D6E4FF", logic.NOT_ASSESSED: "E9ECEF", logic.NOT_REQUIRED: "E9ECEF"}


def assessments_for(db: Session, users: list[User], cycle: Cycle | None,
                    finalized_only: bool = True) -> dict[int, Assessment]:
    if not cycle or not users:
        return {}
    q = db.query(Assessment).filter(Assessment.cycle_id == cycle.id,
                                    Assessment.employee_id.in_([u.id for u in users]))
    if finalized_only:
        q = q.filter(Assessment.status == "Finalized")
    return {a.employee_id: a for a in q}


def employee_summaries(db: Session, users: list[User], cycle: Cycle | None):
    all_a = assessments_for(db, users, cycle, finalized_only=False)
    out = []
    for u in sorted(users, key=lambda x: x.name):
        a = all_a.get(u.id)
        official = a if a and a.status == "Finalized" else None
        out.append({"user": u, "assessment": a,
                    "summary": logic.summarize(rows_for(official)) if official else None})
    return out


def _bucket():
    return {"assessed": 0, "meets": 0, "gap1": 0, "gap2": 0, "gap_total": 0,
            "employees": set()}


def _add(b, row: logic.Row, emp_id: int):
    if row.required == 0 or row.validated is None:
        return
    b["assessed"] += 1
    b["employees"].add(emp_id)
    g = row.gap or 0
    b["gap_total"] += g
    b["meets" if g == 0 else "gap1" if g == 1 else "gap2"] += 1


def _finish(b):
    b["employees"] = len(b["employees"])
    b["meets_pct"] = b["meets"] / b["assessed"] if b["assessed"] else None
    b["avg_gap"] = b["gap_total"] / b["assessed"] if b["assessed"] else None
    return b


def team_summary(db: Session, users: list[User], cycle: Cycle | None):
    finals = assessments_for(db, users, cycle, finalized_only=True)
    by_area: dict[str, dict] = defaultdict(_bucket)
    by_role: dict[str, dict] = defaultdict(_bucket)
    by_family: dict[str, dict] = defaultdict(_bucket)
    by_type: dict[str, dict] = defaultdict(_bucket)
    area_meta = {a.code: a for a in db.query(Area).all()}
    for emp_id, a in finals.items():
        for row in rows_for(a):
            _add(by_area[row.code], row, emp_id)
            _add(by_role[a.role.title], row, emp_id)
            _add(by_family[a.role.family or "—"], row, emp_id)
            _add(by_type[row.type], row, emp_id)
    areas = []
    for code in sorted(by_area, key=lambda c: (area_meta[c].sort_order if c in area_meta else 0, c)):
        b = _finish(by_area[code])
        b["code"], b["area"] = code, area_meta.get(code)
        areas.append(b)
    # most common gaps: rank by share of employees with a gap, then 2+ gaps
    top = sorted([b for b in areas if b["assessed"]],
                 key=lambda b: (-(b["gap1"] + b["gap2"]) / b["assessed"], -b["gap2"]))[:5]
    return {
        "employees_total": len(users),
        "employees_finalized": len(finals),
        "areas": areas,
        "roles": {k: _finish(v) for k, v in sorted(by_role.items())},
        "families": {k: _finish(v) for k, v in sorted(by_family.items())},
        "types": {k: _finish(by_type[k]) for k in ("Knowledge", "Skill", "Competency")
                  if k in by_type},
        "top_gaps": [b for b in top if b["gap1"] + b["gap2"] > 0],
    }


# --- Excel ------------------------------------------------------------------------

def _sheet(wb, title, header, rows, widths=None):
    ws = wb.create_sheet(title)
    ws.append(header)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1F3A5F")
        c.alignment = Alignment(wrap_text=True, vertical="top")
    for r in rows:
        ws.append(r)
    ws.freeze_panes = "A2"
    for i, _ in enumerate(header, 1):
        ws.column_dimensions[get_column_letter(i)].width = (widths or {}).get(i, 16)
    return ws


def _bytes(wb) -> bytes:
    if "Sheet" in wb.sheetnames and len(wb.sheetnames) > 1:
        del wb["Sheet"]
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


ASSESSMENT_HEADER = ["Assessment ID", "Cycle", "Employee ID", "Employee Name", "Employee Email",
                     "Role Family", "Role Title", "Role Validation Status", "Manager Email",
                     "KSC Code", "Type", "Area", "Required Level", "Self Level", "Self Evidence",
                     "Evidence Link", "Confidence", "Manager Level", "Manager Comment",
                     "Validated Current Level", "Self Gap", "Development Gap", "Surplus",
                     "Priority Score", "Status", "Assessment Date", "Validation Date",
                     "Next Review Date", "Record Status", "Version"]


def export_report(db: Session, users: list[User], cycle: Cycle | None) -> bytes:
    wb = openpyxl.Workbook()
    alls = assessments_for(db, users, cycle, finalized_only=False)
    rows = []
    for a in sorted(alls.values(), key=lambda x: x.employee.name):
        for r in sorted_responses(a):
            st = logic.status(r.required_level, r.validated_level)
            rows.append([
                a.code, a.cycle.name, a.employee.employee_id, a.employee.name, a.employee.email,
                a.role.family, a.role.title, a.role.validation_status,
                a.manager.email if a.manager else "", r.area.code, r.area.type, r.area.name,
                r.required_level, r.self_level, r.self_evidence, r.evidence_link, r.confidence,
                r.manager_level, r.manager_comment, r.validated_level,
                logic.self_gap(r.required_level, r.self_level),
                logic.development_gap(r.required_level, r.validated_level),
                logic.surplus(r.required_level, r.validated_level),
                logic.priority_score(r.required_level, r.validated_level), st,
                a.assessment_date, a.validation_date, a.next_review_date, a.status, a.version])
    ws = _sheet(wb, "Employee Assessment", ASSESSMENT_HEADER, rows, {4: 24, 7: 30, 12: 34, 15: 40})
    st_col = ASSESSMENT_HEADER.index("Status") + 1
    for row in ws.iter_rows(min_row=2):
        c = row[st_col - 1]
        if c.value in FILL:
            c.fill = PatternFill("solid", fgColor=FILL[c.value])

    emp_rows = []
    for e in employee_summaries(db, users, cycle):
        s, u, a = e["summary"], e["user"], e["assessment"]
        emp_rows.append([
            u.employee_id, u.name, u.role.family if u.role else "", u.role.title if u.role else "",
            a.status if a else "Not started",
            s.required_areas if s else None, s.assessed if s else None,
            round(s.completion * 100) if s else None, s.meets if s else None,
            s.gap1 if s else None, s.gap2 if s else None,
            round(s.avg_gap, 2) if s and s.avg_gap is not None else None,
            ", ".join(f"{r.code} {r.name}" for r in s.critical_control_gaps) if s else "",
            "; ".join(f"{r.code} {r.name} (gap {r.gap})" for r in s.priorities) if s else ""])
    _sheet(wb, "Employee Gap Summary",
           ["Employee ID", "Employee", "Role Family", "Role", "Record Status", "Required Areas",
            "Assessed", "Completion %", "Meets", "Gap 1", "Gap 2+", "Avg Gap",
            "Critical-control gaps", "Priority Development Areas"], emp_rows,
           {2: 24, 4: 30, 13: 40, 14: 70})

    t = team_summary(db, users, cycle)

    def pct(v):
        return round(v * 100) if v is not None else None

    _sheet(wb, "Team Gap by Area",
           ["Code", "Type", "Area", "Employees Assessed", "Meets", "Gap 1", "Gap 2+", "Meets %",
            "Avg Gap"],
           [[b["code"], b["area"].type if b["area"] else "", b["area"].name if b["area"] else "",
             b["employees"], b["meets"], b["gap1"], b["gap2"], pct(b["meets_pct"]),
             round(b["avg_gap"], 2) if b["avg_gap"] is not None else None] for b in t["areas"]],
           {3: 36})
    for title, key, label in (("Team Gap by Role", "roles", "Role"),
                              ("Team Gap by Role Family", "families", "Role Family"),
                              ("Team Gap by Type", "types", "Type")):
        _sheet(wb, title, [label, "Employees", "Ratings", "Meets", "Gap 1", "Gap 2+", "Meets %",
                           "Avg Gap"],
               [[k, b["employees"], b["assessed"], b["meets"], b["gap1"], b["gap2"],
                 pct(b["meets_pct"]), round(b["avg_gap"], 2) if b["avg_gap"] is not None else None]
                for k, b in t[key].items()], {1: 36})
    return _bytes(wb)


def export_role_matrix(db: Session, team: Team | None) -> bytes:
    """Role matrix in the importable layout. With team=None it is an empty template."""
    wb = openpyxl.Workbook()
    areas = active_areas(db)
    header = (["Role Family", "Role Title"] + [f"{a.code} | {a.name}" for a in areas]
              + ["Validation Status", "Proposal rationale / assumptions", "Reviewer comments"])
    rows = []
    roles = (db.query(Role).filter_by(team_id=team.id).order_by(Role.sort_order).all()
             if team else [])
    for r in roles:
        req = r.required_map()
        rows.append([r.family, r.title] + [req.get(a.id, 0) for a in areas]
                    + [r.validation_status, r.rationale, r.reviewer_comment])
    if not team:
        rows.append(["Example family", "Example Role Title"] + [0] * len(areas)
                    + ["Draft — title-based proposal", "", ""])
    _sheet(wb, "Role Requirements", header, rows, {1: 22, 2: 34})
    return _bytes(wb)


def export_employee_template() -> bytes:
    wb = openpyxl.Workbook()
    _sheet(wb, "Employees", EMPLOYEE_COLUMNS,
           [["10001", "Jane Example", "jane.example@company.com", "CRM Campaign Manager",
             "manager@company.com", "N", "N"]], {2: 24, 3: 32, 4: 32, 5: 32})
    return _bytes(wb)
