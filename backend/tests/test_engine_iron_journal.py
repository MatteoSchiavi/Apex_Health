"""Engine logic regression tests for the §7 components that were wired late:

- illness_risk_score.journal_soreness_fatigue (journal module landed Phase 3;
  the seeded 0.10 weight said to activate on landing),
- daily_features.iron_status_flag (labs module landed Phase 4; the flag was
  hardcoded NULL while /status and get_donation_status read it),
- best_mean_power's sliding-window anchors (a hard finish after a quiet
  warm-up must be found, not stepped over).

All expected values are hand-computed from the documented formulas — the
same standard the golden dataset holds the rest of the engine to.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.discipline import best_mean_power
from app.features.engine import compute_user_day
from app.models.features import DailyFeature
from app.models.journal import JournalEntry
from app.models.medical import LabMetric, LabPanel
from app.models.user import User
from app.models.wellness import HrvReading

ROME = ZoneInfo("Europe/Rome")
BASE_DAY = date(2025, 6, 30)  # no DST noise in late June


class _Stream:
    """Minimal duck-typed stream sample for best_mean_power."""

    def __init__(self, t: int, power: float) -> None:
        self.t_offset_s = t
        self.power = power


@pytest_asyncio.fixture
async def hrv_user(db_session: AsyncSession) -> User:
    """A user with a flat 65 ms HRV baseline over [D-28, D-1] and a 45.5 ms
    reading on D (a -30%... dev = (45.5-65)/65*100 = -30.0%)."""
    user = User(name="iron-journal", dob=date(1990, 5, 1), timezone="Europe/Rome")
    db_session.add(user)
    await db_session.flush()

    async def hrv_at(local_day: date, hour: int, ms: float) -> None:
        stamp = datetime(
            local_day.year, local_day.month, local_day.day, hour, tzinfo=ROME
        ).astimezone()
        db_session.add(
            HrvReading(
                user_id=user.id,
                timestamp=stamp,
                hrv_ms=ms,
                reading_type="overnight_avg",
            )
        )

    for offset in range(1, 29):
        await hrv_at(BASE_DAY - timedelta(days=offset), 12, 65.0)
    await hrv_at(BASE_DAY, 7, 45.5)
    await db_session.commit()
    return user


async def fetch_row(session: AsyncSession, user_id: int, day: date) -> DailyFeature:
    row = (
        await session.scalars(
            select(DailyFeature)
            .where(DailyFeature.user_id == user_id, DailyFeature.date == day)
            .execution_options(populate_existing=True)
        )
    ).first()
    assert row is not None, "engine produced no daily row for a wellness day"
    return row


# --- illness: journal component --------------------------------------------


async def test_illness_without_journal_is_hrv_only(hrv_user, db_session):
    """No journal on D: hrv_drop = clamp01(30/30) = 1.0 is the only active
    component -> illness = 1.0 * 100."""
    await compute_user_day(db_session, hrv_user, BASE_DAY)
    row = await fetch_row(db_session, hrv_user.id, BASE_DAY)
    assert float(row.illness_risk_score) == pytest.approx(100.0, abs=1e-6)


async def test_illness_with_max_soreness_journal(hrv_user, db_session):
    """soreness 10 + energy 1 -> journal component (9/9 + 9/9)/2 = 1.0.
    Blend: (0.40*1.0 + 0.10*1.0) / 0.50 = 1.0 -> 100.0 (unchanged — both
    components agree the signal is maximal)."""
    db_session.add(
        JournalEntry(
            user_id=hrv_user.id,
            date=BASE_DAY,
            soreness_score=Decimal(10),
            energy_score=Decimal(1),
            source="telegram_voice",
        )
    )
    await db_session.commit()
    await compute_user_day(db_session, hrv_user, BASE_DAY)
    row = await fetch_row(db_session, hrv_user.id, BASE_DAY)
    assert float(row.illness_risk_score) == pytest.approx(100.0, abs=1e-6)


async def test_illness_journal_renormalizes(hrv_user, db_session):
    """soreness 1 (no signal) + energy 10 (no fatigue): component 0.0.
    Blend: (0.40*1.0 + 0.10*0.0) / 0.50 = 0.8 -> 80.0 — the journal presence
    DILUTES the HRV signal instead of silently padding it."""
    db_session.add(
        JournalEntry(
            user_id=hrv_user.id,
            date=BASE_DAY,
            soreness_score=Decimal(1),
            energy_score=Decimal(10),
            source="telegram_text",
        )
    )
    await db_session.commit()
    await compute_user_day(db_session, hrv_user, BASE_DAY)
    row = await fetch_row(db_session, hrv_user.id, BASE_DAY)
    assert float(row.illness_risk_score) == pytest.approx(80.0, abs=1e-6)


async def test_illness_journal_on_other_day_ignored(hrv_user, db_session):
    """A journal entry dated D-1 must not touch D's illness score."""
    db_session.add(
        JournalEntry(
            user_id=hrv_user.id,
            date=BASE_DAY - timedelta(days=1),
            soreness_score=Decimal(10),
            source="telegram_voice",
        )
    )
    await db_session.commit()
    await compute_user_day(db_session, hrv_user, BASE_DAY)
    row = await fetch_row(db_session, hrv_user.id, BASE_DAY)
    assert float(row.illness_risk_score) == pytest.approx(100.0, abs=1e-6)


# --- iron_status_flag --------------------------------------------------------


async def test_iron_flag_none_without_panels(hrv_user, db_session):
    await compute_user_day(db_session, hrv_user, BASE_DAY)
    row = await fetch_row(db_session, hrv_user.id, BASE_DAY)
    assert row.iron_status_flag is None


