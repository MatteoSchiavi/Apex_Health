"""Medical module acceptance tests (§23 Phase 4).

AC1: a low-ferritin entry fires an alert — DB-backed row + pushed to the
linked chat. Also proves §17's app-layer encryption of lab_panels notes and
the §8.3 shared reads (get_lab_trend, get_donation_status) now running on the
Phase 4 ORM models.

No third-party calls — the Telegram client is the fixture implementation
(§0, §16.7, §20).
"""

import os
from datetime import date

from httpx import AsyncClient
from sqlalchemy import select, text

from app.core.db import sessionmaker
from app.medical.labs import (
    decrypt_notes,
    evaluate_ferritin_alert,
    record_lab_panel,
)
from app.models.alert import Alert
from app.models.medical import LabMetric, LabPanel
from app.models.telegram import TelegramLink
from app.connectors.telegram.alerts import push_alert
from app.queries import get_donation_status, get_lab_trend
from tests.helpers.telegram import (
    FixtureTelegramClient,
    clean_bot_tables,  # noqa: F401 — autouse per-test truncate
)

CSRF = {"X-CSRF-Token": "test"}
OWNER_EMAIL = os.environ["OWNER_EMAIL"]
OWNER_PASSWORD = os.environ["OWNER_PASSWORD"]


async def _owner_id(db_session) -> int:
    row = await db_session.execute(
        text("SELECT id FROM users ORDER BY id LIMIT 1")
    )
    return row.scalar_one()


async def _link_chat(db_session, user_id: int, chat_id: int) -> None:
    db_session.add(TelegramLink(user_id=user_id, chat_id=chat_id))
    await db_session.commit()


async def test_low_ferritin_entry_fires_alert_and_pushes(db_session):
    """AC1: a low-ferritin panel → low_ferritin alert row + Telegram push."""
    client = FixtureTelegramClient()
    user_id = await _owner_id(db_session)
    await _link_chat(db_session, user_id, 555)

    panel = await record_lab_panel(
        db_session,
        user_id=user_id,
        panel_date=date(2025, 5, 2),
        panel_type="post_donation_check",
        donation_type="whole_blood",
        ferritin=12.0,
        reference_ranges={"ferritin": (30.0, 400.0)},
        notes="felt tired for days",
    )
    alert = await evaluate_ferritin_alert(db_session, panel)
    assert alert is not None
    await db_session.commit()

    notified = await push_alert(sessionmaker, client, alert)

    assert notified == 1
    (msg,) = client.sent_messages
    assert msg["chat_id"] == 555
    assert "low_ferritin" in msg["text"]
    assert "12" in msg["text"] and "30" in msg["text"]

    alerts = (
        await db_session.scalars(
            select(Alert).where(Alert.type == "low_ferritin")
        )
    ).all()
    assert len(alerts) == 1
    assert alerts[0].severity == "warning"
    assert alerts[0].acknowledged is False


async def test_low_ferritin_uses_default_threshold_without_lab_range(db_session):
    """No lab-provided ref_low → the configured default (30 ng/mL) applies."""
    user_id = await _owner_id(db_session)
    panel = await record_lab_panel(
        db_session,
        user_id=user_id,
        panel_date=date(2025, 5, 3),
        panel_type="routine",
        ferritin=25.0,
    )
    alert = await evaluate_ferritin_alert(db_session, panel)
    assert alert is not None
    assert "25" in alert.message


async def test_normal_ferritin_never_fires(db_session):
    user_id = await _owner_id(db_session)
    panel = await record_lab_panel(
        db_session,
        user_id=user_id,
        panel_date=date(2025, 5, 4),
        panel_type="routine",
        ferritin=80.0,
        reference_ranges={"ferritin": (30.0, 400.0)},
    )
    assert await evaluate_ferritin_alert(db_session, panel) is None
    panels = (await db_session.scalars(select(Alert))).all()
    assert panels == []


async def test_panel_without_ferritin_never_fires(db_session):
    user_id = await _owner_id(db_session)
    panel = await record_lab_panel(
        db_session,
        user_id=user_id,
        panel_date=date(2025, 5, 5),
        panel_type="routine",
        hemoglobin=14.5,
    )
    assert await evaluate_ferritin_alert(db_session, panel) is None


