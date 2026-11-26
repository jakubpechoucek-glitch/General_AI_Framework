import re

from conftest import client_for


def _ids(html, prefix):
    return sorted(set(re.findall(rf'name="{prefix}_(\d+)"', html)))


def test_import(seeded):
    from app.db import SessionLocal
    from app.models import Area, Role, ScaleLevel
    db = SessionLocal()
    assert db.query(Area).count() == 5
    assert db.get(ScaleLevel, 2).skill == "s2."
    op = db.query(Role).filter_by(title="Operator").one()
    assert {r.area.code: r.level for r in op.requirements}["C08"] == 0
    assert {a.code for a in db.query(Area).filter_by(critical_control=True)} == {"K06", "S05"}


def test_full_workflow(seeded):
    emp = client_for("emp@x.com")
    r = emp.post("/assessment/start", data={"confirm": "yes"})
    assert r.status_code == 200
    aid = int(re.search(r'/assessment/(\d+)"', r.text).group(1))
    html = emp.get(f"/assessment/{aid}").text
    rids = _ids(html, "level")
    assert len(rids) == 5

    # submit without evidence for a level-3 rating is blocked (R04)
    data = {"action": "submit", "confirm_accuracy": "1"}
    for rid in rids:
        data |= {f"level_{rid}": "3", f"evidence_{rid}": "", f"conf_{rid}": "High"}
    emp.post(f"/assessment/{aid}", data=data)
    assert "Draft" in emp.get("/").text
    for rid in rids:
        data[f"evidence_{rid}"] = "Concrete work example"
    r = emp.post(f"/assessment/{aid}", data=data)
    assert "Indicative result" in r.text

    # employee can no longer edit (R15)
    r = emp.post(f"/assessment/{aid}", data=data)
    assert "locked" in r.text

    # other users cannot see it
    assert client_for("other@x.com").get(f"/review/{aid}").status_code == 403

    mgr = client_for("mgr@x.com")
    html = mgr.get(f"/review/{aid}").text
    mids = _ids(html, "mlevel")
    review = {"action": "complete_review"} | {f"mlevel_{i}": "2" for i in mids}
    r = mgr.post(f"/review/{aid}", data=review)
    assert "comment is required" in r.text  # R08
    review |= {f"mcomment_{i}": "Evidence shows working level" for i in mids}
    r = mgr.post(f"/review/{aid}", data=review)
    assert "Step: calibration" in r.text

    # finalize requires validated levels (R09)
    r = mgr.post(f"/review/{aid}", data={"action": "finalize"})
    assert "Set the validated current level" in r.text
    mgr.post(f"/review/{aid}", data={"action": "copy_manager"})
    r = mgr.post(f"/review/{aid}", data={"action": "finalize", "next_review_date": "2028-01-31"})
    assert "Official result" in r.text

    from app.db import SessionLocal
    from app.models import Assessment
    db = SessionLocal()
    a = db.get(Assessment, aid)
    assert a.status == "Finalized" and a.next_review_date.isoformat() == "2028-01-31"
    gaps = {r.area.code: r.required_level - r.validated_level for r in a.responses}
    assert gaps["C08"] == 2 and gaps["S01"] == 0

    # reports & export
    r = mgr.get("/reports")
    assert r.status_code == 200 and "Eli Employee" in r.text and "Critical-control gap" in r.text
    x = mgr.get("/reports/export.xlsx")
    assert x.status_code == 200 and x.content[:2] == b"PK"

    # finalised requirements are frozen when the matrix changes
    adm = client_for("admin@x.com")
    team_html = adm.get("/admin/teams/1").text
    key = re.search(r'name="(req_\d+_\d+)"', team_html).group(1)  # Head of Demo / K01
    adm.post("/admin/teams/1", data={"action": "matrix", key: "0"})
    db.expire_all()
    k01 = next(r for r in db.get(Assessment, aid).responses if r.area.code == "K01")
    assert k01.required_level == 3  # frozen at finalisation


    # reopen -> Draft, version 2
    r = mgr.post(f"/review/{aid}", data={"action": "reopen", "reason": "role change"})
    db.expire_all()
    a = db.get(Assessment, aid)
    assert a.status == "Draft" and a.version == 2
    k01 = next(r for r in a.responses if r.area.code == "K01")
    assert k01.required_level == 0  # reopened assessments pick up the current matrix


def test_admin_only(seeded):
    emp = client_for("emp@x.com")
    assert emp.get("/admin").status_code == 403
    assert emp.get("/reports").status_code == 403


def test_onboard_team_and_employees(seeded):
    adm = client_for("admin@x.com")
    r = adm.post("/admin/teams", data={"name": "Retail", "description": ""})
    tid = int(re.search(r"/admin/teams/(\d+)", str(r.url)).group(1))
    adm.post(f"/admin/teams/{tid}", data={"action": "add_role", "title": "Branch Advisor",
                                          "family": "Branch"})
    csv = ("Employee ID,Name,Email,Role Title,Manager Email,Admin,Calibrator\n"
           "R1,Rita Lead,rita@x.com,Branch Advisor,,N,Y\n"
           "R2,Rob Advisor,rob@x.com,Branch Advisor,rita@x.com,N,N\n")
    r = adm.post("/admin/users-import", data={"team_id": str(tid)},
                 files={"file": ("e.csv", csv.encode(), "text/csv")})
    assert "2 created" in r.text and "Temporary passwords" in r.text
    from app.db import SessionLocal
    from app.models import User
    db = SessionLocal()
    rob = db.query(User).filter_by(email="rob@x.com").one()
    assert rob.manager.email == "rita@x.com" and rob.role.title == "Branch Advisor"
    assert rob.must_change_password
