"""Deterministic in-app notifications. No automatic external channel delivery."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import select
from app.models.lab import AthleteEntry, LabNotification
from app.services.evidence import coverage, scope_lock


def notification_dict(row, locale="en"):
    from app.services.lab_language import translate_notification

    return {
        "id": row.id,
        "category": row.category,
        "severity": row.severity,
        "state": row.state,
        "payload": translate_notification(row.payload, locale),
        "created_at": row.created_at.isoformat(),
        "expires_at": row.expires_at.isoformat(),
        "snoozed_until": row.snoozed_until.isoformat() if row.snoozed_until else None,
    }


async def refresh_notifications(session, user, *, now=None):
    now = now or datetime.now(UTC)
    await scope_lock(session, user.id, "notifications")
    cover = await coverage(session, user, now=now)
    pref = await session.scalar(
        select(AthleteEntry)
        .where(
            AthleteEntry.user_id == user.id,
            AthleteEntry.kind == "notification_preferences",
        )
        .order_by(AthleteEntry.id.desc())
        .limit(1)
    )
    prefs = (
        pref.payload
        if pref
        else {
            "daily_cap": 5,
            "muted_classes": [],
            "quiet_start_hour": 22,
            "quiet_end_hour": 7,
        }
    )
    rules = {}
    for item in cover["integrations"]:
        if item["consecutive_failures"] >= 2 or item["status"] != "active":
            key = "sync:" + item["provider"]
            rules[key] = (
                "sync",
                "action",
                {
                    "title": f"{item['provider'].title()} needs attention",
                    "why": "Sync or authorization failed; current evidence may be incomplete.",
                    "evidence": item,
                    "action": "Reconnect the provider or run a scoped repair.",
                    "href": "/app/data-health",
                },
            )
    gaps = [
        m
        for m in cover["metrics"]
        if m["metric"] in ("hrv_overnight_rmssd", "resting_hr", "sleep_duration")
        and (m["availability"] != "available" or m["sample_days_7d"] < 4)
    ]
    if gaps:
        rules["coverage:core"] = (
            "data_quality",
            "watch",
            {
                "title": "Today's evidence is incomplete",
                "why": "The training decision is limited by missing or old measurements.",
                "evidence": [
                    {
                        "metric": g["metric"],
                        "availability": g["availability"],
                        "latest_measurement": g["latest"]["measured_at"]
                        if g["latest"]
                        else None,
                    }
                    for g in gaps
                ],
                "action": "Review data coverage or record a check-in.",
                "href": "/app/data-health",
            },
        )
    # Require the same two abnormalities on three consecutive measured days.
    # This is a conservative planning notification, never a diagnosis.
    from app.services.analytics import baseline
    from app.services.evidence import query_observations

    local_today = now.astimezone(ZoneInfo(user.timezone)).date()
    eligible_cover = await coverage(session, user, now=now, for_ai=True)
    selected = {
        m["metric"]: m["latest"]
        for m in eligible_cover["metrics"]
        if m["metric"] in ("hrv_overnight_rmssd", "resting_hr")
    }
    paired = {}
    try:
        for metric in ("hrv_overnight_rmssd", "resting_hr"):
            origin = selected[metric]["origin"] if selected[metric] else "garmin"
            ref = await baseline(
                session,
                user,
                metric,
                local_today - timedelta(days=31),
                local_today - timedelta(days=4),
                origin=origin,
                for_ai=True,
            )
            samples = await query_observations(
                session,
                user.id,
                metric,
                local_today - timedelta(days=2),
                local_today,
                origin=origin,
                for_ai=True,
            )
            by_day = {
                r.local_date: r
                for r in samples
                if isinstance(r.value.get("value"), (float, int))
            }
            paired[metric] = (ref, by_day)
        hrv, hr = paired["hrv_overnight_rmssd"], paired["resting_hr"]
        if (
            hrv[0]["state"] == "available"
            and hr[0]["state"] == "available"
            and all(
                day in hrv[1]
                and day in hr[1]
                and hrv[1][day].value["value"] < 0.8 * hrv[0]["median"]
                and hr[1][day].value["value"] >= hr[0]["median"] + 5
                for day in (local_today - timedelta(days=i) for i in range(3))
            )
        ):
            rules["training:confirmed_multi_signal"] = (
                "training",
                "action",
                {
                    "title": "A persistent change deserves a plan review",
                    "why": "Three recorded days show lower HRV and higher resting HR relative to comparable personal baselines.",
                    "evidence": [
                        f"observation:{r.id}:{r.revision}"
                        for _, days in paired.values()
                        for r in days.values()
                    ],
                    "action": "Review the conservative decision and record any symptoms.",
                    "href": "/app",
                },
            )
    except ValueError:
        pass  # Mixed sources or too little data cannot justify this notification.
    from app.services.analytics import constraints

    ctx = await constraints(
        session, user, now.astimezone(ZoneInfo(user.timezone)).date()
    )
    for event in ctx["events"]:
        if event["priority"] == 1 and event["days_away"] <= event["taper_days"]:
            rules[f"event:{event['id']}"] = (
                "event",
                "action",
                {
                    "title": "Priority event is approaching",
                    "why": "Review the configured taper and preserve the session focus.",
                    "evidence": event,
                    "action": "Review today's decision and planned sessions.",
                    "href": "/app/calendar",
                },
            )
    from app.queries.snapshot import gear_overview

    for gear in await gear_overview(session, user.id):
        if gear.get("active") and (gear.get("usage_pct") or 0) >= 100:
            rules[f"gear:{gear['gear_id']}"] = (
                "gear",
                "watch",
                {
                    "title": "Equipment service is due",
                    "why": "Recorded usage reached the configured service interval.",
                    "evidence": gear,
                    "action": "Inspect equipment and record completed service.",
                    "href": "/app/gear",
                },
            )
    existing = (
        await session.scalars(
            select(LabNotification).where(LabNotification.user_id == user.id)
        )
    ).all()
    by_key = {r.dedupe_key: r for r in existing}
    local_day = now.astimezone(ZoneInfo(user.timezone)).date()
    count_today = sum(
        datetime.fromisoformat(
            r.payload.get("_last_triggered_at", r.created_at.isoformat())
        )
        .astimezone(ZoneInfo(user.timezone))
        .date()
        == local_day
        for r in existing
    )
    for key, (category, severity, payload) in rules.items():
        if category in prefs["muted_classes"]:
            continue
        row = by_key.get(key)
        if row is None:
            if count_today >= prefs["daily_cap"]:
                continue
            row = LabNotification(
                user_id=user.id,
                dedupe_key=key,
                category=category,
                severity=severity,
                payload={**payload, "_last_triggered_at": now.isoformat()},
                state="created",
                expires_at=now + timedelta(days=7),
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            count_today += 1
        elif row.state in ("resolved", "expired") and now - row.updated_at >= timedelta(
            hours=24
        ):
            # A resolved continuing condition does not immediately reopen.
            # Require a changed condition before reopening the same alert.
            if count_today < prefs["daily_cap"] and row.payload.get(
                "evidence"
            ) != payload.get("evidence"):
                count_today += 1
                row.state = "created"
                row.payload = {**payload, "_last_triggered_at": now.isoformat()}
                row.updated_at = now
                row.expires_at = now + timedelta(days=7)
        elif row.state in ("created", "read", "snoozed"):
            row.payload = {
                **payload,
                "_last_triggered_at": row.payload.get(
                    "_last_triggered_at", row.created_at.isoformat()
                ),
            }
            if (
                row.state == "snoozed"
                and row.snoozed_until
                and row.snoozed_until <= now
            ):
                row.state = "created"
                row.snoozed_until = None
    for row in existing:
        if row.dedupe_key not in rules and row.state not in ("resolved", "expired"):
            row.state = "resolved"
            row.updated_at = now
        elif row.expires_at <= now and row.state != "resolved":
            row.state = "expired"
    await session.flush()
    hour = now.astimezone(ZoneInfo(user.timezone)).hour
    a, b = prefs["quiet_start_hour"], prefs["quiet_end_hour"]
    quiet = (a <= hour < b) if a < b else (hour >= a or hour < b) if a != b else False
    return {"quiet_hours_active": quiet, "preferences": prefs}
