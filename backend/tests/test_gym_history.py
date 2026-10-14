"""A–J history-aware gym regression cases, without external services."""
from datetime import date, timedelta
from types import SimpleNamespace
import pytest
from app.models.gym_detail import GymDayExercise, GymDayPlan
from app.models.lab import ChangeAudit
from app.services import gym_advisor as advisor

DAY = date(2026, 10, 9)
USER = SimpleNamespace(id=1, timezone="UTC", locale="en")

def history(group="legs", days=1, sets=9, **extra):
    return {"date": DAY-timedelta(days=days), "groups": {group: sets}, "source": "gym set logs", **extra}

def exercise(ident, name, group, pattern):
    return SimpleNamespace(id=ident, name=name, muscle_group=group, movement_pattern=pattern, impact_level="low")

CATALOG = [exercise(1,"Back Squat","legs","squat"), exercise(2,"Bench Press","push","push_h"),
    exercise(3,"Row","pull","pull_h"), exercise(4,"Plank","core","core_anti"), exercise(5,"Incline Press","push","push_h")]


def test_a_recorded_lower_yesterday_changes_suggestion_with_dated_evidence():
    groups, note = advisor.choose_split(DAY,["legs","core"],[history()])
    assert groups == ["push","pull","core"]
    assert "2026-10-08" in note and "gym set logs" in note and "upper body" in note
    assert "recovered" not in note


def test_b_confirmed_upper_overrides_friday_default():
    groups, note = advisor.choose_split(DAY,["push","pull"],[history()],confirmed=True)
    assert groups == ["push","pull"] and "Lower-body work" not in note


def test_c_intervals_tomorrow_shift_suggestion_but_preserve_confirmation():
    upcoming = [{"date":DAY+timedelta(days=1),"hard":True,"source":"planned_session:12"}]
    groups, note = advisor.choose_split(DAY,["legs"],[],upcoming=upcoming)
    assert groups == ["push","pull","core"] and "2026-10-10" in note and "planned_session:12" in note
    groups, note = advisor.choose_split(DAY,["legs"],[],upcoming=upcoming,confirmed=True)
    assert groups == ["legs"] and "confirmed session retained" in note


def test_d_no_recorded_activity_has_honest_provisional_fallback():
    groups, note = advisor.choose_split(DAY,[],[])
    assert groups == ["legs","core"] and "No recent activity recorded" in note and "unknown" in note


def test_e_strength_without_sets_is_unknown():
    groups,note = advisor.choose_split(DAY,["push"],[history(group="",sets=0,unknown_strength=True)])
    assert groups == ["push"] and "without exercise details" in note and "unknown" in note


def test_h_protected_lower_session_retained_with_reviewable_conflict():
    groups,note = advisor.choose_split(DAY,["legs"],[history()],confirmed=True)
    assert groups == ["legs"] and "confirmed session retained" in note and "Review an upper-body alternative" in note


def test_i_recorded_exercises_preserved_for_progression():
    observed=[history("push",days=3,exercise_ids=[2])]
    first=advisor._catalog_rows(CATALOG,["push"],observed,DAY,[],"")
    second=advisor._catalog_rows(CATALOG,["push"],observed,DAY+timedelta(days=7),[],"")
    assert first[0]["exercise_id"] == second[0]["exercise_id"] == 2


def test_j_multiple_strength_sessions_follow_preferred_split():
    observed=[history("push",days=5),history("pull",days=3),history("legs",days=2)]
    groups,note=advisor.choose_split(DAY,[],observed,preferred_split="push/pull/legs")
    assert groups == ["push","core"] and "recorded work" in note


def test_template_actual_exercises_override_misleading_title():
    groups,ids=advisor._prescription({"title":"Leg day","description":"Bench Press; Row"},CATALOG)
    assert groups == ["push","pull"] and ids == [2,3]
    rows=advisor._catalog_rows(CATALOG,["push"],[],DAY,[2,5],"")
    assert [r["exercise_id"] for r in rows] == [2,5]


class Result:
    def __init__(self,values): self.values=values
    def all(self): return self.values

