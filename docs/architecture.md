# Architecture and deployment

## Technology

| Layer | Choice | Why |
|---|---|---|
| Web framework | **FastAPI** (Python) with server-rendered **Jinja2** templates | Simple to run and change; no front-end build step |
| Database | **SQLAlchemy 2** with **SQLite** by default, **PostgreSQL** via `DATABASE_URL` | Zero-setup for pilots, standard database for production |
| Excel | **openpyxl** | Import of the framework workbook, role matrices and employee lists; Excel exports |
| UI | Plain HTML/CSS plus a small progressive-enhancement script | Works without JavaScript; accessible form controls |

## Data model

```
Area (K01…C10) ─┐                                   ScaleLevel (0–4, anchors per type)
                │                                   EvidenceGuide (per type)
Team ── Role ── RoleRequirement (role × area → required 0–4)
         │
User (employee: team, role, manager, flags) ── Assessment (per cycle: status, version, dates)
                                                    └── Response (per area: required snapshot, self, evidence,
                                                                   link, confidence, manager, comment, validated)
Cycle                                               AuditLog (who, what, when)
```

- **Required level** lives on `RoleRequirement` (role × area). It is copied to `Response.required_level` and kept in sync
  until finalisation, when it is frozen.
- **One `Response` per assessment × area** (normalised long format). This maps directly to the *Employee Assessment*
  export and to other platforms (Dataverse, SharePoint Lists, SQL).
- Gap, surplus, status and priority are **calculated** and not stored, so they can never be inconsistent.

## Permissions

| Capability | Employee | Manager (has direct reports) | Calibration owner | Admin |
|---|---|---|---|---|
| Own self-assessment | ✔ | ✔ | ✔ | ✔ |
| See / review direct reports | | ✔ | | ✔ |
| Set validated level, finalise, reopen | | direct reports | whole own team | all |
| Gap reports & export | | direct reports | whole own team | all teams |
| Administration | | | | ✔ |

Managers cannot review or validate their own assessment.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///data/app.db` | e.g. `postgresql+psycopg://user:pass@host/db` (install the `psycopg` driver) |
| `SECRET_KEY` | random per start | **Set a fixed value in production**, otherwise sessions end at every restart |
| `HTTPS_ONLY` | `0` | Set to `1` behind HTTPS so session cookies are marked Secure |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | – | If set and no administrator exists yet, the first admin is created at start-up (password must be changed at first sign-in). Used for hosted deployments where the seed script is not run. |

## Running in production

```bash
pip install -r requirements.txt
export SECRET_KEY=... HTTPS_ONLY=1 DATABASE_URL=...
python -m scripts.seed --workbook path/to/workbook.xlsx --team CRM --admin-email admin@company.com
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
```

Put it behind your organisation's reverse proxy / HTTPS. Any platform that runs a Python web service works
(Azure App Service, a container, Render, an internal VM). The health check endpoint is `/healthz`.
Tables are created automatically at start-up. For later schema changes, adding Alembic migrations is recommended.

## Deploying on Render

`render.yaml` describes a Python web service plus a PostgreSQL database (region Frankfurt).

1. Create the PostgreSQL database and the web service (Blueprint, dashboard or the Render MCP tools):
   - Build: `pip install -r requirements.txt`
   - Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips '*'`
   - Health check: `/healthz`
   - Env vars: `DATABASE_URL` (internal connection string of the database), `SECRET_KEY`, `HTTPS_ONLY=1`,
     `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `PYTHON_VERSION`.
2. Open the service URL, sign in as the admin and set your own password.
3. **Admin → Import workbook**: upload the framework workbook (framework areas, scale, role matrix into a new team, e.g. *CRM*).
   This keeps organisational data out of the public repository.
4. **Admin → Cycles**: create the active cycle; **Admin → Employees**: import employees.

Notes: do not use SQLite on Render, because the service's disk is wiped on every deploy. On the free plan the service sleeps when idle
(first request takes ~1 minute) and the free database expires after 30 days. Use paid plans for real use.

## Security

- Passwords are hashed with PBKDF2-SHA256 (240 000 iterations); temporary passwords must be changed at first sign-in.
- Session cookie is signed, `SameSite=Strict` (protects form posts against cross-site requests), 8-hour lifetime.
- Every request checks role-based permissions on the server; employees cannot see others' data.
- All changes to framework, roles, employees and assessments are recorded in the audit log.
- No organisational data is stored in the repository (`data/` and `*.xlsx` are git-ignored).

## Roadmap / recommended next steps

1. **Microsoft Entra ID single sign-on (OIDC)**: replace the local login in `app/auth.py`. The rest of the app only needs
   the signed-in user's email to find the `User` record. HR data (role, manager) can then be synced instead of imported.
2. **Email / Teams notifications**: invitation, submitted → manager, finalised → employee, review-date reminders.
3. **Learning catalogue mapping**: map courses or learning interventions to areas and levels, and suggest them for gaps.
4. **Database migrations** (Alembic) and PostgreSQL for multi-team production use.
5. **Power BI**: connect to the database or use the Excel export for organisation-wide dashboards.
