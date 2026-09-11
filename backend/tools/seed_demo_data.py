"""Seed the local dev database with a realistic ~180-day demo dataset.

Purpose: give the temporary Grafana web UI (grafana/ in the repo root) real,
meaningful data for every feature surface built in Phases 0-8 — activities,
sleep/HRV/stress, biometrics, feature-engine outputs, nutrition, supplements,
journal + Telegram voice flow, lab panels, gear, plans, AI sessions/tool
calls/token budget, reports, embeddings, forecasts, raw ingest, rollups.

Deterministic (seed 42). TRUNCATEs all user data first; migration seeds
(disciplines, feature_weights) are kept. Re-runnable at any time.

Usage (from backend/, with venv and env exported):
    .venv/bin/python tools/seed_demo_data.py [--days 180]

Owner login after seeding: owner@apexhealth.dev / demo-owner-1234
"""

import argparse
import asyncio
import json
import math
import random
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select, text

from app.core.db import sessionmaker
from app.core.security import hash_password
from app.models.activity import (
    Activity,
    ActivitySourceLink,
    ActivityStream,
    Discipline,
)
from app.models.ai import (
    AgentToolCall,
    AiReport,
    Embedding,
    TokenUsage,
)
from app.models.alert import Alert
from app.models.chat import AiChatMessage, AiChatSession
from app.models.features import DailyFeature, DisciplineFeature
from app.models.gear import (
    ActivityGearLink,
    DisciplineGearDefault,
    Gear,
    GearServiceLog,
)
from app.models.integration import Integration, RawIngest
from app.models.journal import JournalEntry
from app.models.medical import (
    LabMetric,
    LabPanel,
    NutritionLog,
    SupplementLog,
    SupplementProtocol,
)
from app.medical.labs import encrypt_notes
from app.models.telegram import TelegramLink, TelegramMessage
from app.models.training import PlannedSession, TrainingPlan
from app.models.user import AuthCredential, User, UserSession
from app.models.weather import ForecastCache
from app.models.wellness import (
    DailyBiometric,
    HrvReading,
    SleepSession,
    StressReading,
)

UTC = timezone.utc
TOOL_NAMES = [
    "get_metric_trend", "get_lab_trend", "get_activity_summary",
    "get_journal_entries", "search_context", "get_training_plan",
    "get_donation_status", "get_gear_status", "propose_training_plan",
    "propose_supplement_change", "sync_plan_to_technogym",
]
TRUNCATE_TABLES = """TRUNCATE agent_tool_calls, ai_chat_messages, ai_chat_sessions,
ai_reports, alerts, auth_credentials, daily_biometrics, daily_features,
discipline_features, discipline_gear_defaults, embeddings, forecast_cache,
gear, gear_service_logs, hrv_readings, integrations, invites,
journal_entries, lab_metrics, lab_panels, monthly_rollups, nutrition_logs,
planned_sessions, raw_ingest, segment_efforts, segments, sessions,
sleep_sessions, stress_readings, supplement_logs, supplement_protocols,
technogym_sync_log, telegram_links, telegram_messages, token_usage,
training_plans, users, watch_sync_log,
activities, activity_gear_links, activity_source_links, activity_streams
RESTART IDENTITY CASCADE"""


def D(x: float) -> float:
    """Round to 2dp — numeric columns land clean."""
    return round(float(x), 2)


async def wipe(session) -> None:
    await session.execute(text(TRUNCATE_TABLES))


async def seed_owner(session) -> User:
    user = User(
        name="Demo Owner", dob=date(1988, 4, 12), sex="M",
        height_cm=180.0, weight_goal_direction="lose",
        timezone="Europe/Rome",
    )
    session.add(user)
    await session.flush()
    session.add(AuthCredential(
        user_id=user.id, email="owner@apexhealth.dev",
        password_hash=hash_password("demo-owner-1234"),
        role="owner", ai_access_tier="full", share_segments=True,
    ))
    now = datetime.now(UTC)
    session.add(UserSession(user_id=user.id, token_hash="demo" + "a" * 60,
                            created_at=now - timedelta(days=3),
                            expires_at=now + timedelta(days=4)))
    session.add(UserSession(user_id=user.id, token_hash="demo" + "b" * 60,
                            created_at=now - timedelta(days=1),
                            expires_at=now + timedelta(days=6)))
    session.add(UserSession(user_id=user.id, token_hash="demo" + "c" * 60,
                            created_at=now - timedelta(days=30),
                            expires_at=now - timedelta(days=1)))
    session.add(TelegramLink(user_id=user.id, chat_id=550123456,
                             linked_at=now - timedelta(days=120)))
    session.add(Integration(
        user_id=user.id, provider="garmin", status="active",
        credentials_encrypted=b"demo-encrypted-creds",
        consecutive_failures=0, last_synced_at=now - timedelta(hours=2),
        created_at=now - timedelta(days=170),
    ))
    session.add(Integration(
        user_id=user.id, provider="technogym", status="active",
        credentials_encrypted=b"demo-encrypted-creds",
        consecutive_failures=0, last_synced_at=now - timedelta(hours=9),
        created_at=now - timedelta(days=60),
    ))
    return user


