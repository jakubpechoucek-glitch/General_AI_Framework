"""Initialise the database from the framework workbook and create the first admin.

Usage:
  python -m scripts.seed --workbook "data/CRM AI Skills Pool and Role Rating.xlsx" \
      --team CRM --admin-email you@company.com [--admin-password ...] [--cycle "2027 Annual"] [--demo]

--demo adds fictional employees (example.com) with sample assessments so the
workflow and reports can be explored. Do not use --demo in production.
"""
import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.auth import hash_password, temp_password  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.importer import import_framework, import_role_matrix, import_scale, load_workbook  # noqa: E402
from app.models import Assessment, Cycle, Role, Team, User, utcnow  # noqa: E402
from app.services import finalize, start_assessment  # noqa: E402

DEMO_PASSWORD = "demo-password-123"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--workbook", required=True)
    p.add_argument("--team", default="CRM")
    p.add_argument("--admin-email", required=True)
    p.add_argument("--admin-name", default="Administrator")
    p.add_argument("--admin-password")
    p.add_argument("--cycle", default="2027 Annual")
    p.add_argument("--demo", action="store_true")
    args = p.parse_args()

    init_db()
    db = SessionLocal()
    wb = load_workbook(Path(args.workbook).read_bytes())
    print("Framework:", import_framework(db, wb).summary())
    print("Scale:", import_scale(db, wb).summary())
    team = db.query(Team).filter_by(name=args.team).one_or_none() or Team(name=args.team)
    db.add(team)
    db.flush()
    rep = import_role_matrix(db, wb, team)
    print(f"Roles ({team.name}):", rep.summary(), *rep.messages, sep="\n  ")

    if not db.query(Cycle).filter_by(name=args.cycle).first():
        db.add(Cycle(name=args.cycle, active=True))

    email = args.admin_email.lower()
    admin = db.query(User).filter_by(email=email).one_or_none()
    if admin is None:
        pwd = args.admin_password or temp_password()
        admin = User(employee_id="ADMIN-001", name=args.admin_name, email=email, is_admin=True,
                     password_hash=hash_password(pwd), must_change_password=not args.admin_password)
        db.add(admin)
        print(f"Admin created: {email} / {pwd}" + ("" if args.admin_password else
                                                    "  (temporary, change at first sign-in)"))
    db.flush()
    if args.demo:
        demo(db, team, db.query(Cycle).filter_by(name=args.cycle).one())
    db.commit()
    print("Done.")


def demo(db, team, cycle):
    roles = db.query(Role).filter_by(team_id=team.id).order_by(Role.sort_order).all()
    if not roles:
        return
    rnd = random.Random(42)

    def mk(i, name, role, manager=None, **kw):
        email = f"demo.{name.split()[0].lower()}@example.com"
        u = db.query(User).filter_by(email=email).one_or_none()
        if u:
            return u
        u = User(employee_id=f"DEMO-{i:03d}", name=name, email=email, team=team, role=role,
                 manager=manager, password_hash=hash_password(DEMO_PASSWORD),
                 must_change_password=False, **kw)
        db.add(u)
        db.flush()
        return u

    mgr = mk(1, "Morgan Manager", roles[0], is_calibrator=True)
    names = ["Alex Analyst", "Casey Campaign", "Robin Retention", "Sam Specialist",
             "Taylor Telesales", "Jordan Journey"]
    people = [mk(i + 2, n, roles[min(len(roles) - 1, 5 + i * 7)], mgr) for i, n in enumerate(names)]

    for idx, u in enumerate(people):
        if db.query(Assessment).filter_by(cycle_id=cycle.id, employee_id=u.id).first():
            continue
        a = start_assessment(db, u, cycle)
        a.role_confirmed = True
        stage = ["Finalized", "Finalized", "Finalized", "Finalized", "Submitted", "Draft"][idx]
        for r in a.responses:
            if r.required_level == 0:
                continue
            r.self_level = max(0, min(4, r.required_level + rnd.choice([-2, -1, -1, 0, 0, 0, 1])))
            r.confidence = rnd.choice(["Low", "Medium", "High"])
            if r.self_level >= 2:
                r.self_evidence = f"Example of applying {r.area.name.lower()} in recent work."
            if stage == "Finalized":
                r.manager_level = max(0, r.self_level - rnd.choice([0, 0, 0, 1]))
                if r.manager_level != r.self_level:
                    r.manager_comment = "Evidence supports one level lower for now."
                r.validated_level = r.manager_level
        if stage != "Draft":
            a.status = "Submitted"
            a.assessment_date = utcnow()
        if stage == "Finalized":
            finalize(db, a, mgr)
    db.flush()
    print(f"Demo users created (password '{DEMO_PASSWORD}'): manager {mgr.email}, "
          + ", ".join(u.email for u in people))


if __name__ == "__main__":
    main()
