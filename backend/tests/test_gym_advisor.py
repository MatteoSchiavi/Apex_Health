"""Pure adjustment-core tests for the adaptive gym advisor (no DB): the
taper rule, the soreness/injury rules, and the rest-day rule."""

from datetime import date, timedelta

from app.services.gym_advisor import adjust

TODAY = date(2026, 9, 22)


def _ex(name, group, pattern, impact="low", sets=4):
    return {
        "exercise_id": 1,
        "name": name,
        "muscle_group": group,
        "movement_pattern": pattern,
        "impact_level": impact,
        "sets": sets,
        "reps_min": 8,
        "reps_max": 12,
        "rest_seconds": 90,
        "notes": None,
    }


def _event(kind, days_from_now, priority=1, taper_days=3, title="Race"):
    return {
        "kind": kind,
        "priority": priority,
        "starts_at": TODAY + timedelta(days=days_from_now),
        "taper_days": taper_days,
        "title": title,
    }


def _leg_day():
    return [
        _ex("Back Squat", "legs", "squat", sets=4),
        _ex("Romanian Deadlift", "legs", "hinge", sets=3),
        _ex("Box Jump", "legs", "plyo", impact="high", sets=4),
        _ex("Plank", "core", "core_anti", sets=3),
    ]


def test_no_adjustments_without_events_or_feedback():
    kept, notes = adjust(_leg_day(), [], [], TODAY)
    assert len(kept) == 4
    assert kept[0]["sets"] == 4
    assert notes == ["no adjustments — full template session (no upcoming priority events, no soreness)"]


def test_taper_halves_legs_and_drops_plyo():
    event = _event("ski", 2)  # Saturday, within 3-day taper
    kept, notes = adjust(_leg_day(), [event], [], TODAY)
    names = {r["name"] for r in kept}
    assert "Box Jump" not in names  # high impact dropped
    squat = next(r for r in kept if r["name"] == "Back Squat")
    assert squat["sets"] == 2  # halved with floor
    assert any("taper" in n for n in notes)
    # core work untouched
    plank = next(r for r in kept if r["name"] == "Plank")
    assert plank["sets"] == 3


def test_taper_outside_window_is_ignored():
    event = _event("ski", 6, taper_days=3)  # beyond the taper window
    kept, notes = adjust(_leg_day(), [event], [], TODAY)
    assert kept[0]["sets"] == 4
    assert "Box Jump" in {r["name"] for r in kept}


def test_low_priority_event_does_not_taper():
    event = _event("ski", 2, priority=3)
    kept, _ = adjust(_leg_day(), [event], [], TODAY)
    assert kept[0]["sets"] == 4


def test_soreness_knees_drops_plyo_and_keeps_legs_light():
    feedback = [{"date": TODAY, "activity_kind": "ski", "rpe": 7, "soreness": ["knees"], "injury_flag": False}]
    kept, notes = adjust(_leg_day(), [], [feedback[0]], TODAY)
    names = {r["name"] for r in kept}
    assert "Box Jump" not in names  # plyo avoided
    assert any("knees" in n for n in notes)


def test_injury_flag_drops_affected_group():
    feedback = [
        {
            "date": TODAY,
            "activity_kind": "ski",
            "rpe": 9,
            "soreness": ["knees"],
            "injury_flag": True,
        }
    ]
    kept, notes = adjust(_leg_day(), [], feedback[0:1], TODAY)
    assert "Plank" in {r["name"] for r in kept}  # core kept
    assert all(r["muscle_group"] != "legs" for r in kept)  # legs dropped
    assert any("injury" in n for n in notes)


def test_rest_day_advice_for_event_tomorrow():
    event = _event("race", 1, title="10k race")
    kept, notes = adjust(_leg_day(), [event], [], TODAY)
    assert all(r["sets"] <= 2 for r in kept)
    assert "Box Jump" not in {r["name"] for r in kept}
    assert any("tomorrow" in n for n in notes)


def test_never_returns_empty_session():
    event = _event("race", 0, title="10k race")
    feedback = [{"date": TODAY, "activity_kind": "ski", "rpe": 10, "soreness": ["knees"], "injury_flag": True}]
    kept, notes = adjust(_leg_day(), [event], feedback[0:1], TODAY)
    assert kept  # always something to do