async def test_iron_flag_low_then_normal_latest_panel_wins(hrv_user, db_session):
    """Panel D-10 ferritin 21 (< 30 default) -> 'low'; panel D-2 ferritin 80
    -> later recomputes read 'normal'. Historical days keep the flag the
    panels known at the time supported."""
    db_session.add(
        LabPanel(
            user_id=hrv_user.id,
            date=BASE_DAY - timedelta(days=10),
            panel_type="blood",
            ferritin_ng_ml=Decimal(21),
        )
    )
    await db_session.commit()

    await compute_user_day(db_session, hrv_user, BASE_DAY - timedelta(days=9))
    early = await fetch_row(db_session, hrv_user.id, BASE_DAY - timedelta(days=9))
    assert early.iron_status_flag == "low"

    await compute_user_day(db_session, hrv_user, BASE_DAY - timedelta(days=11))
    before_panel = await fetch_row(db_session, hrv_user.id, BASE_DAY - timedelta(days=11))
    assert before_panel.iron_status_flag is None

    db_session.add(
        LabPanel(
            user_id=hrv_user.id,
            date=BASE_DAY - timedelta(days=2),
            panel_type="blood",
            ferritin_ng_ml=Decimal(80),
        )
    )
    await db_session.commit()
    await compute_user_day(db_session, hrv_user, BASE_DAY)
    after = await fetch_row(db_session, hrv_user.id, BASE_DAY)
    assert after.iron_status_flag == "normal"


async def test_iron_flag_lab_reference_low_wins(hrv_user, db_session):
    """A lab-provided ref_low (50) overrides the 30 ng/mL default: ferritin
    40 is 'low' against the lab's own range."""
    panel = LabPanel(
        user_id=hrv_user.id,
        date=BASE_DAY - timedelta(days=5),
        panel_type="blood",
        ferritin_ng_ml=Decimal(40),
    )
    db_session.add(panel)
    await db_session.flush()
    db_session.add(
        LabMetric(
            lab_panel_id=panel.id,
            metric_name="ferritin",
            value=Decimal(40),
            unit="ng/mL",
            ref_low=Decimal(50),
            ref_high=Decimal(300),
        )
    )
    await db_session.commit()
    await compute_user_day(db_session, hrv_user, BASE_DAY - timedelta(days=4))
    row = await fetch_row(db_session, hrv_user.id, BASE_DAY - timedelta(days=4))
    assert row.iron_status_flag == "low"


async def test_iron_flag_ignores_ferritinless_panels(hrv_user, db_session):
    """A newer panel WITHOUT a ferritin value says nothing about iron — the
    older ferritin result stays the latest known."""
    db_session.add(
        LabPanel(
            user_id=hrv_user.id,
            date=BASE_DAY - timedelta(days=10),
            panel_type="blood",
            ferritin_ng_ml=Decimal(21),
        )
    )
    db_session.add(
        LabPanel(
            user_id=hrv_user.id,
            date=BASE_DAY - timedelta(days=1),
            panel_type="blood",
        )
    )
    await db_session.commit()
    await compute_user_day(db_session, hrv_user, BASE_DAY)
    row = await fetch_row(db_session, hrv_user.id, BASE_DAY)
    assert row.iron_status_flag == "low"


async def test_donation_status_includes_iron_flag(hrv_user, db_session):
    """§8.3 get_donation_status carries the iron flag from daily_features
    (None before any panel, then the engine's point-in-time verdict)."""
    from app.queries.labs import get_donation_status

    status = await get_donation_status(db_session, hrv_user.id, BASE_DAY)
    assert status is None  # no donation panel yet — unchanged contract

    db_session.add(
        LabPanel(
            user_id=hrv_user.id,
            date=BASE_DAY - timedelta(days=30),
            panel_type="donation",
            donation_type="whole_blood",
            ferritin_ng_ml=Decimal(45),
            next_eligible_date=BASE_DAY + timedelta(days=60),
        )
    )
    await db_session.commit()
    await compute_user_day(db_session, hrv_user, BASE_DAY)
    status = await get_donation_status(db_session, hrv_user.id, BASE_DAY)
    assert status["donation_type"] == "whole_blood"
    # ferritin 45 >= the 30 ng/mL default -> the engine writes "normal"
    assert status["iron_flag"] == "normal"

    db_session.add(
        LabPanel(
            user_id=hrv_user.id,
            date=BASE_DAY - timedelta(days=3),
            panel_type="blood",
            ferritin_ng_ml=Decimal(21),
        )
    )
    await db_session.commit()
    await compute_user_day(db_session, hrv_user, BASE_DAY)
    status = await get_donation_status(db_session, hrv_user.id, BASE_DAY)
    assert status["iron_flag"] == "low"


# --- best_mean_power window anchors ------------------------------------------

def test_best_mean_power_finds_hard_finish_after_quiet_warmup():
    """0 W for 1000 s then 100 W for 1000 s, window 1500 s: the best window
    starts at t=500 (neither a sample offset nor 0) and reads 66.67 W."""
    streams = [_Stream(0, 0), _Stream(1000, 100), _Stream(2000, 0)]
    assert best_mean_power(streams, 2000, 1500) == pytest.approx(100 * 1000 / 1500)


def test_best_mean_power_effort_anchored_at_sample_unchanged():
    """An effort anchored at a sample offset keeps its exact value."""
    streams = [_Stream(0, 200), _Stream(600, 300), _Stream(1200, 400)]
    assert best_mean_power(streams, 2400, 1200) == pytest.approx(400.0)


def test_best_mean_power_window_longer_than_activity():
    assert best_mean_power([_Stream(0, 250)], 600, 1200) is None