class MemorySession:
    def __init__(self):
        self.plan=None; self.rows=[]; self.audits=[]; self.has_logs=False
    async def scalar(self,query):
        model=query.column_descriptions[0]["entity"]
        if model is GymDayPlan: return self.plan
        if model is ChangeAudit: return self.audits[-1] if self.audits else None
        return 1 if self.has_logs else None
    async def scalars(self,query): return Result(CATALOG)
    async def execute(self,query): self.rows=[]
    def add(self,obj):
        if isinstance(obj,GymDayPlan): obj.id=33; self.plan=obj
        elif isinstance(obj,GymDayExercise): self.rows.append(obj)
        elif isinstance(obj,ChangeAudit): self.audits.append(obj)
    async def flush(self): pass

@pytest.fixture
def engine(monkeypatch):
    data={"history":[],"intended":[],"upcoming":[],"safety":None,"checks":[],"profile":{},
        "profile_revision":1,"training_focus":["gym"],"complete":True}
    async def inputs(*args): return data
    async def empty(*args,**kwargs): return []
    async def noop(*args,**kwargs): pass
    async def rows(session,plan):
        return [{"exercise_id":r.exercise_id,"muscle_group":next(e.muscle_group for e in CATALOG if e.id==r.exercise_id),
            "sets":r.sets,"reps_min":r.reps_min,"reps_max":r.reps_max,"rest_seconds":r.rest_seconds,"notes":r.notes} for r in session.rows]
    monkeypatch.setattr(advisor,"planning_inputs",inputs)
    monkeypatch.setattr(advisor,"recent_feedback",empty)
    monkeypatch.setattr(advisor,"upcoming_events",empty)
    monkeypatch.setattr(advisor,"_plan_rows",rows)
    monkeypatch.setattr("app.queries.gym.list_slots",empty)
    monkeypatch.setattr("app.services.evidence.scope_lock",noop)
    return MemorySession(),data

async def test_f_repeated_generation_is_idempotent(engine):
    session,_=engine
    first,rows,note=await advisor.generate_day_plan(session,USER,DAY)
    old_rows=list(session.rows)
    second,new_rows,new_note=await advisor.generate_day_plan(session,USER,DAY)
    assert first.id == second.id == 33 and rows==new_rows and note==new_note
    assert session.rows==old_rows and len(session.audits)==1 and session.audits[0].payload["revision"]==1

async def test_g_sync_refreshes_draft_and_audits_previous_revision(engine):
    session,data=engine
    _,before,_=await advisor.generate_day_plan(session,USER,DAY)
    assert any(r["muscle_group"]=="legs" for r in before)
    data["history"]=[history()]
    updated,after,note=await advisor.generate_day_plan(session,USER,DAY)
    assert updated.status=="draft" and all(r["muscle_group"]!="legs" for r in after)
    assert "2026-10-08" in note and len(session.audits)==2
    audit=session.audits[-1]
    assert audit.action=="gym_draft_refreshed" and audit.payload["revision"]==2
    assert audit.payload["before"]["exercises"] and audit.payload["after"]["exercises"]
    assert session.audits[0].payload["input_fingerprint"]!=audit.payload["input_fingerprint"]

@pytest.mark.parametrize("status,has_logs",[("confirmed",False),("done",False),("draft",True)])
async def test_confirmed_completed_and_started_plans_never_mutate(engine,status,has_logs):
    session,data=engine
    plan,before,_=await advisor.generate_day_plan(session,USER,DAY)
    plan.status,session.has_logs=status,has_logs
    data["history"]=[history()]
    _,after,note=await advisor.generate_day_plan(session,USER,DAY)
    assert before==after and plan.status==status and len(session.audits)==1
    assert "confirmed session retained" in note

async def test_approved_exercises_preserved(engine):
    session,data=engine
    data["intended"]=[{"title":"Upper","description":"Bench Press; Row","protected":True,"source":"planned_session:10"}]
    data["history"]=[history()]
    _,rows,_=await advisor.generate_day_plan(session,USER,DAY)
    assert [r["exercise_id"] for r in rows]==[2,3] and data["intended"][0]["protected"] is True

async def test_unknown_approved_prescription_does_not_fabricate_exercises(engine):
    session,data=engine
    data["intended"]=[{"title":"Gym","description":"Follow coach's program","source":"planned_session:10"}]
    _,rows,note=await advisor.generate_day_plan(session,USER,DAY)
    assert rows==[] and "no exercises inferred" in note

