# Administrator guide

Administrators can change every part of the framework and onboard new teams. Everything is under **Admin** in the top bar.
Every change is written to the **Audit log**.

## 1. Initial setup

1. Install and seed the app (see the [README](../README.md#quick-start)). The seed script imports from the workbook:
   - **General AI Framework** → 29 framework areas (code, type, definition, observable statement, typical evidence),
   - **Proficiency Scale** → levels 0–4 with Knowledge / Skill / Competency anchors and JD wording,
   - **CRM KSC Role Rating** → the CRM team with 59 roles and their required levels,
   - an active cycle (default *2027 Annual*) and your admin account.
2. Sign in, set your password.
3. Alternatively, upload the workbook later via **Admin → Import workbook**. The import is repeatable: records are
   updated by area code / role title and nothing is deleted.

## 2. Framework areas

**Admin → Framework areas**
- **Edit** an area: code, type, name, definition, observable statement, typical evidence, sort order.
- **Critical control area**: any gap in such an area is flagged in results and reports even if the overall profile is good.
  The import marks *K06 Security, privacy and confidentiality*, *S05 AI output validation*, *C05 Responsible AI application*
  and *C06 AI quality and risk management* by default.
- **Add an area** (e.g. `S12`). New areas start with required level 0 for all roles. Set the levels in the role matrix.
- **Deactivate** instead of delete when an area already has assessment data. It disappears from new and open assessments,
  and finalised assessments keep their history. Delete is possible only without assessment data.
- **Evidence guidance by type**: the text employees see above the Knowledge / Skill / Competency sections.

## 3. Proficiency scale

**Admin → Proficiency scale** edits the label, the three type-specific anchors and the sample JD wording for levels 0–4.
The anchors are what employees and managers read on the level cards.

## 4. Teams, roles and the requirement matrix

**Admin → Teams & roles → (team)**

- **Role requirement matrix**: one row per role, one column per active area, values 0–4. Change cells and **Save matrix**.
  - Open (not finalised) assessments pick up changes immediately.
  - **Finalised assessments keep the levels they were validated against** (snapshot at finalisation). If an assessment
    is reopened, it picks up the current matrix.
- **Add a role** (starts with all levels 0). **Open a role** to edit family/title, rationale, reviewer comments,
  active flag, or delete it (only if no employees or assessments use it).
- **Export current matrix / Import roles (.xlsx)** lets you edit the matrix in Excel and upload it again (same layout as the template).

### Management validation of required levels
Required levels must be validated with the team's management before gaps are treated as final.
- Per role: set **Validation status** (*Draft — title-based proposal*, *In review with management*, *Validated*) and
  **Validated by**. The date is recorded automatically.
- After a calibration workshop: **Mark all roles validated** with the name of the forum, e.g. *CRM leadership workshop 2027-01-15*.
- Until a role is validated, employees and managers see a banner that the requirements are a proposal, and team lists
  show *requirements not validated*.

## 5. Onboarding a new team

1. **Teams & roles → Onboard a new team**: enter the name.
2. **Download the role-matrix template**, fill in roles and required levels with the team's management (one row per role),
   then **Import roles** on the team page. You can also add roles one by one and fill in the grid.
3. Validate the levels with management and record it (see above).
4. **Employees → Bulk import**: choose the team and upload the employee list (.xlsx or .csv, template available):

   | Employee ID | Name | Email | Role Title | Manager Email | Admin | Calibrator |
   |---|---|---|---|---|---|---|

   - *Role Title* must match a role of that team.
   - Managers can be in the same file. Managers from other teams are matched by email.
   - Existing employees (same email or ID) are updated, not duplicated.
   - **Temporary passwords** for new accounts are shown **once** after the import. Download them as CSV and distribute securely.
5. Make sure a cycle is active and share the link.

## 6. Employees

**Admin → Employees**: search, filter by team, add or edit an employee (ID, name, email, team, role, manager,
administrator, calibration owner, active), or **generate a temporary password** when someone forgets theirs.
Deactivate leavers instead of deleting them so history is kept. A role change applies to the employee's next assessment.

Role mismatches reported by employees appear on the **Admin overview**.

## 7. Cycles

**Admin → Cycles**: one cycle is active at a time (e.g. *2027 Annual*). Creating a new cycle makes it active; employees then
start a new assessment for it, and previous cycles stay available in history and reports. The recommended rhythm is
annual, or earlier after a material role change.

## 8. Assessments

**Admin → Assessments** lists all assessments with filters. Admins can open, review, calibrate, reopen and, if necessary,
permanently delete an assessment (for example a test entry).

## 9. Reports and exports

**Gap reports** (admins see all teams, with a team filter) and **Export to Excel**, which produces:

| Sheet | Content |
|---|---|
| Employee Assessment | Long format: one row per employee × area, with required, self, manager, validated level, self gap, development gap, surplus, priority, status, dates, workflow status and version |
| Employee Gap Summary | Per employee: required areas, assessed, completion, meets, gap 1, gap 2+, average gap, critical-control gaps, priorities |
| Team Gap by Area / Role / Role Family / Type | Assessed, meets, gap 1, gap 2+, meets %, average gap |

## 10. Backups

With the default SQLite database, back up `data/app.db` regularly (stop the app or use `sqlite3 data/app.db ".backup backup.db"`).
For production use PostgreSQL (see [Architecture](architecture.md)).
