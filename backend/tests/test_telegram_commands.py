"""Bot command tests (§10.3): /status, /donate, /report, /gear read through
the shared query layer (§8.2) with seeded §6.4 data. lab_panels/gear are
seeded with raw SQL — their models are mapped in Phase 4."""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select, text

from app.connectors.telegram.handlers import handle_update
from app.models.features import DailyFeature
from app.models.integration import Integration
from app.models.telegram import TelegramLink
from app.models.user import AuthCredential
from tests.helpers.telegram import (
    FixtureTelegramClient,
    bot_context,
    clean_bot_tables,  # noqa: F401 — autouse per-test truncate
    load_update,
    sent_texts,
    with_text,
)

CHAT = 42


async def _link_chat(ctx, chat_id: int) -> int:
    async with ctx.sessionmaker() as session:
        owner = (
            await session.scalars(
                select(AuthCredential.user_id).where(AuthCredential.role == "owner")
            )
        ).first()
        session.add(TelegramLink(user_id=owner, chat_id=chat_id))
        await session.commit()
    return owner


async def _seed_feature_data(ctx, owner: int) -> date:
    """Yesterday (owner-local) with a full daily feature row + activity + sleep."""
    day = date(2025, 3, 9)
    async with ctx.sessionmaker() as session:
        session.add(
            DailyFeature(
                user_id=owner,
                date=day,
                recovery_score=78.0,
                strain_score=12.4,
                readiness_score=71.0,
                training_load_acute=812.0,
                training_load_chronic=670.0,
                acwr=1.21,
                sleep_architecture_score=66.0,
                hrv_deviation_from_baseline=3.1,
                iron_status_flag=None,
                data_completeness="full",
            )
        )
        session.add(
            Integration(user_id=owner, provider="garmin", status="active",
                        last_synced_at=datetime(2025, 3, 10, 6, 0, tzinfo=UTC))
        )
        await session.commit()
    return day


async def test_status_with_data():
    client = FixtureTelegramClient()
    async with bot_context(client) as ctx:
        owner = await _link_chat(ctx, CHAT)
        await _seed_feature_data(ctx, owner)
        await handle_update(ctx, load_update("text_status"))
    out = sent_texts(client)[0]
    assert "Recovery 78" in out and "Readiness 71" in out
    assert "ACWR 1.21" in out
    assert "- garmin: active, last sync 2025-03-10 06:00Z" in out
    assert "Open alerts: 0" in out


async def test_status_without_any_data_is_honest():
    client = FixtureTelegramClient()
    async with bot_context(client) as ctx:
        await _link_chat(ctx, CHAT)
        await handle_update(ctx, load_update("text_status"))
    out = sent_texts(client)[0]
    assert "No daily metrics yet" in out
    assert "No integrations connected yet." in out


async def test_report_templated_summary():
    client = FixtureTelegramClient()
    async with bot_context(client) as ctx:
        owner = await _link_chat(ctx, CHAT)
        day = await _seed_feature_data(ctx, owner)
        async with ctx.sessionmaker() as session:
            from app.models.activity import Activity, Discipline
            from app.models.wellness import SleepSession

            discipline = (
                await session.scalars(select(Discipline).where(Discipline.name == "road_cycling"))
            ).one()
            session.add(
                Activity(
                    user_id=owner,
                    discipline_id=discipline.id,
                    start_time=datetime(2025, 3, 9, 9, 0, tzinfo=UTC),
                    start_tz_offset_minutes=60,
                    local_date=day,
                    duration_s=7440,
                    distance_m=41200,
                )
            )
            session.add(
                SleepSession(
                    user_id=owner,
                    local_date=day,
                    start_time=datetime(2025, 3, 8, 23, 10, tzinfo=UTC),
                    end_time=datetime(2025, 3, 9, 7, 25, tzinfo=UTC),
                    total_sleep_s=26100,
                    sleep_score=84.0,
                )
            )
            await session.commit()
        await handle_update(ctx, load_update("text_report"))
    out = sent_texts(client)[0]
    assert f"Daily report — {day}" in out
    assert "Readiness 71" in out
    assert "ACWR 1.21 (acute 812 · chronic 670)" in out
    assert "Sleep 7h15 · score 84" in out
    assert "road_cycling 2h04 (41.2 km)" in out


async def test_report_without_data():
    client = FixtureTelegramClient()
    async with bot_context(client) as ctx:
        await _link_chat(ctx, CHAT)
        await handle_update(ctx, load_update("text_report"))
    assert "No daily metrics yet" in sent_texts(client)[0]


async def test_donate_with_history():
    client = FixtureTelegramClient()
    async with bot_context(client) as ctx:
        owner = await _link_chat(ctx, CHAT)
        await _seed_feature_data(ctx, owner)
        async with ctx.sessionmaker() as session:
            await session.execute(
                text(
                    "INSERT INTO lab_panels (user_id, date, panel_type, donation_type, "
                    "next_eligible_date) VALUES (:uid, :d, 'blood_count', 'whole_blood', :next)"
                ),
                {
                    "uid": owner,
                    "d": date(2025, 3, 1),
                    "next": datetime.now(UTC).date() + timedelta(days=60),
                },
            )
            await session.commit()
        await handle_update(ctx, load_update("text_donate"))
    out = sent_texts(client)[0]
    assert "Last whole_blood: 2025-03-01" in out
    assert "Next eligible:" in out and "— in" in out
    assert "Iron flag: none yet" in out


