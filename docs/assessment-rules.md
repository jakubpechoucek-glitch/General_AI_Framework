# Assessment and gap rules

This document describes how the app calculates results. The rules follow the *Gap Rules* sheet (R01–R20) of the
framework workbook. The formulas are implemented in [`app/logic.py`](../app/logic.py) and covered by unit tests.

## Framework

| Element | Definition | Assessment question | Evidence |
|---|---|---|---|
| **Knowledge** (K01–K08) | What a person knows and understands | Does the person understand the relevant AI concepts, limitations and rules? | Can explain concepts, recognise risks, distinguish approaches |
| **Skill** (S01–S11) | What a person can do | Can the person perform a defined AI-related task? | Produces a usable output or completes a task using AI |
| **Competency** (C01–C10) | Applying knowledge and skills effectively in a work context | Can the person combine knowledge and skills to achieve an outcome responsibly? | Applies AI in context, exercises judgment, achieves outcomes |

## Three levels per area

| Level | Entered by | Meaning |
|---|---|---|
| **Required Level** | Role matrix (admin, validated with management) | What the role needs (0–4). Belongs to the role, never to a person. |
| **Self Level** | Employee | Self-assessed current level |
| **Manager Level** | Manager | Evidence-based assessment of observable performance |
| **Validated Current Level** | Manager / calibration owner | Final, calibrated whole number used for the official gap |

The validated level is **never an average** of self and manager levels (R09). Differences are resolved through evidence
and conversation, not arithmetic.

## Formulas

```
Self Gap         = MAX(Required − Self, 0)                          indicative, shown to the employee after submission (R06)
Development Gap  = blank if Validated is blank,
                   else MAX(Required − Validated, 0)                official gap (R10)
Surplus          = blank if Validated is blank,
                   else MAX(Validated − Required, 0)                shown separately; never offsets a gap elsewhere (R11)
Priority Score   = Development Gap × Required Level  (0–16)          sorting of development priorities only (R14)
Completion       = assessed required areas / required areas         only areas with Required > 0 count (R13)
```

Positive gaps are used on purpose: *Development Gap = 2* is easier to understand in HR reporting than *Gap = −2*.

## Status (R12)

Evaluated top to bottom:

| Condition | Status | Colour | Employee message | Manager action |
|---|---|---|---|---|
| Required = 0 | Not required | grey | Not required for the role | No assessment needed |
| Validated is blank | Not assessed | grey | Awaiting review or validation | Complete review and final rating |
| Gap ≥ 2 | **Critical gap** | red | Priority development area | Agree a targeted action and review date |
| Gap = 1 | **Development needed** | orange | One level needed to meet the requirement | Agree practical experience or learning |
| Current = Required | **Meets requirement** | green | Meets the role requirement | Maintain through regular application |
| Current > Required | **Exceeds requirement** | blue | Exceeds the role requirement | Mentoring, stretch work, future-role pathways |

Status is always shown as text and colour, so it stays readable without colour.

## Rule implementation (R01–R20)

| Rule | Implementation in the app |
|---|---|
| R01 Role mapping | Required level is looked up from the employee's role × area. Employees cannot edit it; they confirm the role or report a mismatch. |
| R02 Scope | Areas with Required = 0 are not shown in the self-assessment. The record is kept for completeness. |
| R03 Self-rating | Five level cards (0–4) with type-specific anchors; integers only. |
| R04 Evidence | Evidence text is mandatory for self levels 2–4; submission is blocked otherwise. |
| R05 Evidence by type | Different evidence guidance for Knowledge, Skill and Competency (editable by admins). |
| R06 Self gap | Shown on the results page after submission as an indicative result. |
| R07 Manager review | Manager selects 0–4 after seeing self level, confidence and evidence. |
| R08 Disagreement | Manager comment is mandatory when manager level ≠ self level. |
| R09 Validated level | Blank by default; set explicitly by manager or calibration owner. No averaging. |
| R10 Official gap | Reports use only finalised assessments and the validated level. |
| R11 Surplus | Calculated and shown separately; summaries never net surplus against gaps. |
| R12 Status | See the table above. |
| R13 Completion | Assessed required areas / required areas. |
| R14 Priority | Gap × required level; used to sort development priorities, not as a performance score. |
| R15 Submission | All required areas rated, evidence rules met, accuracy confirmed. Then the record is locked for the employee. |
| R16 Workflow | Draft → Submitted → Manager Review → Calibration → Finalized, with role-based permissions; reopen increments the version. |
| R17 Review cycle | Next review date defaults to validation date + 12 months and can be changed at finalisation. |
| R18 Privacy | Employees are told not to enter confidential data and to link to approved locations; only http(s) links are accepted; access is restricted by role. |
| R19 Reporting | No single overall "AI score". Knowledge, Skill and Competency are reported separately and critical-control gaps are flagged. |
| R20 Data model | One response record per Assessment + area code; codes and IDs are keys, labels are display values. |

## Evidence expectations

| Level | Expected evidence |
|---|---|
| L1 | Simple confirmation or example |
| L2 | At least one work example |
| L3 | Several examples or a documented complex output |
| L4 | Evidence of setting standards, leading others or organisational impact |

## Required levels over time

- While an assessment is open, its required levels follow the current role matrix.
- At **finalisation** the required levels are frozen in the assessment, so later matrix changes do not rewrite official history.
- If a finalised assessment is **reopened**, it picks up the current matrix again.
- Results based on roles whose requirements are not yet **validated by management** show a warning banner.

## Example

| Required | Validated | Development Gap | Surplus | Status |
|---|---|---|---|---|
| 3 | 1 | 2 | 0 | Critical gap |
| 3 | 2 | 1 | 0 | Development needed |
| 3 | 3 | 0 | 0 | Meets requirement |
| 2 | 3 | 0 | 1 | Exceeds requirement |
| 0 | – | – | – | Not required |