async def test_reported_fatigue_reduces_draft_volume(engine):
    session,data=engine
    data["checks"]=[{"id":20,"fatigue":8,"soreness":None}]
    _,rows,note=await advisor.generate_day_plan(session,USER,DAY)
    assert all(r["sets"]<=2 for r in rows) and "Reported fatigue" in note

async def test_approved_structured_strength_preserves_sets_reps_and_load(engine):
    session,data=engine
    data["intended"]=[{"title":"Upper","description":"Legs title is misleading", "protected":True,
        "source":"planned_session:10", "steps":[{"kind":"strength","exercise":"Bench Press","sets":5,"reps":6,"load_kg":70}]}]
    _,rows,_=await advisor.generate_day_plan(session,USER,DAY)
    assert len(rows)==1 and rows[0]["exercise_id"]==2
    assert rows[0]["sets"]==5 and rows[0]["reps_min"]==rows[0]["reps_max"]==6
    assert "70 kg prescribed" in rows[0]["notes"]

async def test_unknown_structured_exercise_stays_unknown_even_with_upper_title(engine):
    session,data=engine
    data["intended"]=[{"title":"Upper","description":"Bench Press","source":"planned_session:10",
        "steps":[{"kind":"strength","exercise":"Uncatalogued rehabilitation exercise","sets":2,"reps":8}]}]
    _,rows,note=await advisor.generate_day_plan(session,USER,DAY)
    assert rows==[] and "no exercises inferred" in note

async def test_canonical_targets_retained_with_safety_conflict(engine):
    session,data=engine
    data["intended"]=[{"title":"Lower","description":"Back Squat","source":"planned_session:10",
        "steps":[{"kind":"strength","exercise":"Back Squat","sets":4,"reps":5}]}]
    data["safety"]={"systemic_stress":90}
    _,rows,note=await advisor.generate_day_plan(session,USER,DAY)
    assert rows[0]["sets"]==4 and rows[0]["reps_min"]==5
    assert "Safety adjustments require review" in note


def test_repeat_blocks_preserve_approved_sequence():
    entry={"steps":[{"kind":"repeat","repetitions":2,"steps":[
        {"kind":"strength","exercise":"Bench Press","sets":2,"reps":8},
        {"kind":"strength","exercise":"Row","sets":2,"reps":10}]}]}
    assert [r["exercise_id"] for r in advisor._programmed_rows(entry,CATALOG)] == [2,3,2,3]

async def test_preferred_rest_day_is_respected(engine):
    session,data=engine
    data["profile"]={"preferred_rest_day":DAY.weekday()}
    _,rows,note=await advisor.generate_day_plan(session,USER,DAY)
    assert rows==[] and "Saved preferred rest day" in note

def test_high_volume_upper_overlap_can_change_suggestion_but_not_confirmed_program():
    recorded=[history("push",sets=8)]
    groups,note=advisor.choose_split(DAY,["push","core"],recorded)
    assert groups==["pull","core"] and "2026-10-08" in note
    groups,note=advisor.choose_split(DAY,["push","core"],recorded,confirmed=True)
    assert groups==["push","core"] and "confirmed session retained" in note

async def test_current_input_fingerprint_detects_history_and_profile_changes_without_writes(engine):
    session,data=engine
    plan,rows,note=await advisor.generate_day_plan(session,USER,DAY)
    stored=session.audits[0].payload["input_fingerprint"]
    assert await advisor.current_input_fingerprint(session,USER,DAY)==stored
    data["history"]=[history()]
    assert await advisor.current_input_fingerprint(session,USER,DAY)!=stored
    assert len(session.audits)==1 and plan.status=="draft" and plan.adjustment_note==note
    data["history"]=[]
    data["profile"]={"gym_split":"upper/lower"}
    data["profile_revision"]=2
    assert await advisor.current_input_fingerprint(session,USER,DAY)!=stored
    assert len(session.audits)==1 and [r.exercise_id for r in session.rows]==[r["exercise_id"] for r in rows]

async def test_generation_takes_shared_evidence_lock_before_day_lock(engine,monkeypatch):
    session,_=engine
    acquired=[]
    async def lock(session,user_id,resource):
        acquired.append(resource)
    monkeypatch.setattr("app.services.evidence.scope_lock",lock)
    await advisor.generate_day_plan(session,USER,DAY)
    assert acquired==["changes",f"gym-plan:{DAY}"]
