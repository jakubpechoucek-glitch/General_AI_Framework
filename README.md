# General AI Framework – AI KSC Self-Assessment

A web application for assessing **AI Knowledge, Skills and Competencies (KSC)** against role requirements.
Employees rate their current level, managers review and validate it, and the app calculates the
**development gap** between the validated current level and the level the role requires.

The app is built on the *General AI Knowledge, Skills & Competencies Framework* (29 areas: K01–K08,
S01–S11, C01–C10), the shared 0–4 proficiency scale and role requirement matrices such as
*CRM KSC Role Rating*.

> **Core design principle:** Required Level belongs to the **role**, Current Level belongs to the **employee**.
> The gap only exists when the two are joined via *Role* + *KSC code*. Role requirements are kept in one place,
> so every change to a role matrix flows into all open gap analyses.

## Features

| For | What it does |
|---|---|
| **Employees** | Confirm role → self-rate each required area (0–4) on type-specific anchors → add evidence → submit → see indicative *Self Gap*, later the official *Development Gap* and personal development priorities. The required level is hidden while rating, so it can't anchor the answer. |
| **Managers** | Review direct reports' ratings and evidence, give an evidence-based manager level (comment mandatory when it differs), set the **validated current level** and finalise. Can return an assessment to the employee. |
| **Calibration owners** | Same calibration rights across their whole team. |
| **Management / L&D** | Employee Gap Summary, Team Gap Summary by area, role, role family and K/S/C type, most common gaps, critical-control flags. Full Excel export (long format + summaries). |
| **Admins** | Edit everything: framework areas, proficiency scale, evidence guidance, teams, roles, requirement matrix (grid editor), management validation status of roles, employees, cycles, assessments. Onboard new teams by importing a role matrix and an employee list. Audit log. |

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Put the framework workbook in ./data (it is git-ignored) and seed the database:
python -m scripts.seed --workbook "data/CRM_AI_Skills_Pool_and_Role_Rating.xlsx" \
    --team CRM --admin-email you@company.com --admin-name "Your Name"
#   add --demo to create fictional demo users and sample assessments

SECRET_KEY=$(python -c "import secrets;print(secrets.token_hex(32))") uvicorn app.main:app --reload
```

Open http://localhost:8000 and sign in with the admin email and the temporary password printed by the seed script.

Run the tests with `pytest`. They use a synthetic workbook, so no organisational data is needed.

## Documentation

- [User guide](docs/user-guide.md): employees, managers and calibration owners
- [Administrator guide](docs/admin-guide.md): setup, editing the framework, onboarding new teams, imports and exports
- [Assessment and gap rules](docs/assessment-rules.md): scale, workflow, formulas, statuses, evidence rules (R01–R20)
- [Architecture and deployment](docs/architecture.md): data model, permissions, configuration, security, roadmap

## Project structure

```
app/
  main.py          FastAPI app, middleware, error handling
  models.py        Data model (areas, scale, teams, roles, requirements, users, cycles, assessments, responses, audit)
  logic.py         Gap rules as pure functions (status, gaps, surplus, priority, validation, summaries)
  services.py      Assessment lifecycle (create, sync requirements, finalise, reopen)
  importer.py      Excel/CSV import (framework, scale, role matrix, employees)
  reporting.py     Employee/Team gap summaries and Excel exports
  auth.py          Login, password hashing, permission checks
  routes/          core (login, self-assessment), review (manager, calibration, reports), admin
  templates/       Server-rendered Jinja2 pages
  static/          CSS and a small progressive-enhancement script
scripts/seed.py    Initialise DB from the workbook, create admin, optional demo data
tests/             Unit tests for the rules + end-to-end workflow tests
docs/              Documentation
```

## Data protection

Assessment data is employee-related information. The repository contains **no organisational data**:
the workbook, the database and all `.xlsx` files are git-ignored. Keep it that way, especially while the repository is public.