async def seed_gear(session, user_id: int) -> dict[str, Gear]:
    bike = Gear(user_id=user_id, name="Road Bike", gear_type="bike",
                acquired_date=date.today() - timedelta(days=400),
                service_interval_km=800.0, hours_since_service=D(112.0),
                km_since_service=D(2150.0), active=True)
    shoes = Gear(user_id=user_id, name="Running Shoes", gear_type="shoes",
                 acquired_date=date.today() - timedelta(days=150),
                 service_interval_km=700.0, hours_since_service=None,
                 km_since_service=D(512.0), active=True)
    trainer = Gear(user_id=user_id, name="Trainer", gear_type="trainer",
                   acquired_date=date.today() - timedelta(days=500),
                   service_interval_hours=250.0, hours_since_service=D(88.0),
                   km_since_service=None, active=True)
    session.add_all([bike, shoes, trainer])
    await session.flush()
    session.add_all([
        GearServiceLog(gear_id=bike.id, service_type="chain replacement",
                       performed_at=datetime.now(UTC) - timedelta(days=70),
                       notes="full drivetrain degrease + new chain"),
        GearServiceLog(gear_id=trainer.id, service_type="belt check",
                       performed_at=datetime.now(UTC) - timedelta(days=120),
                       notes=None),
    ])
    return {"bike": bike, "shoes": shoes, "trainer": trainer}


def plan_day(rng: random.Random, day: date) -> tuple[str, str] | None:
    """(discipline, session flavour) or None for a rest day."""
    wd = day.weekday()  # 0=Mon
    if rng.random() < 0.10:
        return None
    if wd in (1, 3):            # Tue/Thu
        return ("running", "intervals" if rng.random() < 0.4 else "easy")
    if wd == 5:                 # Sat
        return ("road_cycling", "long") if rng.random() < 0.65 else ("running", "long_run")
    if wd == 6:                 # Sun
        return ("running", "recovery") if rng.random() < 0.5 else None
    if wd in (0, 4):            # Mon/Fri
        return ("strength", "full_body")
    return ("road_cycling", "tempo") if rng.random() < 0.5 else ("gym_general", "mobility")


def make_activity(rng: random.Random, user_id: int, disc: Discipline,
                  day: date, flavour: str) -> Activity:
    start_h, start_m = rng.choice([(6, 40), (7, 15), (12, 30), (17, 45), (18, 30)])
    start = datetime(day.year, day.month, day.day, start_h, start_m, tzinfo=UTC)
    if disc.name == "running":
        if flavour == "intervals":
            dur, pace = rng.randint(2900, 3800), rng.uniform(0.155, 0.170)
            hr, power = rng.randint(148, 162), None
        elif flavour == "long_run":
            dur, pace = rng.randint(4800, 6600), rng.uniform(0.170, 0.185)
            hr, power = rng.randint(135, 148), None
        elif flavour == "recovery":
            dur, pace = rng.randint(1800, 2600), rng.uniform(0.195, 0.215)
            hr, power = rng.randint(118, 130), None
        else:
            dur, pace = rng.randint(2200, 3600), rng.uniform(0.165, 0.180)
            hr, power = rng.randint(132, 148), None
        dist = dur / 60 * pace * 1000
        cal = int(dur * rng.uniform(9.5, 11.5))
        load = D(dur / 60 * rng.uniform(65, 105))
    elif disc.name == "road_cycling":
        if flavour == "long":
            dur = rng.randint(7200, 12000)
        elif flavour == "tempo":
            dur = rng.randint(3600, 5400)
        else:
            dur = rng.randint(3000, 4200)
        dist = dur / 60 * rng.uniform(0.35, 0.46) * 1000
        hr = rng.randint(124, 146)
        power = D(rng.uniform(145, 215))
        cal = int(dur * rng.uniform(8.0, 10.5))
        load = D(dur / 60 * rng.uniform(55, 95))
    elif disc.name in ("strength", "gym_general"):
        dur, hr, power = rng.randint(2700, 4500), rng.randint(102, 128), None
        dist, cal = None, int(dur * rng.uniform(4.5, 6.5))
        load = D(dur / 60 * rng.uniform(30, 55))
    else:  # tennis / others
        dur, hr, power = rng.randint(3600, 6000), rng.randint(128, 152), None
        dist, cal = None, int(dur * rng.uniform(7.0, 9.0))
        load = D(dur / 60 * rng.uniform(45, 80))
    max_hr = min(hr + rng.randint(18, 34), 196)
    snap = None
    if rng.random() < 0.85:
        tmax = rng.uniform(12, 34)
        snap = {
            "temperature_2m_mean": D(tmax - rng.uniform(4, 8)),
            "temperature_2m_max": D(tmax),
            "temperature_2m_min": D(tmax - rng.uniform(8, 14)),
            "wind_speed_10m_max": D(rng.uniform(3, 38)),
            "weather_code": rng.choice([0, 1, 1, 2, 3, 45, 51, 61, 63, 80, 95]),
        }
    return Activity(
        user_id=user_id, discipline_id=disc.id, start_time=start,
        start_tz_offset_minutes=120, local_date=day,
        duration_s=dur, distance_m=D(dist) if dist else None,
        elevation_gain_m=D(rng.uniform(0, 620)) if disc.name in ("running", "road_cycling") else None,
        avg_hr=hr, max_hr=max_hr, avg_power=power,
        np_power=D(power * 1.12) if power else None,
        calories=cal, training_load=load,
        data_completeness="full" if rng.random() < 0.9 else "partial",
        weather_snapshot=snap,
    )


