"""Fictional demo data for screenshots and local exploration.

Everything here is invented example content (team "Marketing (demo)", example.com
people, a shortened framework). It deliberately contains no organisational data, so the
screenshots generated from it can live in the public repository.
"""
from __future__ import annotations

import io

import openpyxl

from app.auth import hash_password

DEMO_PASSWORD = "demo-password-123"
TEAM = "Marketing (demo)"

AREAS = [
    ("Knowledge", "K01", "AI fundamentals",
     "Understands what AI, machine learning and generative AI are and how they differ.",
     "Explains the main AI concepts in plain language.",
     "Explains the difference between a rules engine, a predictive model and a chatbot."),
    ("Knowledge", "K02", "Capabilities and limitations",
     "Understands where AI helps and where outputs can be unreliable (e.g. hallucinations).",
     "Recognises likely failure modes before relying on AI output.",
     "Lists the risks before using AI to draft a customer letter."),
    ("Knowledge", "K03", "Data protection and confidentiality",
     "Knows which information must not be shared with AI tools and why.",
     "Chooses safe ways to handle personal and confidential data.",
     "Explains why customer data stays out of public chatbots."),
    ("Skill", "S01", "Prompting",
     "Writes clear instructions with context, constraints and an expected format.",
     "Gets a usable result within a few iterations.",
     "A prompt that produces a campaign brief in the team template."),
    ("Skill", "S02", "Research and summarising",
     "Uses AI to find, compare and summarise information with sources.",
     "Produces a short, traceable summary that separates facts from assumptions.",
     "A one-page competitor summary with sources."),
    ("Skill", "S03", "Checking AI output",
     "Verifies facts, numbers and sources before using AI output.",
     "Corrects errors and documents what was checked.",
     "A reviewed AI draft with corrected figures."),
    ("Competency", "C01", "Finding AI opportunities",
     "Identifies work where AI can create real value.",
     "Connects a business problem to a feasible AI use case.",
     "A prioritised list of use cases for the team."),
    ("Competency", "C02", "AI in daily work",
     "Uses AI routinely to improve speed or quality of own work.",
     "Shows a sustained improvement in an end-to-end task.",
     "Reporting time cut from 4 hours to 1 hour per week."),
    ("Competency", "C03", "Responsible application",
     "Balances value with privacy, fairness and human oversight.",
     "Adds controls or declines AI use when risk outweighs benefit.",
     "Introduced a review step before AI-drafted texts reach customers."),
]
CRITICAL = {"K03", "S03", "C03"}

SCALE = [
    (0, "Not required", "Not required for the role."),
    (1, "Basic", "Knowledge: basic awareness. Skill: simple tasks with guidance. "
                 "Competency: contributes in well-defined situations with guidance."),
    (2, "Working", "Knowledge: solid working knowledge. Skill: performs independently in "
                   "regular situations. Competency: applies independently in own work."),
    (3, "Advanced", "Knowledge: deep understanding, can explain to others. Skill: handles "
                    "complex tasks and guides others. Competency: improves ways of working."),
    (4, "Expert", "Knowledge: recognised expertise. Skill: sets standards and enables others. "
                  "Competency: shapes strategy and organisational practice."),
]

#            K01 K02 K03 S01 S02 S03 C01 C02 C03
ROLES = [
    ("Leadership", "Head of Marketing", [3, 3, 3, 2, 2, 3, 4, 3, 4], "Validated"),
    ("Campaigns", "Campaign Manager", [2, 3, 3, 3, 2, 3, 2, 3, 3], "Validated"),
    ("Insights", "Marketing Analyst", [2, 2, 3, 2, 3, 3, 1, 2, 2], "Validated"),
    ("Content", "Content Specialist", [1, 2, 2, 3, 2, 2, 0, 2, 2],
     "Draft — title-based proposal"),
]


