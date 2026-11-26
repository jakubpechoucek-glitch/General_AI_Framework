import io
import os
import sys
import tempfile
from pathlib import Path

import openpyxl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["SECRET_KEY"] = "test"

AREAS = [("Knowledge", "K01", "AI fundamentals"), ("Knowledge", "K06", "Security"),
         ("Skill", "S01", "Prompting"), ("Skill", "S05", "AI output validation"),
         ("Competency", "C08", "AI value realization")]


def make_workbook() -> bytes:
    """Synthetic workbook in the same layout as the real framework file."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "General AI Framework"
    ws.append(["General AI Knowledge, Skills & Competencies Framework"])
    ws.append(["Type", "Code", "Area", "Definition", "Observable statement", "Typical evidence"])
    for t, c, n in AREAS:
        ws.append([t, c, n, f"{n} definition", f"{n} observable", f"{n} evidence"])
    sc = wb.create_sheet("Proficiency Scale")
    sc.append(["Scale"])
    sc.append(["Level", "Label", "Application", "Sample JD Wording"])
    sc.append([0, "Not required", "Not required for the role.", ""])
    for i, lab in enumerate(["Basic", "Working", "Advanced", "Expert"], 1):
        sc.append([i, lab, f"Knowledge: k{i}. Skill: s{i}. Competency: c{i}.", f"jd{i}"])
    m = wb.create_sheet("Demo KSC Role Rating")
    m.append(["TITLE"])
    m.append(["Role Family", "Role Title"] + [f"{c} | {n}" for _, c, n in AREAS]
             + ["Required areas (1–4)", "Validation Status", "Proposal rationale / assumptions",
                "Reviewer comments"])
    m.append(["Leadership", "Head of Demo", 3, 3, 2, 3, 4, 5, "Draft — title-based proposal", "r", ""])
    m.append(["Operations", "Operator", 1, 2, 1, 2, 0, 4, "Draft — title-based proposal", "r", ""])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture(scope="session")
def seeded():
    from app.auth import hash_password
    from app.db import SessionLocal, init_db
    from app.importer import import_framework, import_role_matrix, import_scale, load_workbook
    from app.models import Cycle, Role, Team, User

    init_db()
    db = SessionLocal()
    wb = load_workbook(make_workbook())
    import_framework(db, wb)
    import_scale(db, wb)
    team = Team(name="Demo")
    db.add(team)
    db.flush()
    import_role_matrix(db, wb, team)
    head = db.query(Role).filter_by(title="Head of Demo").one()
    db.add(Cycle(name="2027 Annual", active=True))
    pw = hash_password("password-123")
    admin = User(employee_id="A1", name="Admin", email="admin@x.com", is_admin=True,
                 password_hash=pw, must_change_password=False)
    mgr = User(employee_id="M1", name="Mia Manager", email="mgr@x.com", team=team, role=head,
               password_hash=pw, must_change_password=False)
    db.add_all([admin, mgr])
    db.flush()
    emp = User(employee_id="E1", name="Eli Employee", email="emp@x.com", team=team, role=head,
               manager=mgr, password_hash=pw, must_change_password=False)
    other = User(employee_id="E2", name="Oli Other", email="other@x.com", team=team, role=head,
                 password_hash=pw, must_change_password=False)
    db.add_all([emp, other])
    db.commit()
    db.close()
    return True


def client_for(email):
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    r = c.post("/login", data={"email": email, "password": "password-123"}, follow_redirects=False)
    assert r.status_code == 303
    return c
