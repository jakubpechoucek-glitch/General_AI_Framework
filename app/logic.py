"""Gap rules (see the 'Gap Rules' sheet, R01-R20). Pure functions, no DB access."""
from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date
from urllib.parse import urlparse

NOT_REQUIRED = "Not required"
NOT_ASSESSED = "Not assessed"
CRITICAL = "Critical gap"
DEVELOPMENT = "Development needed"
MEETS = "Meets requirement"
EXCEEDS = "Exceeds requirement"
STATUSES = (CRITICAL, DEVELOPMENT, MEETS, EXCEEDS, NOT_ASSESSED, NOT_REQUIRED)
STATUS_CSS = {CRITICAL: "critical", DEVELOPMENT: "development", MEETS: "meets",
              EXCEEDS: "exceeds", NOT_ASSESSED: "neutral", NOT_REQUIRED: "neutral"}

EVIDENCE_MIN_LEVEL = 2  # R04


def _valid_level(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 4


def self_gap(required: int, self_level: int | None) -> int | None:
    """R06: MAX(Required - Self, 0). Indicative only."""
    if self_level is None:
        return None
    return max(required - self_level, 0)


def development_gap(required: int, validated: int | None) -> int | None:
    """R10: blank until validated; otherwise MAX(Required - Validated, 0)."""
    if validated is None:
        return None
    return max(required - validated, 0)


def surplus(required: int, validated: int | None) -> int | None:
    """R11: blank until validated; otherwise MAX(Validated - Required, 0)."""
    if validated is None:
        return None
    return max(validated - required, 0)


def status(required: int, validated: int | None) -> str:
    """R12 status classification."""
    if required == 0:
        return NOT_REQUIRED
    if validated is None:
        return NOT_ASSESSED
    gap = required - validated
    if gap >= 2:
        return CRITICAL
    if gap == 1:
        return DEVELOPMENT
    if gap == 0:
        return MEETS
    return EXCEEDS


def priority_score(required: int, validated: int | None) -> int:
    """R14: Development Gap x Required Level (0-16). For sorting only."""
    gap = development_gap(required, validated)
    return (gap or 0) * required


def is_valid_url(url: str) -> bool:
    try:
        p = urlparse(url.strip())
    except ValueError:
        return False
    return p.scheme in ("http", "https") and bool(p.netloc)


def next_review(from_date: date, months: int = 12) -> date:
    """R17: normally validation date + 12 months."""
    m = from_date.month - 1 + months
    y, m = from_date.year + m // 12, m % 12 + 1
    day = min(from_date.day, calendar.monthrange(y, m)[1])
    return date(y, m, day)


# --- validation of submissions --------------------------------------------------

def validate_self_response(required: int, level, evidence: str, link: str,
                           confidence: str) -> list[str]:
    """R02-R05 for one response. Returns a list of error messages."""
    if required == 0:
        return []  # R02: not required, no self-rating needed
    errors = []
    if level is None:
        errors.append("Select your current level (0-4).")
        return errors
    if not _valid_level(level):
        errors.append("Level must be a whole number from 0 to 4.")
    if level >= EVIDENCE_MIN_LEVEL and not (evidence or "").strip():
        errors.append("Concrete evidence is required for levels 2-4.")
    if not confidence:
        errors.append("Select your confidence (Low / Medium / High).")
    if link and not is_valid_url(link):
        errors.append("Evidence link must be a valid http(s) URL.")
    return errors


def validate_manager_response(required: int, self_level, manager_level,
                              comment: str) -> list[str]:
    """R07-R08 for one response."""
    if required == 0:
        return []
    if manager_level is None:
        return ["Select the manager level (0-4)."]
    if not _valid_level(manager_level):
        return ["Manager level must be a whole number from 0 to 4."]
    if self_level is not None and manager_level != self_level and not (comment or "").strip():
        return ["A comment is required when the manager level differs from the self level."]
    return []


def validate_validated_response(required: int, validated) -> list[str]:
    """R09: integer 0-4, set explicitly (never averaged)."""
    if required == 0:
        return []
    if validated is None:
        return ["Set the validated current level."]
    if not _valid_level(validated):
        return ["Validated level must be a whole number from 0 to 4."]
    return []


# --- aggregation ------------------------------------------------------------------

@dataclass
class Row:
    """Minimal view of one response for aggregation."""
    code: str
    name: str
    type: str
    required: int
    validated: int | None
    critical_control: bool = False

    @property
    def status(self) -> str:
        return status(self.required, self.validated)

    @property
    def gap(self) -> int | None:
        return development_gap(self.required, self.validated)

    @property
    def priority(self) -> int:
        return priority_score(self.required, self.validated)


@dataclass
class Summary:
    required_areas: int = 0
    assessed: int = 0
    meets: int = 0          # Meets + Exceeds (requirement satisfied)
    exceeds: int = 0
    gap1: int = 0
    gap2: int = 0
    gap_total: int = 0
    by_type: dict = field(default_factory=dict)
    priorities: list = field(default_factory=list)
    critical_control_gaps: list = field(default_factory=list)

    @property
    def completion(self) -> float:
        """R13: assessed required areas / required areas."""
        return self.assessed / self.required_areas if self.required_areas else 0.0

    @property
    def avg_gap(self) -> float | None:
        """Average gap over assessed *required* areas only."""
        return self.gap_total / self.assessed if self.assessed else None

    @property
    def meets_pct(self) -> float | None:
        return self.meets / self.assessed if self.assessed else None


def summarize(rows: list[Row], top_n: int = 5) -> Summary:
    s = Summary()
    for t in ("Knowledge", "Skill", "Competency"):
        s.by_type[t] = {"required": 0, "assessed": 0, "meets": 0, "gap1": 0, "gap2": 0}
    for r in rows:
        if r.required == 0:
            continue
        bt = s.by_type.setdefault(r.type, {"required": 0, "assessed": 0, "meets": 0,
                                            "gap1": 0, "gap2": 0})
        s.required_areas += 1
        bt["required"] += 1
        if r.validated is None:
            continue
        s.assessed += 1
        bt["assessed"] += 1
        g = r.gap or 0
        s.gap_total += g
        if g == 0:
            s.meets += 1
            bt["meets"] += 1
            if r.validated > r.required:
                s.exceeds += 1
        elif g == 1:
            s.gap1 += 1
            bt["gap1"] += 1
        else:
            s.gap2 += 1
            bt["gap2"] += 1
        if g > 0 and r.critical_control:
            s.critical_control_gaps.append(r)
    gaps = [r for r in rows if r.priority > 0]
    gaps.sort(key=lambda r: (-r.priority, -(r.gap or 0), r.code))
    s.priorities = gaps[:top_n]
    return s