def workbook_bytes() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "General AI Framework"
    ws.append(["Demo framework"])
    ws.append(["Type", "Code", "Area", "Definition", "Observable statement", "Typical evidence"])
    for row in AREAS:
        ws.append(list(row))
    sc = wb.create_sheet("Proficiency Scale")
    sc.append(["Level", "Label", "Application", "JD wording"])
    for lvl, label, text in SCALE:
        sc.append([lvl, label, text, ""])
    m = wb.create_sheet("Demo KSC Role Rating")
    m.append(["Role Family", "Role Title"] + [f"{a[1]} | {a[2]}" for a in AREAS]
             + ["Validation Status", "Proposal rationale / assumptions", "Reviewer comments"])
    for fam, title, levels, status in ROLES:
        m.append([fam, title] + levels + [status, "Demo rationale.", ""])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def seed(db) -> dict:
    """Create the demo team, people and assessments in every workflow state.

    Returns a dict of handy ids for the screenshot script.
    """
    from datetime import date

    from app.importer import import_framework, import_role_matrix, import_scale, load_workbook
    from app.models import Area, Cycle, Role, Team, User
    from app.services import finalize, start_assessment
    from app.models import utcnow

    wb = load_workbook(workbook_bytes())
    import_framework(db, wb)
    import_scale(db, wb)
    for a in db.query(Area):
        a.critical_control = a.code in CRITICAL
    team = Team(name=TEAM, description="Fictional team used for the user guide")
    db.add(team)
    db.flush()
    import_role_matrix(db, wb, team)
    for r in db.query(Role).filter_by(validation_status="Validated"):
        r.validated_by, r.validated_on = "Marketing leadership workshop", date(2027, 1, 15)
    db.add(Cycle(name="2027 Annual", active=True, start_date=date(2027, 1, 1),
                 end_date=date(2027, 3, 31)))
    db.flush()
    cycle = db.query(Cycle).one()
    roles = {r.title: r for r in db.query(Role)}
    pw = hash_password(DEMO_PASSWORD)

    def user(eid, name, email, role=None, manager=None, **kw):
        u = User(employee_id=eid, name=name, email=email, team=team, role=role,
                 manager=manager, password_hash=pw, must_change_password=False, **kw)
        db.add(u)
        db.flush()
        return u

    admin = user("D-001", "Alex Admin", "alex.admin@example.com", is_admin=True)
    admin.team = None
    pat = user("D-002", "Pat Partner", "pat.partner@example.com", is_calibrator=True)
    maria = user("D-010", "Maria Manager", "maria.manager@example.com",
                 roles["Head of Marketing"])
    erin = user("D-011", "Erin Employee", "erin.employee@example.com",
                roles["Campaign Manager"], maria)
    sam = user("D-012", "Sam Submitted", "sam.submitted@example.com",
               roles["Marketing Analyst"], maria)
    chris = user("D-013", "Chris Calibration", "chris.calibration@example.com",
                 roles["Campaign Manager"], maria)
    dana = user("D-014", "Dana Done", "dana.done@example.com", roles["Campaign Manager"], maria)
    lee = user("D-015", "Lee Lindqvist", "lee.lindqvist@example.com",
               roles["Marketing Analyst"], maria)
    kim = user("D-016", "Kim Kovac", "kim.kovac@example.com", roles["Content Specialist"], maria)
    noah = user("D-017", "Noah New", "noah.new@example.com", roles["Content Specialist"], maria)
    newbie = user("D-018", "Nina Newcomer", "nina.newcomer@example.com",
                  roles["Content Specialist"], maria)
    newbie.must_change_password = True

    # deterministic self / manager / validated patterns per area index
    patterns = {
        "erin": [2, 3, None, None, None, None, None, None, None],
        "sam": [2, 2, 2, 3, 3, 2, 1, 2, 2],
        "chris": [2, 3, 2, 3, 2, 3, 2, 3, 2],
        "dana": [2, 3, 1, 3, 3, 2, 2, 3, 3],
        "lee": [2, 2, 3, 2, 3, 2, 1, 1, 2],
        "kim": [1, 2, 2, 4, 2, 1, 0, 2, 1],
    }
    evidence = {
        "K01": "Explained generative AI vs. predictive models in our team meeting.",
        "K02": "Flagged hallucinated figures in an AI-drafted market summary before use.",
        "K03": "Use only the approved enterprise assistant; anonymise customer examples.",
        "S01": "Prompt template for campaign briefs, used for the Q1 launches.",
        "S02": "Competitor summary with sources for the pricing workshop.",
        "S03": "Checked every number in the AI draft against the BI dashboard.",
        "C01": "Proposed two use cases for weekly reporting; one is in pilot.",
        "C02": "Weekly reporting now takes 1 hour instead of 4.",
        "C03": "Added a human review step before AI texts go to customers.",
    }

    def fill(u, key, stage, manager_delta=None):
        a = start_assessment(db, u, cycle)
        a.role_confirmed = True
        resp = sorted(a.responses, key=lambda r: r.area.sort_order)
        for i, r in enumerate(resp):
            lvl = patterns[key][i]
            if r.required_level == 0 or lvl is None:
                continue
            r.self_level = lvl
            r.confidence = ["Medium", "High", "Low"][i % 3]
            if lvl >= 1:
                r.self_evidence = evidence[r.area.code]
            if stage in ("Calibration", "Finalized"):
                d = (manager_delta or {}).get(r.area.code, 0)
                r.manager_level = max(0, lvl - d)
                if d:
                    r.manager_comment = "Evidence supports one level lower; let's agree a stretch task."
                if stage == "Finalized":
                    r.validated_level = r.manager_level
        if stage != "Draft":
            a.status = "Submitted" if stage == "Submitted" else stage
            a.assessment_date = utcnow()
        if stage == "Finalized":
            finalize(db, a, maria)
        return a

    ids = {
        "erin": fill(erin, "erin", "Draft").id,
        "sam": fill(sam, "sam", "Submitted").id,
        "chris": fill(chris, "chris", "Calibration", {"S02": 1, "C03": 1}).id,
        "dana": fill(dana, "dana", "Finalized", {"K03": 0, "S03": 1}).id,
        "lee": fill(lee, "lee", "Finalized", {"C02": 1}).id,
        "kim": fill(kim, "kim", "Finalized", {"S01": 1}).id,
    }
    _ = (noah, pat, admin)
    db.flush()
    ids["team"] = team.id
    ids["role"] = roles["Campaign Manager"].id
    ids["area"] = db.query(Area).filter_by(code="S03").one().id
    ids["user"] = erin.id
    return ids
