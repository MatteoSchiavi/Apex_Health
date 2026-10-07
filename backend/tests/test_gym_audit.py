"""Focused regression coverage for the gym-plan safety audit."""

from datetime import date, timedelta

from app.services.gym_advisor import _select_diverse_exercises, adjust


def _row(exercise_id, pattern, group="legs", impact="low"):
    return {
        "exercise_id": exercise_id,
        "name": f"Exercise {exercise_id}",
        "muscle_group": group,
        "movement_pattern": pattern,
        "impact_level": impact,
        "sets": 3,
        "reps_min": 8,
        "reps_max": 12,
        "rest_seconds": 90,
        "notes": None,
    }


def test_catalog_selection_limits_axial_and_keeps_supported_variety():
    rows = [
        _row(1, "squat"),
        _row(2, "hinge"),
        _row(3, "lunge"),
        _row(4, "single_leg"),
        _row(5, "isolation"),
        _row(6, "isolation"),
        _row(7, "core_anti", group="core"),
        _row(8, "core_flex", group="core"),
        _row(9, "push_h", group="push"),
    ]

    chosen = _select_diverse_exercises(rows)

    assert [row["exercise_id"] for row in chosen] == [1, 3, 5, 7, 9]


def test_safety_veto_can_return_empty_and_does_not_claim_medical_safety():
    rows = [_row(1, "squat", impact="high"), _row(2, "hinge", impact="moderate")]
    chosen, notes = adjust(
        rows,
        [],
        [],
        date(2026, 10, 7),
        safety={"illness_risk": 90},
        locale="it",
    )

    assert chosen == []
    assert notes
    assert all("safe" not in note.lower() and "sicuro" not in note.lower() for note in notes)


def test_empty_injury_protected_day_recommends_rest_without_restoring_rows():
    rows = [_row(1, "squat"), _row(2, "hinge")]
    feedback = [{"soreness": ["knees"], "injury_flag": True, "rpe": 9}]

    chosen, notes = adjust(rows, [], feedback, date(2026, 10, 7), locale="it")

    assert chosen == []
    assert any("riposo" in note or "mobilità" in note for note in notes)
    assert all("injury flag" not in note for note in notes)


def test_italian_notes_cover_event_taper():
    today = date(2026, 10, 7)
    rows = [_row(1, "squat")]
    event = {
        "kind": "ski",
        "priority": 1,
        "starts_at": today + timedelta(days=2),
        "taper_days": 3,
        "title": "Gara",
    }

    _, notes = adjust(rows, [event], [], today, locale="it")

    assert any("scarico" in note for note in notes)
    assert all("taper for" not in note for note in notes)