async def test_donate_without_history():
    client = FixtureTelegramClient()
    async with bot_context(client) as ctx:
        await _link_chat(ctx, CHAT)
        await handle_update(ctx, load_update("text_donate"))
    assert "No donations recorded yet" in sent_texts(client)[0]


async def test_gear_usage_and_overdue():
    client = FixtureTelegramClient()
    async with bot_context(client) as ctx:
        owner = await _link_chat(ctx, CHAT)
        async with ctx.sessionmaker() as session:
            await session.execute(
                text(
                    "INSERT INTO gear (user_id, name, gear_type, km_since_service, "
                    "service_interval_km, hours_since_service) VALUES "
                    "(:uid, 'Road bike', 'bike', 1900, 2000, 12), "
                    "(:uid, 'Chainring bolt kit', 'parts', 0, 0, 410)"
                ),
                {"uid": owner},
            )
            # 410 h against a 400 h interval — due
            await session.execute(
                text("UPDATE gear SET service_interval_hours = 400 WHERE name = 'Chainring bolt kit'")
            )
            await session.commit()
        await handle_update(ctx, load_update("text_gear"))
    out = sent_texts(client)[0]
    assert "- Road bike (bike): 1900/2000 km (95%)" in out
    # no km interval configured → km part omitted entirely
    assert "- Chainring bolt kit (parts): 410/400 h (102%) ⚠️ service due" in out


async def test_gear_empty():
    client = FixtureTelegramClient()
    async with bot_context(client) as ctx:
        await _link_chat(ctx, CHAT)
        await handle_update(ctx, load_update("text_gear"))
    assert "No gear tracked yet" in sent_texts(client)[0]


# --------------------------------------------------- /forecast (§14, Phase 7)


def _cached_day(day) -> dict:
    return {
        "source": "open-meteo",
        "time": day.isoformat(),
        "daily": {
            "temperature_2m_max": 16.1,
            "temperature_2m_min": 7.1,
            "temperature_2m_mean": 11.2,
            "precipitation_sum": 0.4,
            "precipitation_probability_max": 35,
            "wind_speed_10m_max": 18.6,
            "weather_code": 2.0,
        },
    }


async def _seed_forecast_cache(ctx, owner: int, days: int = 3) -> None:
    from decimal import Decimal

    from app.models.weather import ForecastCache

    async with ctx.sessionmaker() as session:
        for offset in range(days):
            day = date.today() + timedelta(days=offset)
            session.add(
                ForecastCache(
                    lat=Decimal("45.075"),
                    lon=Decimal("9.725"),
                    date=day,
                    payload=_cached_day(day),
                    fetched_at=datetime.now(UTC),
                )
            )
        await session.commit()


def _with_home_configured(monkeypatch) -> None:
    from types import SimpleNamespace

    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: SimpleNamespace(weather_home_lat=45.075, weather_home_lon=9.725),
    )


async def test_forecast_renders_cached_days(monkeypatch):
    client = FixtureTelegramClient()
    async with bot_context(client) as ctx:
        owner = await _link_chat(ctx, CHAT)
        await _seed_forecast_cache(ctx, owner)
        _with_home_configured(monkeypatch)
        await handle_update(ctx, with_text(load_update("text_status"), "/forecast"))
    out = sent_texts(client)[0]
    assert out.startswith("Forecast (45.08, 9.72) — Europe/Rome")
    assert "- " in out and "Partly cloudy" in out
    assert "7.1–16.1°C" in out
    assert "0.4mm, 35%" in out
    assert "wind 18.6km/h" in out


async def test_forecast_days_argument_limits_rows(monkeypatch):
    client = FixtureTelegramClient()
    async with bot_context(client) as ctx:
        owner = await _link_chat(ctx, CHAT)
        await _seed_forecast_cache(ctx, owner, days=5)
        _with_home_configured(monkeypatch)
        await handle_update(
            ctx, with_text(load_update("text_status"), "/forecast 2")
        )
    out = sent_texts(client)[0]
    assert out.count("\n- ") == 2


async def test_forecast_without_configuration_is_honest(monkeypatch):
    from types import SimpleNamespace

    client = FixtureTelegramClient()
    async with bot_context(client) as ctx:
        owner = await _link_chat(ctx, CHAT)
        monkeypatch.setattr(
            "app.core.config.get_settings",
            lambda: SimpleNamespace(weather_home_lat=0.0, weather_home_lon=0.0),
        )
        await handle_update(ctx, with_text(load_update("text_status"), "/forecast"))
    out = sent_texts(client)[0]
    assert "not configured" in out


async def test_forecast_with_empty_cache_tells_the_truth(monkeypatch):
    client = FixtureTelegramClient()
    async with bot_context(client) as ctx:
        owner = await _link_chat(ctx, CHAT)
        _with_home_configured(monkeypatch)
        await handle_update(ctx, with_text(load_update("text_status"), "/forecast"))
    out = sent_texts(client)[0]
    assert "No forecast cached yet" in out