async def test_notes_are_encrypted_at_rest_and_roundtrip(db_session):
    """§17: the DB column holds ciphertext; only the service decrypts."""
    user_id = await _owner_id(db_session)
    secret = "felt dizzy after donating 450ml"
    panel = await record_lab_panel(
        db_session,
        user_id=user_id,
        panel_date=date(2025, 5, 2),
        panel_type="post_donation",
        ferritin=12.0,
        notes=secret,
    )
    await db_session.commit()
    raw = await db_session.execute(
        text("SELECT notes FROM lab_panels WHERE id = :id"), {"id": panel.id}
    )
    stored = raw.scalar_one()
    assert stored is not None
    assert secret not in stored
    assert "dizzy" not in stored

    fresh = await db_session.get(LabPanel, panel.id)
    assert decrypt_notes(fresh) == secret


async def test_extra_markers_land_in_lab_metrics(db_session):
    user_id = await _owner_id(db_session)
    panel = await record_lab_panel(
        db_session,
        user_id=user_id,
        panel_date=date(2025, 5, 2),
        panel_type="full_blood",
        ferritin=12.0,
        reference_ranges={"ferritin": (30.0, 400.0)},
        extra_markers=[
            {"name": "vitamin_d", "value": 18.0, "unit": "ng/mL",
             "ref_low": 30.0, "ref_high": 100.0},
        ],
    )
    await db_session.commit()
    names = set(
        (
            await db_session.scalars(
                select(LabMetric.metric_name).where(
                    LabMetric.lab_panel_id == panel.id
                )
            )
        ).all()
    )
    assert names == {"ferritin", "vitamin_d"}


async def test_get_lab_trend_reads_uniform_series(db_session):
    user_id = await _owner_id(db_session)
    for day, value in ((3, 40.0), (28, 22.0)):
        await record_lab_panel(
            db_session,
            user_id=user_id,
            panel_date=date(2025, 5, day),
            panel_type="routine",
            ferritin=value,
            reference_ranges={"ferritin": (30.0, 400.0)},
        )
    await db_session.commit()

    series = await get_lab_trend(db_session, user_id, "ferritin")
    assert [s["value"] for s in series] == [40.0, 22.0]
    assert series[0]["ref_low"] == 30.0 and series[0]["ref_high"] == 400.0

    # alias + date-window variants hit the same implementation
    aliased = await get_lab_trend(db_session, user_id, "ferritin_ng_ml")
    assert len(aliased) == 2
    windowed = await get_lab_trend(
        db_session, user_id, "ferritin", start_date=date(2025, 5, 10)
    )
    assert [s["value"] for s in windowed] == [22.0]


async def test_get_donation_status_from_last_panel(db_session):
    user_id = await _owner_id(db_session)
    await record_lab_panel(
        db_session,
        user_id=user_id,
        panel_date=date(2025, 4, 10),
        panel_type="donation",
        donation_type="whole_blood",
        ferritin=45.0,
        next_eligible_date=date(2025, 7, 3),
    )
    await db_session.commit()
    status = await get_donation_status(db_session, user_id, date(2025, 5, 10))
    assert status is not None
    assert status["donation_type"] == "whole_blood"
    assert status["days_since"] == 30
    assert status["next_eligible_date"] == date(2025, 7, 3)
    assert await get_donation_status(db_session, user_id + 1000, date(2025, 5, 10)) is None


async def test_labs_api_endpoints(client: AsyncClient, db_session):
    """§18 /labs: session-protected, CSRF-gated POST, decrypted read-back."""
    resp = await client.get("/labs")
    assert resp.status_code == 401  # §17: no route without a session

    login = await client.post(
        "/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD},
        headers=CSRF,
    )
    assert login.status_code == 200

    resp = await client.post(
        "/labs",
        json={
            "panel_date": "2025-05-02",
            "panel_type": "post_donation_check",
            "donation_type": "whole_blood",
            "ferritin": 12.0,
            "notes": "private note",
            "reference_ranges": {"ferritin": [30.0, 400.0]},
        },
        headers=CSRF,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["ferritin"] == 12.0
    assert body["notes"] == "private note"  # decrypted read-back

    # the alert fired server-side even with no bot token configured (row first)
    alert = (
        await db_session.scalars(select(Alert).where(Alert.type == "low_ferritin"))
    ).first()
    assert alert is not None

    listed = await client.get("/labs")
    assert [p["id"] for p in listed.json()] == [body["id"]]
    fetched = await client.get(f"/labs/{body['id']}")
    assert fetched.json()["panel_type"] == "post_donation_check"
