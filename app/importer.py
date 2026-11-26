"""Excel / CSV import: framework, proficiency scale, role matrices and employee lists.

The role-matrix import accepts the layout of the 'CRM KSC Role Rating' sheet: a header
row with 'Role Family', 'Role Title', one column per area whose header starts with the
area code (e.g. 'K01 | AI fundamentals'), and optional 'Validation Status',
'Proposal rationale / assumptions' and 'Reviewer comments' columns. The same layout is
produced by the downloadable template, so new teams can be onboarded the same way.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field

import openpyxl
from sqlalchemy.orm import Session

from .auth import hash_password, temp_password
from .models import Area, EvidenceGuide, Role, RoleRequirement, ScaleLevel, Team, User

CODE_RE = re.compile(r"^\s*([KSC]\d{2})\b")
DEFAULT_CRITICAL = {"K06", "S05", "C05", "C06"}
DEFAULT_EVIDENCE = {
    "Knowledge": "Show what you understand: a short knowledge check, an explanation of the "
                 "concept, a relevant completed course, or correctly recognising risks or a "
                 "suitable AI approach.",
    "Skill": "Show what you can actually do: a prompt you created, an AI-assisted analysis, "
             "a validated AI output, an automation you built, or a research or content "
             "output. A course completion alone does not prove a Skill.",
    "Competency": "Show application in your work context: a delivered use case, a process "
                  "change, a decision supported by AI, benefit against a baseline, controls "
                  "you introduced, or a way of working you spread across the team.",
}


@dataclass
class ImportReport:
    created: int = 0
    updated: int = 0
    skipped: int = 0
    messages: list[str] = field(default_factory=list)
    credentials: list[tuple[str, str]] = field(default_factory=list)

    def summary(self) -> str:
        return f"{self.created} created, {self.updated} updated, {self.skipped} skipped"


def _s(v) -> str:
    return "" if v is None else str(v).strip()


def _norm(v) -> str:
    return re.sub(r"[^a-z0-9]", "", _s(v).lower())


def load_workbook(data: bytes):
    return openpyxl.load_workbook(io.BytesIO(data), data_only=True)


# --- framework ------------------------------------------------------------------

def import_framework(db: Session, wb) -> ImportReport:
    rep = ImportReport()
    ws = wb["General AI Framework"] if "General AI Framework" in wb.sheetnames else None
    if ws is None:
        rep.messages.append("Sheet 'General AI Framework' not found.")
        return rep
    header_row = None
    for row in ws.iter_rows(min_row=1, max_row=30):
        if _norm(row[0].value) == "type" and _norm(row[1].value) == "code":
            header_row = row[0].row
            break
    if header_row is None:
        rep.messages.append("Header row 'Type | Code | Area ...' not found.")
        return rep
    order = 0
    for row in ws.iter_rows(min_row=header_row + 1, values_only=True):
        typ, code, name = _s(row[0]), _s(row[1]), _s(row[2])
        if not CODE_RE.match(code) or typ not in ("Knowledge", "Skill", "Competency"):
            continue
        order += 1
        area = db.query(Area).filter_by(code=code).one_or_none()
        if area is None:
            area = Area(code=code, critical_control=code in DEFAULT_CRITICAL)
            db.add(area)
            rep.created += 1
        else:
            rep.updated += 1
        area.type, area.name = typ, name
        area.definition = _s(row[3]) if len(row) > 3 else ""
        area.observable = _s(row[4]) if len(row) > 4 else ""
        area.evidence_example = _s(row[5]) if len(row) > 5 else ""
        area.sort_order = order
        area.active = True
    for t, p in DEFAULT_EVIDENCE.items():
        if db.get(EvidenceGuide, t) is None:
            db.add(EvidenceGuide(type=t, prompt=p))
    db.flush()
    return rep


def _split_anchor(text: str) -> dict[str, str]:
    parts = re.split(r"(Knowledge|Skill|Competency):", text)
    out = {}
    for i in range(1, len(parts) - 1, 2):
        out[parts[i]] = parts[i + 1].strip().rstrip(".") + "."
    if not out:
        out = {"Knowledge": text, "Skill": text, "Competency": text}
    return out


def import_scale(db: Session, wb) -> ImportReport:
    rep = ImportReport()
    if "Proficiency Scale" not in wb.sheetnames:
        rep.messages.append("Sheet 'Proficiency Scale' not found.")
        return rep
    for row in wb["Proficiency Scale"].iter_rows(values_only=True):
        if not isinstance(row[0], (int, float)) or not 0 <= int(row[0]) <= 4:
            continue
        lvl = int(row[0])
        anchors = _split_anchor(_s(row[2]))
        sl = db.get(ScaleLevel, lvl)
        if sl is None:
            sl = ScaleLevel(level=lvl)
            db.add(sl)
            rep.created += 1
        else:
            rep.updated += 1
        sl.label = _s(row[1])
        sl.knowledge = anchors.get("Knowledge", "")
        sl.skill = anchors.get("Skill", "")
        sl.competency = anchors.get("Competency", "")
        sl.jd_wording = _s(row[3]) if len(row) > 3 else ""
    db.flush()
    return rep


# --- role matrix ------------------------------------------------------------------

def _find_matrix(wb):
    """Return (worksheet, header_row_index, column map) of the first role matrix found."""
    preferred = [n for n in wb.sheetnames if "ksc" in n.lower()] + wb.sheetnames
    for name in preferred:
        ws = wb[name]
        for row in ws.iter_rows(min_row=1, max_row=40):
            labels = [_norm(c.value) for c in row]
            if "roletitle" in labels and any(CODE_RE.match(_s(c.value)) for c in row):
                cols = {"codes": {}}
                for c in row:
                    n, raw = _norm(c.value), _s(c.value)
                    m = CODE_RE.match(raw)
                    if m:
                        cols["codes"][m.group(1)] = c.column - 1
                    elif n == "rolefamily":
                        cols["family"] = c.column - 1
                    elif n == "roletitle":
                        cols["title"] = c.column - 1
                    elif n.startswith("validationstatus"):
                        cols["status"] = c.column - 1
                    elif n.startswith("proposalrationale") or n.startswith("rationale"):
                        cols["rationale"] = c.column - 1
                    elif n.startswith("reviewercomment"):
                        cols["comment"] = c.column - 1
                return ws, row[0].row, cols
    return None, None, None


def import_role_matrix(db: Session, wb, team: Team) -> ImportReport:
    rep = ImportReport()
    ws, header, cols = _find_matrix(wb)
    if ws is None:
        rep.messages.append("No role matrix found (need a header with 'Role Title' and area "
                            "code columns such as 'K01 | AI fundamentals').")
        return rep
    areas = {a.code: a for a in db.query(Area).all()}
    unknown = sorted(set(cols["codes"]) - set(areas))
    if unknown:
        rep.messages.append(f"Ignored unknown area codes: {', '.join(unknown)}. "
                            "Add them in Framework first.")
    order = db.query(Role).filter_by(team_id=team.id).count()
    for row in ws.iter_rows(min_row=header + 1, values_only=True):
        title = _s(row[cols["title"]])
        if not title:
            continue
        levels = {}
        bad = False
        for code, idx in cols["codes"].items():
            if code not in areas:
                continue
            v = row[idx] if idx < len(row) else None
            if v is None or _s(v) == "":
                v = 0
            try:
                v = int(float(v))
            except (TypeError, ValueError):
                bad = True
                break
            if not 0 <= v <= 4:
                bad = True
                break
            levels[code] = v
        if bad:
            rep.skipped += 1
            rep.messages.append(f"Skipped '{title}': levels must be whole numbers 0-4.")
            continue
        role = db.query(Role).filter_by(team_id=team.id, title=title).one_or_none()
        if role is None:
            order += 1
            role = Role(team=team, title=title, sort_order=order)
            db.add(role)
            rep.created += 1
        else:
            rep.updated += 1
        if "family" in cols:
            role.family = _s(row[cols["family"]])
        if "status" in cols and _s(row[cols["status"]]):
            role.validation_status = _s(row[cols["status"]])
        if "rationale" in cols:
            role.rationale = _s(row[cols["rationale"]])
        if "comment" in cols:
            role.reviewer_comment = _s(row[cols["comment"]])
        existing = {r.area_id: r for r in role.requirements}
        for code, lvl in levels.items():
            a = areas[code]
            if a.id in existing:
                existing[a.id].level = lvl
            else:
                role.requirements.append(RoleRequirement(area=a, level=lvl))
    db.flush()
    return rep


# --- employees ------------------------------------------------------------------

EMPLOYEE_COLUMNS = ["Employee ID", "Name", "Email", "Role Title", "Manager Email",
                    "Admin", "Calibrator"]


def _rows_from_upload(filename: str, data: bytes) -> list[dict]:
    if filename.lower().endswith((".xlsx", ".xlsm")):
        ws = load_workbook(data).worksheets[0]
        it = ws.iter_rows(values_only=True)
        header = [_s(h) for h in next(it)]
        return [dict(zip(header, r)) for r in it if any(v is not None for v in r)]
    text = data.decode("utf-8-sig")
    dialect = csv.Sniffer().sniff(text.splitlines()[0], delimiters=",;\t")
    return list(csv.DictReader(io.StringIO(text), dialect=dialect))


def _yes(v) -> bool:
    return _s(v).lower() in ("y", "yes", "true", "1", "x")


def import_employees(db: Session, team: Team, filename: str, data: bytes) -> ImportReport:
    rep = ImportReport()
    rows = _rows_from_upload(filename, data)
    normed = [{_norm(k): v for k, v in r.items() if k} for r in rows]
    roles = {r.title.lower(): r for r in db.query(Role).filter_by(team_id=team.id)}
    by_email: dict[str, User] = {}
    for r in normed:
        email = _s(r.get("email")).lower()
        emp_id = _s(r.get("employeeid"))
        name = _s(r.get("name") or r.get("employeename"))
        if not email or not emp_id or not name:
            rep.skipped += 1
            rep.messages.append(f"Skipped row without Employee ID / Name / Email: {r}")
            continue
        user = (db.query(User).filter_by(email=email).one_or_none()
                or db.query(User).filter_by(employee_id=emp_id).one_or_none())
        if user is None:
            pwd = temp_password()
            user = User(email=email, employee_id=emp_id, name=name,
                        password_hash=hash_password(pwd), must_change_password=True)
            db.add(user)
            rep.created += 1
            rep.credentials.append((email, pwd))
        else:
            rep.updated += 1
        user.employee_id, user.name, user.email, user.team = emp_id, name, email, team
        title = _s(r.get("roletitle") or r.get("role")).lower()
        if title:
            if title in roles:
                user.role = roles[title]
            else:
                rep.messages.append(f"{email}: role '{title}' not found in team {team.name}.")
        if "admin" in r:
            user.is_admin = _yes(r["admin"]) or user.is_admin
        if "calibrator" in r:
            user.is_calibrator = _yes(r["calibrator"])
        by_email[email] = user
    db.flush()
    for r in normed:
        email = _s(r.get("email")).lower()
        mgr = _s(r.get("manageremail")).lower()
        if email in by_email and mgr:
            m = by_email.get(mgr) or db.query(User).filter_by(email=mgr).one_or_none()
            if m and m is not by_email[email]:
                by_email[email].manager = m
            else:
                rep.messages.append(f"{email}: manager '{mgr}' not found.")
    db.flush()
    return rep