async def seed_activities(session, user_id: int, days: int, rng: random.Random):
    discs = {d.name: d for d in
             (await session.execute(select(Discipline))).scalars()}
    gear = {"bike": None, "shoes": None}
    gear_rows = (await session.execute(
        select(Gear).where(Gear.user_id == user_id))).scalars().all()
    for g in gear_rows:
        gear[g.gear_type] = g
    if gear["bike"]:
        await session.execute(text(
            "INSERT INTO discipline_gear_defaults (user_id, discipline_id, gear_id) "
            "SELECT :u, id, :g FROM disciplines WHERE name='road_cycling'"),
            {"u": user_id, "g": gear["bike"].id})
    loads: dict[date, float] = {}
    acts = []
    for back in range(days, 0, -1):
        day = date.today() - timedelta(days=back - 1)
        picked = plan_day(rng, day)
        if picked is None:
            continue
        dname, flavour = picked
        disc = discs.get(dname)
        if disc is None:
            continue
        act = make_activity(rng, user_id, disc, day, flavour)
        session.add(act)
        acts.append((act, disc, flavour))
        loads[day] = loads.get(day, 0.0) + float(act.training_load or 0)
    await session.flush()

    # source links — every activity came from somewhere
    for act, disc, flavour in acts:
        source = "garmin" if disc.name not in ("strength", "gym_general") else \
                 ("technogym" if rng.random() < 0.6 else "garmin")
        session.add(ActivitySourceLink(
            activity_id=act.id, source=source,
            external_id=f"{source}-demo-{act.id}", raw_ingest_id=None))
        g = gear["bike"] if disc.name == "road_cycling" else \
            gear["shoes"] if disc.name == "running" else None
        if g is not None and rng.random() < 0.9:
            session.add(ActivityGearLink(activity_id=act.id, gear_id=g.id))

    # streams for the six most recent outdoor activities
    outdoor = [(a, d, f) for a, d, f in acts
               if d.name in ("running", "road_cycling")][-6:]
    for act, disc, _ in outdoor:
        n = max(2, act.duration_s // 60)
        base = float(act.avg_hr or 130)
        for i in range(min(n, 90)):
            t = act.start_time + timedelta(seconds=i * (act.duration_s / min(n, 90)))
            hr = base + 6 * math.sin(i / 7) + rng.uniform(-4, 6)
            session.add(ActivityStream(
                activity_id=act.id, t_offset_s=int(i * (act.duration_s / min(n, 90))),
                hr=int(min(hr, act.max_hr or 190)),
                power=D((act.avg_power or 0) * rng.uniform(0.85, 1.2)) or None
                if act.avg_power else None,
                cadence=D(rng.uniform(80, 94)) if disc.name == "road_cycling" else D(rng.uniform(160, 178)),
                speed=D(rng.uniform(2.5, 6.5)) if disc.name == "running" else D(rng.uniform(7, 12)),
                altitude=D(rng.uniform(20, 180)), lat=D(rng.uniform(41.85, 41.95)),
                lon=D(rng.uniform(12.45, 12.55))))
    return acts, loads, discs

async def seed_wellness(session, user_id: int, days: int, rng: random.Random,
                        loads: dict[date, float]) -> dict:
    """Sleep, HRV, stress, biometrics, daily features — one correlated story."""
    weight, sick_start, sick_end = 78.9, days - 40, days - 34
    hrv_hist: list[float] = []
    feat_rows: list[dict] = []
    low_ferritin_day = date.today() - timedelta(days=90)
    for back in range(days, 0, -1):
        day = date.today() - timedelta(days=back - 1)
        sick = sick_start <= back <= sick_end
        day_load = loads.get(day, 0.0)
        # --- sleep ---
        sleep = None
        if rng.random() < 0.93:
            total = int(rng.uniform(6.1, 8.5) * 3600 + min(900, day_load * 0.8))
            deep = int(total * rng.uniform(0.12, 0.20))
            rem = int(total * rng.uniform(0.18, 0.26))
            awake = int(total * rng.uniform(0.03, 0.07))
            light = total - deep - rem - awake
            start = datetime(day.year, day.month, day.day, tzinfo=UTC) \
                - timedelta(minutes=rng.randint(40, 160))
            end = start + timedelta(seconds=total + awake)
            score = max(45.0, min(97.0, 55 + 42 * (total / 30600) + rng.uniform(-6, 6)
                                  - (8 if sick else 0)))
            sleep = SleepSession(
                user_id=user_id, local_date=day, start_time=start, end_time=end,
                total_sleep_s=total, deep_s=deep, light_s=light, rem_s=rem,
                awake_s=awake, sleep_score=D(score),
                respiration_avg=D(rng.uniform(13.2, 16.4)),
                spo2_avg=D(rng.uniform(94.5, 98.2)),
                restlessness=D(rng.uniform(0.05, 0.28)))
            session.add(sleep)
        # --- HRV ---
        val = 62 + 8 * math.sin(back / 23) + rng.uniform(-7, 7) - (20 if sick else 0)
        hrv_hist.append(val)
        window = hrv_hist[-15:-1]
        baseline = D(sum(window) / len(window)) if len(window) >= 7 else D(val)
        session.add(HrvReading(
            user_id=user_id,
            timestamp=datetime(day.year, day.month, day.day, 7, 0, tzinfo=UTC),
            hrv_ms=D(val), reading_type="overnight_avg", rolling_baseline_ms=baseline))
        # --- stress ---
        battery = 88
        for hh in (10, 15, 20):
            battery = max(18, battery - rng.randint(15, 30) - (8 if sick else 0))
            session.add(StressReading(
                user_id=user_id,
                timestamp=datetime(day.year, day.month, day.day, hh, rng.randint(0, 59), tzinfo=UTC),
                stress_level=D(rng.uniform(15, 70)), body_battery=battery))
        # --- biometrics ---
        weight = max(76.0, weight - 0.012 + rng.uniform(-0.18, 0.18))
        session.add(DailyBiometric(
            user_id=user_id, date=day,
            resting_hr=int(rng.randint(48, 56) + (6 if sick else 0)),
            weight_kg=D(weight),
            body_fat_pct=D(max(15.0, 17.8 - (days - back) * 0.012 + rng.uniform(-0.3, 0.3))),
            vo2max=D(51.5 + (days - back) * 0.006 + rng.uniform(-0.4, 0.4)),
            steps=int(rng.randint(5000, 9000) + (7000 if day_load > 200 else 0) - (4000 if sick else 0)),
            floors=int(rng.randint(4, 22)), spo2_avg=D(rng.uniform(95.5, 98.4)),
            hydration_ml=int(rng.randint(1800, 3500))))
        # --- feature-engine outputs ---
        hrv_dev = (val - baseline) / max(baseline, 1.0)
        sleep_q = (sleep.sleep_score if sleep else 70) - 75
        recovery = max(28.0, min(97.0, 62 + hrv_dev * 160 + sleep_q * 0.45 - (18 if sick else 0)))
        readiness = max(25.0, min(98.0, recovery * 0.6 + (sleep.sleep_score if sleep else 70) * 0.4 - (10 if sick else 0)))
        strain = max(8.0, min(82.0, day_load / 9.0 + rng.uniform(-3, 3)))
        acute = sum(loads.get(day - timedelta(days=k), 0.0)
                    for k in range(0, min(7, days)))
        chronic = sum(loads.get(day - timedelta(days=k), 0.0)
                      for k in range(0, min(28, days))) / 4.0
        feat_rows.append(dict(
            day=day, recovery=D(recovery), readiness=D(readiness), strain=D(strain),
            acute=D(acute), chronic=D(chronic),
            acwr=D(acute / chronic) if chronic > 5 else None,
            sleep_arch=D(rng.uniform(58, 92)), hrv_dev=D(hrv_dev * 100),
            illness=D(max(0.0, min(0.9, 0.08 + (0.65 if sick else 0) - readiness / 250))),
            injury=D(max(0.0, min(0.85, 0.1 + max(0.0, (day_load - 500)) / 2500
                                    + (0.15 if (feat_rows and feat_rows[-1]["strain"] > 65) else 0)))),
            iron="low" if 0 <= (low_ferritin_day - day).days <= 30 else "normal",
            fatigue=D(rng.uniform(0.1, 0.6)),
            completeness="full" if rng.random() < 0.92 else "partial"))
    await session.flush()
    for r in feat_rows:
        session.add(DailyFeature(
            user_id=user_id, date=r["day"], recovery_score=r["recovery"],
            strain_score=r["strain"], readiness_score=r["readiness"],
            training_load_acute=r["acute"], training_load_chronic=r["chronic"],
            acwr=r["acwr"], sleep_architecture_score=r["sleep_arch"],
            hrv_deviation_from_baseline=r["hrv_dev"], illness_risk_score=r["illness"],
            injury_risk_score=r["injury"], iron_status_flag=r["iron"],
            cross_discipline_fatigue_index=r["fatigue"],
            data_completeness=r["completeness"]))
    # discipline features for cycling days
    ftp_base = 205.0
    for back in range(days, 0, -1):
        day = date.today() - timedelta(days=back - 1)
        if loads.get(day, 0) > 150 and rng.random() < 0.45:
            ftp_base = min(232.0, ftp_base + 0.12)
            session.add(DisciplineFeature(
                user_id=user_id,
                discipline_id=(await session.execute(
                    text("SELECT id FROM disciplines WHERE name='road_cycling'")))
                .scalar_one(), date=day, estimated_ftp=D(ftp_base),
                aerobic_decoupling_pct=D(rng.uniform(1.5, 9.0)),
                efficiency_factor=D(rng.uniform(0.95, 1.28))))
    await session.flush()
    return {"feat_rows": feat_rows, "weight": weight}


async def seed_nutrition(session, user_id: int, days: int, rng: random.Random):
    for back in range(days, 0, -1):
        day = date.today() - timedelta(days=back - 1)
        kcal = rng.randint(2250, 3050)
        protein = rng.uniform(125, 175)
        carbs = kcal * rng.uniform(0.42, 0.5) / 4
        fat = (kcal - protein * 4 - carbs * 4) / 9
        for slot, (hh, share) in enumerate([(8, 0.25), (12, 0.35), (19, 0.40)]):
            session.add(NutritionLog(
                user_id=user_id,
                timestamp=datetime(day.year, day.month, day.day, hh, rng.randint(0, 59), tzinfo=UTC),
                source="telegram" if rng.random() < 0.25 else "manual",
                calories=int(kcal * share), protein_g=D(protein * share),
                carbs_g=D(carbs * share), fat_g=D(fat * share),
                water_ml=int(rng.uniform(200, 500)), alcohol_units=None,
                caffeine_mg=None))
        session.add(NutritionLog(
            user_id=user_id,
            timestamp=datetime(day.year, day.month, day.day, 9, 15, tzinfo=UTC),
            source="manual", calories=None, protein_g=None, carbs_g=None,
            fat_g=None, water_ml=None, alcohol_units=None,
            caffeine_mg=int(rng.uniform(90, 210))))
        session.add(NutritionLog(
            user_id=user_id,
            timestamp=datetime(day.year, day.month, day.day, 21, 0, tzinfo=UTC),
            source="manual", calories=None, protein_g=None, carbs_g=None,
            fat_g=None, water_ml=int(rng.uniform(1200, 2600)), alcohol_units=None,
            caffeine_mg=None))
        if rng.random() < 0.08:
            session.add(NutritionLog(
                user_id=user_id,
                timestamp=datetime(day.year, day.month, day.day, 21, 30, tzinfo=UTC),
                source="manual", calories=None, protein_g=None, carbs_g=None,
                fat_g=None, water_ml=None, alcohol_units=D(rng.uniform(1.0, 3.0)),
                caffeine_mg=None))
    prot_d = SupplementProtocol(user_id=user_id, supplement_name="Vitamin D3",
                                dose="2000 IU", schedule_cron="0 8 * * *",
                                active=True, start_date=date.today() - timedelta(days=120),
                                reason="indoor training blocks")
    prot_fe = SupplementProtocol(user_id=user_id, supplement_name="Iron bisglycinate",
                                 dose="18 mg", schedule_cron="0 9 * * *",
                                 active=True, start_date=date.today() - timedelta(days=88),
                                 reason="post-donation ferritin recovery")
    prot_om = SupplementProtocol(user_id=user_id, supplement_name="Omega-3",
                                 dose="1000 mg", schedule_cron="0 8 * * *",
                                 active=True, start_date=date.today() - timedelta(days=200),
                                 reason=None)
    prot_cr = SupplementProtocol(user_id=user_id, supplement_name="Creatine monohydrate",
                                 dose="5 g", schedule_cron="0 8 * * *",
                                 active=True, start_date=date.today() - timedelta(days=300),
                                 reason=None)
    session.add_all([prot_d, prot_fe, prot_om, prot_cr])
    await session.flush()
    for back in range(60):
        taken = datetime.now(UTC) - timedelta(days=back, hours=rng.randint(6, 9))
        for p in (prot_d, prot_fe, prot_om, prot_cr):
            if back == 0 and p is prot_fe:
                continue
            if rng.random() < 0.9:
                session.add(SupplementLog(protocol_id=p.id, taken_at=taken, adherence=True))
            elif rng.random() < 0.5:
                session.add(SupplementLog(protocol_id=p.id, taken_at=taken, adherence=False))


JOURNAL_NOTES = [
    "Legs felt heavy on the last intervals — probably the travel week.",
    "Great long ride along the coast, fuelling worked perfectly.",
    "Slept badly, kept the session short and easy.",
    "New shoes feel fast, toes fine after 12km.",
    "Stress day at work, skipped strength and walked instead.",
    "Body battery recovered well after the donation week.",
    "Track session: 8x400 at 3:05 pace, last two were 3:00.",
    "Rest day — long walk, stretching, early night.",
]
JOURNAL_TAGS = ["recovery", "race_prep", "travel", "long_ride", "strength", "nutrition"]


async def seed_journal(session, user_id: int, days: int, rng: random.Random):
    entries = []
    for back in range(days, 1, -1):
        if rng.random() < 0.55:
            continue
        day = date.today() - timedelta(days=back - 1)
        voice = rng.random() < 0.22
        note = rng.choice(JOURNAL_NOTES)
        e = JournalEntry(
            user_id=user_id, date=day,
            mood_score=D(rng.uniform(5, 9.5)), energy_score=D(rng.uniform(4, 9.5)),
            motivation_score=D(rng.uniform(4.5, 9.5)), soreness_score=D(rng.uniform(1, 6)),
            stress_subjective=D(rng.uniform(1, 7)), sleep_quality_subjective=D(rng.uniform(4, 9.5)),
            free_text_notes=note, tags=rng.sample(JOURNAL_TAGS, k=rng.randint(0, 2)),
            source="telegram_voice" if voice else "web",
            raw_transcript=note if voice else None)
        session.add(e)
        entries.append(e)
    await session.flush()
    # Telegram voice notes — some confirmed into journal entries, some rejected, some pending
    for i, e in enumerate(entries):
        if e.source != "voice" or i % 3 == 2:
            continue
        status = "confirmed" if i % 3 == 0 else "rejected"
        session.add(TelegramMessage(
            chat_id=550123456, message_id=9000 + i,
            voice_file_id=f"voice-demo-{i}", raw_transcript=e.free_text_notes,
            extracted_json={"kind": "journal", "mood": float(e.mood_score),
                            "energy": float(e.energy_score), "note": e.free_text_notes},
            status=status,
            linked_journal_entry_id=e.id if status == "confirmed" else None,
            created_at=datetime(e.date.year, e.date.month, e.date.day, 8, 30, tzinfo=UTC)))
    for p in range(3):
        session.add(TelegramMessage(
            chat_id=550123456, message_id=9500 + p, voice_file_id=f"voice-pending-{p}",
            raw_transcript="Felt good today, easy 40 minutes and solid sleep.",
            extracted_json={"kind": "journal", "mood": 7.5, "energy": 7.0,
                            "note": "Felt good today, easy 40 minutes and solid sleep."},
            status="pending", linked_journal_entry_id=None,
            created_at=datetime.now(UTC) - timedelta(days=p, hours=5)))
    await session.flush()
    return entries


async def seed_labs(session, user_id: int, rng: random.Random):
    panels = [
        (150, None, 15.0, 44.1, 86.0, None, "baseline panel — all nominal"),
        (120, "whole_blood", 14.1, 42.3, 52.0, date.today() - timedelta(days=64),
         "post-donation panel"),
        (90, None, 13.8, 41.9, 24.0, None, "ferritin below threshold — alert fired"),
        (35, None, 14.6, 43.0, 38.0, None, "recovering"),
        (5, "plasma", 15.1, 44.6, 46.0, date.today() + timedelta(days=23),
         "plasma donation — fully restored"),
    ]
    for back, don, hgb, hct, ferr, elig, note in panels:
        p = LabPanel(
            user_id=user_id, date=date.today() - timedelta(days=back),
            panel_type="blood_panel", donation_type=don,
            hemoglobin_g_dl=D(hgb), hematocrit_pct=D(hct), ferritin_ng_ml=D(ferr),
            iron=D(rng.uniform(60, 140)), wbc=D(rng.uniform(4.6, 7.2)),
            plt=D(rng.uniform(190, 280)), next_eligible_date=elig,
            source="lab_pdf", notes_ciphertext=encrypt_notes(note))
        session.add(p)
        await session.flush()
        extras = [("Vitamin D (25-OH)", D(rng.uniform(28, 62)), "ng/mL", 30, 100),
                  ("LDL cholesterol", D(rng.uniform(78, 118)), "mg/dL", 0, 116),
                  ("HDL cholesterol", D(rng.uniform(48, 72)), "mg/dL", 40, 100),
                  ("TSH", D(rng.uniform(0.9, 3.4)), "mIU/L", 0.4, 4.0),
                  ("Fasting glucose", D(rng.uniform(78, 96)), "mg/dL", 70, 100)]
        for name, val, unit, lo, hi in extras:
            session.add(LabMetric(lab_panel_id=p.id, metric_name=name, value=val,
                                  unit=unit, ref_low=lo, ref_high=hi))
    session.add(Alert(
        user_id=user_id, type="low_ferritin", severity="warning",
        triggered_at=datetime.now(UTC) - timedelta(days=90),
        acknowledged=True,
        message="Ferritin 24 ng/mL — below the 30 ng/mL threshold. Iron protocol started."))


async def seed_plans(session, user_id: int, discs, rng: random.Random):
    monday = date.today() - timedelta(days=date.today().weekday())
    run = discs["running"]
    plan = TrainingPlan(user_id=user_id, discipline_id=run.id, created_by="ai",
                        week_start=monday, status="active", source_ai_report_id=None,
                        created_at=datetime.now(UTC) - timedelta(days=21))
    draft = TrainingPlan(user_id=user_id, discipline_id=discs["road_cycling"].id,
                         created_by="ai", week_start=monday + timedelta(days=7),
                         status="draft", source_ai_report_id=None,
                         created_at=datetime.now(UTC) - timedelta(days=3))
    session.add_all([plan, draft])
    await session.flush()
    for off, stype, tmin, tload, desc in [
            (1, "easy", 40, 45, "Z1-Z2 run, strides at the end"),
            (2, "intervals", 55, 95, "8x400m @ 3K pace, 90s jog"),
            (4, "easy", 45, 50, "conversation pace, soft surface"),
            (6, "long_run", 90, 140, "progressive long run, last 20min @ marathon effort")]:
        session.add(PlannedSession(
            training_plan_id=plan.id, date=monday + timedelta(days=off - 1),
            discipline_id=run.id, session_type=stype, target_duration_min=tmin,
            target_load=D(tload), description=desc, technogym_program_id=None))
    for off, stype, tmin, tload, desc in [
            (2, "tempo", 70, 110, "3x12min sweet spot"),
            (5, "endurance", 150, 180, "endurance ride, flat route")]:
        session.add(PlannedSession(
            training_plan_id=draft.id, date=monday + timedelta(days=off + 6),
            discipline_id=discs["road_cycling"].id, session_type=stype,
            target_duration_min=tmin, target_load=D(tload), description=desc,
            technogym_program_id=None))


async def seed_ai(session, user_id: int, days: int, rng: random.Random,
                  journal_entries: list):
    now = datetime.now(UTC)
    tool_calls = 0
    sessions_rows = []
    for back in range(0, min(60, days)):
        if rng.random() < 0.55:
            continue
        started = now - timedelta(days=back, hours=rng.randint(1, 12))
        s = AiChatSession(user_id=user_id, started_at=started,
                          last_activity_at=started + timedelta(minutes=rng.randint(2, 25)))
        session.add(s)
        sessions_rows.append(s)
    await session.flush()
    prompts = ["How is my recovery trending this week?",
               "Compare my HRV to my last lab panel",
               "What did my longest rides look like last month?",
               "Should I move tomorrow's intervals?",
               "Any signs I should take an extra rest day?",
               "Summarize my sleep over the last two weeks"]
    for i, s in enumerate(sessions_rows):
        tier = "powerful" if rng.random() < 0.3 else "free"
        q = rng.choice(prompts)
        session.add(AiChatMessage(session_id=s.id, role="user", content=q,
                                  model_tier=tier, referenced_data=None,
                                  created_at=s.started_at))
        session.add(AiChatMessage(
            session_id=s.id, role="assistant",
            content="Based on your last 30 days: HRV is trending up ~4%, "
                    "acute load is stable, and last night's sleep scored "
                    f"{rng.randint(72, 93)}. Recovery looks good for a quality session.",
            model_tier=tier, referenced_data={"tools_used": 2},
            created_at=s.started_at + timedelta(seconds=45)))
        for c in range(rng.randint(1, 4)):
            err = "tool timed out after 2000ms" if rng.random() < 0.05 else None
            session.add(AgentToolCall(
                session_id=s.id, tool_name=rng.choice(TOOL_NAMES),
                input_json={"days": rng.choice([7, 30, 90])},
                output_json=None if err else {"rows": rng.randint(1, 60)},
                error=err, latency_ms=rng.randint(80, 2100),
                created_at=s.started_at + timedelta(seconds=10 + c * 12)))
            tool_calls += 1
    # token usage, last 45 days — one deliberate over-budget day at back=17
    for back in range(45):
        ts_day = now - timedelta(days=back)
        spike = (back == 17)
        rows = [("routing_classification", "free", "glm-4.7-flash",
                 rng.randint(280, 380), rng.randint(6, 12), 0.00004)
                for _ in range(rng.randint(4, 8))]
        rows += [("chat", "free" if rng.random() < 0.7 else "powerful",
                  "glm-4.7-flash" if rng.random() < 0.7 else "glm-5.2",
                  rng.randint(700, 1500), rng.randint(300, 700), 0.0009)
                 for _ in range(rng.randint(2, 6) + (4 if spike else 0))]
        if rng.random() < 0.5 or spike:
            rows.append(("voice_extraction", "free", "glm-4.7-flash",
                         rng.randint(180, 320), rng.randint(90, 200), 0.00025))
        rows.append(("embedding", "free", "text-embedding-3-small",
                     rng.randint(8000, 11000), 0, 0.0011))
        if back % 7 == 1:
            rows.append(("report", "powerful", "glm-5.2",
                         rng.randint(11000, 14000), rng.randint(1800, 2600), 0.055))
        if back in (30, 60) or (back == 17):
            rows.append(("report", "powerful", "glm-5.2",
                         rng.randint(12000, 16000), rng.randint(2200, 3200), 0.11))
        for ct, tier, model, t_in, t_out, cost in rows:
            session.add(TokenUsage(
                user_id=user_id, call_type=ct, tier=tier, model=model,
                tokens_in=t_in, tokens_out=t_out, cached_tokens=0,
                cost_estimate_usd=D(cost * rng.uniform(0.85, 1.15)),
                created_at=ts_day - timedelta(minutes=rng.randint(0, 700))))
    session.add(Alert(
        user_id=user_id, type="budget_warning", severity="info",
        triggered_at=now - timedelta(days=17), acknowledged=True,
        message="Daily AI spend reached $0.27 — above the $0.25 budget."))
    session.add(Alert(
        user_id=user_id, type="sync_failure", severity="critical",
        triggered_at=now - timedelta(days=40), acknowledged=True,
        message="Garmin sync failed 3 times in a row — credentials refreshed."))
    session.add(Alert(
        user_id=user_id, type="gear_service_due", severity="warning",
        triggered_at=now - timedelta(days=2), acknowledged=False,
        message="Road Bike: 2150 km since last service (interval 800 km)."))
    # ai_reports
    for back in range(14):
        day = date.today() - timedelta(days=back)
        session.add(AiReport(
            user_id=user_id, report_type="daily", period_start=day, period_end=day,
            generated_at=datetime(day.year, day.month, day.day, 18, 45, tzinfo=UTC),
            content_md=f"**Daily summary {day}** — readiness {rng.randint(58, 92)}, "
                       f"sleep {rng.uniform(6.5, 8.4):.1f}h, "
                       f"{rng.choice(['easy run', 'rest', 'ride', 'strength'])}.",
            model_used=None, source_feature_ids=None))
    for w in range(6):
        ws = date.today() - timedelta(days=7 * w + date.today().weekday())
        session.add(AiReport(
            user_id=user_id, report_type="weekly", period_start=ws,
            period_end=ws + timedelta(days=6),
            generated_at=datetime(ws.year, ws.month, ws.day, 6, 0, tzinfo=UTC)
            + timedelta(days=7),
            content_md=f"**Week {ws}** — {rng.randint(4, 7)} sessions, "
                       f"{rng.uniform(4.5, 9.5):.1f}h total, ACWR {rng.uniform(0.8, 1.3):.2f}.",
            model_used="glm-5.2", source_feature_ids=None))
    for m in (1, 2):
        ms = (date.today().replace(day=1) - timedelta(days=30 * m)).replace(day=1)
        session.add(AiReport(
            user_id=user_id, report_type="monthly", period_start=ms,
            period_end=ms + timedelta(days=27),
            generated_at=datetime(ms.year, ms.month, ms.day, 6, 0, tzinfo=UTC)
            + timedelta(days=30),
            content_md=f"**Monthly {ms:%B}** — fitness up, ferritin recovering, "
                       f"{rng.randint(16, 24)} sessions.",
            model_used="glm-5.2", source_feature_ids=None))
    # embeddings over journal + reports + panels (random vectors — demo only)
    vec_src = [("journal_entries", e.id, (e.free_text_notes or "")[:180])
               for e in journal_entries if e.free_text_notes][:80]
    await session.flush()
    reports = (await session.execute(select(AiReport))).scalars().all()
    vec_src += [("ai_reports", r.id, r.content_md[:180]) for r in reports[:8]]
    panels = (await session.execute(select(LabPanel))).scalars().all()
    vec_src += [("lab_panels", p.id, f"blood panel {p.date} ferritin {p.ferritin_ng_ml}")
                for p in panels[:5]]
    for tbl, sid, snip in vec_src:
        v = [round(rng.uniform(-0.02, 0.02), 4) for _ in range(1536)]
        await session.execute(text(
            "INSERT INTO embeddings (source_table, source_id, embedding, "
            "content_snippet, created_at) VALUES (:t, :i, CAST(:v AS vector), :s, :ts)"),
            {"t": tbl, "i": sid, "v": str(v), "s": snip,
             "ts": now - timedelta(days=rng.randint(0, 60))})
    return tool_calls


async def seed_system(session, user_id: int, rng: random.Random,
                      series: dict):
    now = datetime.now(UTC)
    # forecast cache — home coords, past 3 + next 7 days
    for off in range(-3, 8):
        day = date.today() + timedelta(days=off)
        payload = {
            "temperature_2m_max": D(rng.uniform(17, 33)),
            "temperature_2m_min": D(rng.uniform(9, 19)),
            "temperature_2m_mean": D(rng.uniform(14, 26)),
            "precipitation_sum": D(rng.uniform(0, 14)),
            "wind_speed_10m_max": D(rng.uniform(4, 38)),
            "weather_code": rng.choice([0, 1, 2, 3, 45, 61, 63, 80, 95]),
            "hourly": [{"time": f"{day}T{h:02d}:00", "temperature_2m": D(rng.uniform(14, 30)),
                        "precipitation": D(rng.uniform(0, 2)),
                        "weather_code": rng.choice([0, 1, 2, 3])} for h in (6, 9, 12, 15, 18, 21)],
        }
        session.add(ForecastCache(lat=41.9028, lon=12.4964, date=day,
                                  fetched_at=now - timedelta(hours=off * 6 + 1),
                                  payload=payload))
    # raw ingest — last 14 days from garmin + a technogym batch
    for back in range(14):
        day = date.today() - timedelta(days=back)
        for ptype in ("daily_stats", "sleep", "hrv"):
            session.add(RawIngest(
                user_id=user_id, source="garmin", payload_type=ptype,
                fetched_at=datetime(day.year, day.month, day.day, 6, 10, tzinfo=UTC),
                raw_json={"demo": ptype, "date": str(day)}, processed=True))
    session.add(RawIngest(user_id=user_id, source="technogym",
                          payload_type="workouts", fetched_at=now - timedelta(hours=9),
                          raw_json={"count": 2}, processed=True))
    # sync logs (raw SQL — no ORM models for these tables)
    for back in range(14):
        day = date.today() - timedelta(days=back)
        await session.execute(text(
            "INSERT INTO watch_sync_log (user_id, device_id, sync_type, synced_at, payload_summary) "
            "VALUES (:u, 'fenix-7-demo', 'full', :t, :p)"),
            {"u": user_id,
             "t": datetime(day.year, day.month, day.day, 6, 12, tzinfo=UTC),
             "p": json.dumps({"activities": rng.randint(0, 2), "ok": True})})
    for back in (0, 2, 5, 8, 12):
        await session.execute(text(
            "INSERT INTO technogym_sync_log (user_id, training_plan_id, sync_direction, "
            "status, synced_at, external_program_id, raw_response) "
            "VALUES (:u, NULL, 'pull', 'ok', :t, 'tg-prog-4412', :p)"),
            {"u": user_id, "t": now - timedelta(days=back, hours=3),
             "p": json.dumps({"workouts": rng.randint(1, 3)})})
    # invites (raw SQL)
    await session.execute(text(
        "INSERT INTO invites (code, created_by, used_by, expires_at, created_at) VALUES "
        "('APEX-DEMO-1', :u, NULL, :e1, :c1), ('APEX-USED-9', :u, NULL, :e2, :c2)"),
        {"u": user_id, "e1": now + timedelta(days=30), "c1": now - timedelta(days=10),
         "e2": now - timedelta(days=5), "c2": now - timedelta(days=100)})
    # weekly / monthly rollups from the real generated series
    weights = series["weights"]
    hrvs = series["hrvs"]
    for w in range(1, 9):
        ws = date.today() - timedelta(days=7 * w + date.today().weekday())
        chunk_w = weights[-(7 * w) - 1:len(weights) - 7 * (w - 1) - 1] or [77.0]
        chunk_h = hrvs[-(7 * w) - 1:len(hrvs) - 7 * (w - 1) - 1] or [60.0]
        if not chunk_w:
            continue
        await session.execute(text(
            "INSERT INTO weekly_rollups (user_id, week_start, metric_name, mean_value, "
            "min_value, max_value, trend_slope) VALUES (:u, :d, 'weight_kg', :mw, :nw, :xw, 0), "
            "(:u, :d, 'hrv_ms', :mh, :nh, :xh, 0)"),
            {"u": user_id, "d": ws,
             "mw": D(sum(chunk_w) / len(chunk_w)), "nw": D(min(chunk_w)), "xw": D(max(chunk_w)),
             "mh": D(sum(chunk_h) / len(chunk_h)), "nh": D(min(chunk_h)), "xh": D(max(chunk_h))})


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=180)
    args = ap.parse_args()
    rng = random.Random(42)
    days = args.days
    async with sessionmaker() as session:
        await wipe(session)
        user = await seed_owner(session)
        uid = user.id
        await seed_gear(session, uid)
        acts, loads, discs = await seed_activities(session, uid, days, rng)
        # segments (raw SQL — no ORM)
        await session.execute(text(
            "INSERT INTO segments (discipline_id, name, geo_polyline) VALUES "
            "(:d, 'Riverside 5K', 'poly-demo-1'), (:d2, 'Villa Climb', 'poly-demo-2')"),
            {"d": discs["running"].id, "d2": discs["road_cycling"].id})
        seg_ids = (await session.execute(text("SELECT id FROM segments ORDER BY id")))
        seg_ids = [r[0] for r in seg_ids]
        outdoor = [(a, d) for a, d, _ in acts if d.name in ("running", "road_cycling")]
        for i, (act, disc) in enumerate(rng.sample(outdoor, min(24, len(outdoor)))):
            seg = seg_ids[0] if disc.name == "running" else seg_ids[1]
            await session.execute(text(
                "INSERT INTO segment_efforts (segment_id, activity_id, elapsed_time_s, "
                "rank, is_pr) VALUES (:s, :a, :t, :r, :pr)"),
                {"s": seg, "a": act.id, "t": rng.randint(760, 1420),
                 "r": rng.randint(1, 40), "pr": rng.random() < 0.12})
        series = await seed_wellness(session, uid, days, rng, loads)
        await seed_nutrition(session, uid, days, rng)
        entries = await seed_journal(session, uid, days, rng)
        await seed_labs(session, uid, rng)
        await seed_plans(session, uid, discs, rng)
        await seed_ai(session, uid, days, rng, entries)
        # pass series into rollups
        bios = (await session.execute(
            select(DailyBiometric).where(DailyBiometric.user_id == uid)
            .order_by(DailyBiometric.date))).scalars().all()
        hrvs = (await session.execute(
            select(HrvReading).where(HrvReading.user_id == uid)
            .order_by(HrvReading.timestamp))).scalars().all()
        series["weights"] = [float(b.weight_kg or 77) for b in bios]
        series["hrvs"] = [float(h.hrv_ms) for h in hrvs]
        await seed_system(session, uid, rng, series)
        await session.commit()
    counts = {
        "activities": len(acts), "journal": len(entries),
        "days": days,
    }
    print("demo dataset seeded:", counts)
    print("owner login: owner@apexhealth.dev / demo-owner-1234")
    print("story notes: low ferritin alert 90d ago; bike overdue for service; "
          "AI budget crossed 17d ago; sync_failure escalation history in alerts; "
          "cycling plan draft awaiting confirmation")


if __name__ == "__main__":
    asyncio.run(main())
