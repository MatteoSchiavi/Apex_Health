"""Seed the UI-era surfaces the phase-9 demo seed predates: AI chat
history, calendar events, challenges + members, and one confirmed gym day
plan — so every web UI page has something honest to render.

Run:  PYTHONPATH=. .venv/bin/python tools/seed_ui_demo.py
"""

import asyncio
import sys
from datetime import UTC, datetime, time, timedelta

from sqlalchemy import delete, select

from app.core.db import sessionmaker
from app.models.chat import AiChatMessage as ChatMessage, AiChatSession as ChatSession
from app.models.challenge import Challenge, ChallengeMember
from app.models.coach import UserEvent
from app.models.gym import GymScheduleSlot
from app.models.gym_detail import GymExercise
from app.models.gym_detail import GymDayExercise, GymDayPlan
from app.models.user import AuthCredential

OWNER_EMAIL = "owner@apexhealth.dev"
FRIEND_EMAIL = "friend@apexhealth.dev"


async def main() -> None:
    async with sessionmaker() as session:
        owner_cred = await session.scalar(
            select(AuthCredential).where(AuthCredential.email == OWNER_EMAIL)
        )
        if owner_cred is None:
            print(f"owner {OWNER_EMAIL} not found — run seed_demo_data.py first")
            sys.exit(1)
        owner_id = owner_cred.user_id

        friend_cred = await session.scalar(
            select(AuthCredential).where(AuthCredential.email == FRIEND_EMAIL)
        )
        friend_id: int | None = friend_cred.user_id if friend_cred else None

        now = datetime.now(UTC)

        # ---- wipe previous UI-seed rows for the owner (idempotent) -------
        from app.models.ai import AgentToolCall

        old_ids = (
            await session.scalars(
                select(ChatSession.id).where(ChatSession.user_id == owner_id)
            )
        ).all()
        for sid in old_ids:
            await session.execute(
                delete(AgentToolCall).where(AgentToolCall.session_id == sid)
            )
            await session.execute(
                delete(ChatMessage).where(ChatMessage.session_id == sid)
            )
        await session.execute(
            delete(ChatSession).where(ChatSession.user_id == owner_id)
        )
        await session.execute(delete(UserEvent).where(UserEvent.user_id == owner_id))
        await session.execute(
            delete(GymDayExercise).where(
                GymDayExercise.gym_day_plan_id.in_(
                    select(GymDayPlan.id).where(GymDayPlan.user_id == owner_id)
                )
            )
        )
        await session.execute(delete(GymDayPlan).where(GymDayPlan.user_id == owner_id))
        await session.execute(delete(GymScheduleSlot).where(GymScheduleSlot.user_id == owner_id))
        await session.execute(
            delete(ChallengeMember).where(ChallengeMember.user_id == owner_id)
        )
        await session.execute(
            delete(Challenge).where(Challenge.created_by == owner_id)
        )

        # ---- AI chat history (two sessions, resumable) --------------------
        s1 = ChatSession(user_id=owner_id, title="HRV dip after the weekend ride",
                         started_at=now - timedelta(days=3),
                         last_activity_at=now - timedelta(days=3, hours=-1))
        s2 = ChatSession(user_id=owner_id, title="Race week plan",
                         started_at=now - timedelta(days=1),
                         last_activity_at=now - timedelta(days=1))
        session.add_all([s1, s2])
        await session.flush()
        msgs1 = [
            ("user", "Why was my HRV so low on Monday? I did a long ride Sunday.", now - timedelta(days=3)),
            ("assistant", "Monday's overnight HRV came in ~18% below your 7-day baseline (42ms → 34ms). "
                          "The likely driver is Sunday's ride: 3h41m at 210 TSS with 42 minutes in threshold — "
                          "your biggest aerobic load in 12 days. Sleep duration was fine (7h22m) but deep sleep "
                          "was on the low side (58m). Expect the baseline to recover by Wednesday if you keep "
                          "today easy.", now - timedelta(days=3)),
            ("user", "Should I do the gym session today?", now - timedelta(days=3)),
            ("assistant", "I'd shift it: your readiness is 61 today. If the knee feels fine, do the upper-body "
                          "slot and leave squats for Thursday when HRV typically rebounds for you.", now - timedelta(days=3, hours=-1)),
        ]
        s1.message_count = len(msgs1)
        session.add_all(ChatMessage(session_id=s1.id, role=r, content=c, created_at=t,
                                    model_tier="powerful" if r == "assistant" else None)
                        for r, c, t in msgs1)
        msgs2 = [
            ("user", "Granfondo is on Sunday. How should the week look?", now - timedelta(days=1)),
            ("assistant", "Taper: keep volume, cut intensity. Tue easy spin 1h, Wed gym (skip heavy legs — "
                          "priority event within 3 days), Thu 3×8min at race pace, Fri rest, Sat 40min with "
                          "4 short pickups. Carbs up from Friday. Your CTL is 74 so the form bounce should be good.", now - timedelta(days=1)),
        ]
        s2.message_count = len(msgs2)
        session.add_all(ChatMessage(session_id=s2.id, role=r, content=c, created_at=t,
                                    model_tier="powerful" if r == "assistant" else None)
                        for r, c, t in msgs2)

        # ---- calendar events ----------------------------------------------
        sunday = now + timedelta(days=(6 - now.weekday()) % 7)
        session.add_all([
            UserEvent(user_id=owner_id, title="Granfondo Il Lombardia", kind="race",
                      starts_at=sunday.replace(hour=8, minute=0), taper_days=5, priority=1,
                      notes="Target event — full taper"),
            UserEvent(user_id=owner_id, title="Ski week — Livigno", kind="ski",
                      starts_at=now + timedelta(days=40), ends_at=now + timedelta(days=47),
                      taper_days=3, priority=1),
            UserEvent(user_id=owner_id, title="Enduro round 1", kind="enduro",
                      starts_at=now + timedelta(days=75), taper_days=4, priority=1),
            UserEvent(user_id=owner_id, title="Sailing weekend", kind="sailing",
                      starts_at=now + timedelta(days=17), ends_at=now + timedelta(days=19),
                      priority=2),
        ])

        # ---- gym weekly slot + one confirmed plan for today ----------------
        session.add(GymScheduleSlot(user_id=owner_id, weekday=now.weekday(),
                                    start_time=time(18, 30), title="Lower strength A"))
        sq_id = await session.scalar(select(GymExercise.id).where(GymExercise.name == "Back Squat"))
        rd_id = await session.scalar(
            select(GymExercise.id).where(GymExercise.name == "Romanian Deadlift")
        )
        plan = GymDayPlan(user_id=owner_id, date=now.date(), status="confirmed",
                          title="Lower strength A (taper-adjusted)",
                          adjustment_note="Priority event in 4 days — heavy squat kept, no plyo block")
        session.add(plan)
        await session.flush()
        exercises = []
        if sq_id:
            exercises.append(GymDayExercise(gym_day_plan_id=plan.id, exercise_id=sq_id, position=1,
                                            sets=4, reps_min=6, reps_max=6, rest_seconds=90))
        if rd_id:
            exercises.append(GymDayExercise(gym_day_plan_id=plan.id, exercise_id=rd_id, position=2,
                                            sets=3, reps_min=8, reps_max=10, rest_seconds=120))
        session.add_all(exercises)

        # ---- challenges + members ------------------------------------------
        ch1 = Challenge(name="September 5k ladder", metric="5k_time_s", period="monthly",
                        starts_at=now - timedelta(days=20), ends_at=now + timedelta(days=10),
                        created_by=owner_id)
        ch2 = Challenge(name="Step war", metric="steps", period="weekly",
                        starts_at=now - timedelta(days=2), ends_at=now + timedelta(days=5),
                        created_by=owner_id)
        session.add_all([ch1, ch2])
        await session.flush()
        session.add(ChallengeMember(challenge_id=ch1.id, user_id=owner_id))
        session.add(ChallengeMember(challenge_id=ch2.id, user_id=owner_id))
        if friend_id:
            session.add(ChallengeMember(challenge_id=ch2.id, user_id=friend_id))

        await session.commit()
        print(f"UI demo seeded for owner {owner_id}"
              + (f" + friend {friend_id}" if friend_id else ""))


asyncio.run(main())
