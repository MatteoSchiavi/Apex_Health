"""Export-shape regressions; synthetic bytes contain no private recordings."""
import struct
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fitdecode.utils import compute_crc
from sqlalchemy import delete, func, select

from app.models.activity import Activity, ActivitySourceLink, ActivityStream
from app.models.lab import LabDocument
from app.models.user import User
from app.services.evidence import EvidenceError
from app.services.activity_presentation import activity_presentation
from app.services.exercise_catalog import fit_exercises
from app.services.fit_import import import_original, parse_original, session_end
from tests.helpers.domain_db import clean_domain_tables  # noqa: F401


def exported_fit():
    start = datetime(2026, 10, 1, 8, tzinfo=UTC)
    stamp = int((start - datetime(1989, 12, 31, tzinfo=UTC)).total_seconds())

    def message(number, fields, values):
        definition = b"\x40\x00\x00" + struct.pack("<HB", number, len(fields)) + b"".join(bytes(f) for f in fields)
        return definition + b"\x00" + values

    # Summary timestamp repeats start. Timer excludes a ten-minute pause.
    data = message(18, [(2, 4, 0x86), (5, 1, 0), (8, 4, 0x86), (7, 4, 0x86), (253, 4, 0x86)],
                   struct.pack("<IBIII", stamp, 10, 3600000, 4200000, stamp))
    fields = [(3, 2, 0x84), (4, 2, 0x84), (5, 1, 0), (6, 4, 0x86), (7, 6, 0x84), (8, 6, 0x84), (10, 2, 0x84)]

    def active(offset, categories, subtypes, reps=8):
        return message(225, fields, struct.pack("<HHBI7H", reps, 40 * 16, 1, stamp + offset, *categories, *subtypes, 0))

    # Index zero deliberately refers to a conflicting title: step/catalogue
    # indices are unrelated and must never override recorded set identity.
    name = b"Panca piana\x00"
    data += message(264, [(254, 2, 0x84), (2, len(name), 7), (0, 2, 0x84), (1, 2, 0x84)],
                    struct.pack("<H", 0) + name + struct.pack("<HH", 0, 1))
    data += active(60, (0, 24, 65534), (1, 65535, 65535))
    data += active(3900, (28, 28, 28), (28, 28, 28))
    data += active(4000, (65534, 7, 0), (65535, 65535, 65535), reps=4)
    # Missing repetitions describe a timed record, not a guessed rep count.
    data += active(4100, (41, 41, 41), (3, 3, 3), reps=65535)
    for offset in (0, 3900, 4200, 4300):
        data += message(20, [(253, 4, 0x86), (3, 1, 2)], struct.pack("<IB", stamp + offset, 120))
    header = struct.pack("<BBHI4s", 14, 0x10, 2100, len(data), b".FIT")
    content = header + struct.pack("<H", compute_crc(header)) + data
    return content + struct.pack("<H", compute_crc(content))


def test_array_categories_keep_selected_detection_and_match_titles_by_identity():
    exercises = fit_exercises(exported_fit())
    assert [(e["name"], e["muscle_group"]) for e in exercises] == [
        ("Barbell Bench Press", "push"), ("Dumbbell Split Squat", "legs"), ("Unknown exercise", None)
    ]
    assert [e["recorded_sets"] for e in exercises] == [
        [{"reps": 8, "weight_kg": 40}], [{"reps": 8, "weight_kg": 40}], [{"reps": 4, "weight_kg": 40}]
    ]


def test_elapsed_boundary_includes_pause_but_respects_valid_summary_end():
    summary = parse_original(exported_fit())[0][0]
    assert session_end(summary) == summary["start_time"] + timedelta(seconds=4200)
    summary["timestamp"] = summary["start_time"] + timedelta(seconds=4300)
    assert session_end(summary) == summary["timestamp"]
    summary["timestamp"] = summary["start_time"]
    summary.pop("total_elapsed_time")
    assert session_end(summary) == summary["start_time"] + timedelta(seconds=3600)
    summary["total_elapsed_time"] = float("nan")
    with pytest.raises(EvidenceError, match="elapsed boundary"):
        session_end(summary)


async def test_export_import_and_repeat_upload_repair_are_owned_and_idempotent(db_session):
    content = exported_fit()
    owner, foreign = User(name=str(uuid4()), timezone="Europe/Rome"), User(name=str(uuid4()), timezone="UTC")
    db_session.add_all([owner, foreign])
    await db_session.commit()
    imported = await import_original(db_session, owner, "export.fit", content, parse_original(content))
    activity = await db_session.get(Activity, imported["activity_ids"][0])
    view = await activity_presentation(db_session, activity, "strength", [])
    assert sum(e["sets"] for e in view["strength"]) == 3
    assert sum(e["reps"] for e in view["strength"]) == 20
    offsets = (await db_session.scalars(select(ActivityStream.t_offset_s).where(ActivityStream.activity_id == activity.id).order_by(ActivityStream.t_offset_s))).all()
    assert offsets == [0, 3900, 4200]  # excludes the actual out-of-window sample
    # Simulate the old parser's empty projection, then repeat the same upload.
    activity.source_metrics = {"fit": {"exercises": []}}
    await db_session.execute(delete(ActivityStream).where(ActivityStream.activity_id == activity.id, ActivityStream.t_offset_s > 0))
    result = await import_original(db_session, owner, "export.fit", content, parse_original(content))
    assert result["already_imported"] and result["activity_ids"] == [activity.id]
    assert len(activity.source_metrics["fit"]["exercises"]) == 3
    assert await db_session.scalar(select(func.count()).select_from(ActivityStream).where(ActivityStream.activity_id == activity.id)) == 3
    assert await db_session.scalar(select(func.count()).select_from(LabDocument).where(LabDocument.user_id == owner.id)) == 1
    assert await db_session.scalar(select(func.count()).select_from(ActivitySourceLink).where(ActivitySourceLink.user_id == owner.id)) == 1
    other = await import_original(db_session, foreign, "same.fit", content, parse_original(content))
    assert other["activity_ids"] != imported["activity_ids"]
    assert (await db_session.get(Activity, other["activity_ids"][0])).user_id == foreign.id
