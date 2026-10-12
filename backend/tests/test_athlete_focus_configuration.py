"""Canonical focus validation and accepted assertion-history behavior, no DB."""
from datetime import UTC,date,datetime
from types import SimpleNamespace as Row
import pytest
from pydantic import ValidationError
from app.schemas.athlete import AthleteContext,AthleteUpdate
from app.services.athlete_constraints import focus_configuration,meaningful_profile
from app.services.sport_progress import ftp_assertion_history

DAY = date(2026,10,12)


def payload(**context):
    return AthleteUpdate(expected_revision=0,training_focus=["running","cycling"],context=context)


def test_defaults_do_not_make_empty_profile_ready():
    context = AthleteContext().model_dump(mode="json",exclude_none=True)
    assert context["focus_mode"] == "prioritized" and context["supporting_focus"] == []
    assert not meaningful_profile(Row(training_focus=[],context=context))
    assert focus_configuration(None,DAY)["effective_priorities"] == []


def test_balanced_allocations_and_explicit_supporting_context():
    saved = payload(focus_mode="balanced",supporting_focus=["cycling"],weekly_time_budget_min=300,
        weekly_allocation_min={"running":180,"cycling":120})
    profile = Row(training_focus=saved.training_focus,context=saved.context.model_dump(mode="json",exclude_none=True))
    result = focus_configuration(profile,DAY)
    assert result["focus_mode"] == "balanced" and result["supporting_focus"] == ["cycling"]
    assert result["weekly_allocation_min"] == {"running":180,"cycling":120}
    assert meaningful_profile(profile)


@pytest.mark.parametrize("context",[{"supporting_focus":["gym"]},{"supporting_focus":["running","running"]},
    {"weekly_allocation_min":{"gym":30}},{"weekly_time_budget_min":30,"weekly_allocation_min":{"running":31}},
    {"weekly_allocation_min":{"running":-1}},{"weekly_allocation_min":{"running":True}},
    {"weekly_allocation_min":{"running":1.5}},{"focus_mode":"automatic"},
    {"seasonal_focus":[{"starts_on":"2026-01-01","ends_on":"2026-12-31","priorities":["gym"]}]}])
def test_incompatible_unselected_and_invalid_allocations_rejected(context):
    with pytest.raises(ValidationError):
        payload(**context)


def test_seasonal_priorities_date_scoped_and_do_not_invent_sessions():
    saved = payload(seasonal_focus=[{"starts_on":"2026-10-01","ends_on":"2026-10-31","priorities":["cycling"]}])
    profile = Row(training_focus=saved.training_focus,context=saved.context.model_dump(mode="json",exclude_none=True))
    assert focus_configuration(profile,DAY)["effective_priorities"] == ["cycling","running"]
    assert focus_configuration(profile,date(2026,11,1))["effective_priorities"] == ["running","cycling"]
    assert "sessions" not in focus_configuration(profile,DAY)


@pytest.mark.parametrize("seasons",[[{"starts_on":"2026-10-31","ends_on":"2026-10-01","priorities":["running"]}],
    [{"starts_on":"2026-10-01","ends_on":"2026-10-31","priorities":["running","running"]}],
    [{"starts_on":"2026-10-01","ends_on":"2026-10-31","priorities":[]}],
    [{"starts_on":"2026-10-01","ends_on":"2026-10-31","priorities":["running"]},
     {"starts_on":"2026-10-31","ends_on":"2026-11-30","priorities":["cycling"]}]])
def test_seasonal_ranges_increasing_unique_nonempty_and_no_overlap(seasons):
    with pytest.raises(ValidationError):
        payload(seasonal_focus=seasons)


def assertion(ident,watts,measured=DAY,**changes):
    return Row(id=ident,revision=1,date=measured,created_at=datetime(2026,10,12,12,tzinfo=UTC),
        payload={"watts":watts,"measured_on":measured.isoformat(),"source":"user_confirmed",**changes})


