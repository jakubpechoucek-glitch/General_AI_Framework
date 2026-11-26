from datetime import date

from app import logic


def test_status_classification():
    assert logic.status(0, None) == logic.NOT_REQUIRED
    assert logic.status(0, 3) == logic.NOT_REQUIRED
    assert logic.status(3, None) == logic.NOT_ASSESSED
    assert logic.status(3, 1) == logic.CRITICAL
    assert logic.status(3, 2) == logic.DEVELOPMENT
    assert logic.status(3, 3) == logic.MEETS
    assert logic.status(2, 3) == logic.EXCEEDS


def test_gaps_and_surplus():
    assert logic.development_gap(3, None) is None
    assert logic.development_gap(3, 1) == 2
    assert logic.development_gap(2, 3) == 0
    assert logic.surplus(2, 3) == 1
    assert logic.surplus(3, 1) == 0
    assert logic.self_gap(3, 2) == 1
    assert logic.priority_score(4, 2) == 8
    assert logic.priority_score(1, None) == 0


def test_self_validation_rules():
    assert logic.validate_self_response(0, None, "", "", "") == []
    assert logic.validate_self_response(2, None, "", "", "")
    assert "evidence" in logic.validate_self_response(2, 2, "", "", "High")[0].lower()
    assert logic.validate_self_response(2, 1, "", "", "High") == []
    assert logic.validate_self_response(2, 3, "did X", "ftp://x", "High")
    assert logic.validate_self_response(2, 3, "did X", "https://x.com/a", "High") == []


def test_manager_comment_required_when_different():
    assert logic.validate_manager_response(3, 3, 2, "")
    assert logic.validate_manager_response(3, 3, 2, "evidence shows L2") == []
    assert logic.validate_manager_response(3, 3, 3, "") == []


def test_summary_no_offsetting():
    rows = [logic.Row("K06", "Security", "Knowledge", 3, 1, True),
            logic.Row("S01", "Prompting", "Skill", 2, 4),
            logic.Row("C08", "Value", "Competency", 0, None)]
    s = logic.summarize(rows)
    assert s.required_areas == 2 and s.assessed == 2
    assert s.gap2 == 1 and s.meets == 1 and s.exceeds == 1
    assert s.avg_gap == 1.0  # surplus in S01 does not offset the K06 gap
    assert [r.code for r in s.critical_control_gaps] == ["K06"]
    assert s.priorities[0].code == "K06"


def test_next_review():
    assert logic.next_review(date(2027, 2, 28)) == date(2028, 2, 28)
    assert logic.next_review(date(2028, 2, 29)) == date(2029, 2, 28)