def test_ftp_history_preserves_assertions_and_excludes_fractional_estimates():
    rows = [assertion(1,250,date(2026,10,1)),assertion(2,260),assertion(3,270,source="estimated_best_20min_fraction")]
    result = ftp_assertion_history(rows,date(2026,10,1),DAY)
    assert [r["watts"] for r in result["value"]] == [250,260]
    assert all(r["method"] == "explicit_dated_profile_assertion" for r in result["value"])
    assert "no_retroactive_history_backfill" in result["limitations"]
    assert result["source_dependencies"] == ["athlete_entry:1:1","athlete_entry:2:1"]
    assert ftp_assertion_history([],DAY,DAY)["value"] is None
    assert ftp_assertion_history(rows,DAY,DAY,complete=False)["value"] is None


@pytest.mark.asyncio
async def test_canonical_profile_helper_records_only_actual_new_ftp_assertions(monkeypatch):
    from app.api.athlete import write_profile
    from app.models.athlete import AthleteProfile
    from app.models.lab import AthleteEntry
    from app.services import athlete_calendar
    async def calendar(*args):
        return None
    monkeypatch.setattr(athlete_calendar,"sync_profile_events",calendar)
    class Session:
        def __init__(self):
            self.row = None
            self.added = []
        async def get(self,*args,**kwargs):
            return self.row
        def add(self,row):
            self.added.append(row)
            if isinstance(row,AthleteProfile):
                self.row = row
        async def flush(self):
            pass
    session = Session()
    user = Row(id=1)
    first = AthleteUpdate(expected_revision=0,training_focus=["cycling"],context={"ftp":{"watts":250,"measured_on":"2026-10-01","confirmed":True}})
    await write_profile(session,user,first)
    assert len([r for r in session.added if isinstance(r,AthleteEntry)]) == 1
    same = first.model_copy(update={"expected_revision":1})
    await write_profile(session,user,same)
    assert len([r for r in session.added if isinstance(r,AthleteEntry)]) == 1
    changed_notes = AthleteUpdate(expected_revision=1,training_focus=["cycling"],context={"ftp":{"watts":250,"measured_on":"2026-10-01","confirmed":True},"athlete_notes":"Reviewed my goals"})
    await write_profile(session,user,changed_notes)
    assert len([r for r in session.added if isinstance(r,AthleteEntry)]) == 1
    changed_ftp = AthleteUpdate(expected_revision=2,training_focus=["cycling"],context={"ftp":{"watts":260,"measured_on":"2026-10-12","confirmed":True}})
    await write_profile(session,user,changed_ftp)
    histories = [r for r in session.added if isinstance(r,AthleteEntry)]
    assert len(histories) == 2 and histories[-1].payload["source"] == "user_confirmed"
    assert histories[-1].date == DAY and histories[-1].payload["watts"] == 260


@pytest.mark.asyncio
async def test_legacy_ftp_snapshot_is_not_backfilled_on_unrelated_profile_edit(monkeypatch):
    from app.api.athlete import write_profile
    from app.models.athlete import AthleteProfile
    from app.models.lab import AthleteEntry
    from app.services import athlete_calendar
    async def calendar(*args): return None
    monkeypatch.setattr(athlete_calendar,"sync_profile_events",calendar)
    ftp = {"watts":250,"measured_on":"2026-10-01","confirmed":True}
    row = AthleteProfile(user_id=1,training_focus=["cycling"],context={"ftp":ftp},revision=1)
    class Session:
        added = []
        async def get(self,*args,**kwargs): return row
        def add(self,entry): self.added.append(entry)
        async def flush(self): pass
    session = Session()
    await write_profile(session,Row(id=1),AthleteUpdate(expected_revision=1,training_focus=["cycling"],context={"ftp":ftp,"athlete_notes":"Saved context"}))
    assert not any(isinstance(entry,AthleteEntry) for entry in session.added)
