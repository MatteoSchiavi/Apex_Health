"""Opt-in private-recording verification, separate from synthetic CI fixtures.

Set APEX_FIT_VERIFICATION_DIR to a directory of original .fit files. No private
recordings or derived health data belong in Git. Uses the disposable test DB.
"""
import io
import json
import os
from collections import Counter
from pathlib import Path
from uuid import uuid4

import fitdecode
import pytest
from sqlalchemy import func, select

from app.api.activities import activity_detail, activity_streams
from app.core.encryption import decrypt_bytes
from app.models.activity import Activity, ActivitySourceLink, ActivityStream
from app.models.lab import LabDocument
from app.models.user import User
from app.services.activity_presentation import activity_presentation
from app.services.fit_import import import_original, parse_original
from tests.helpers.domain_db import clean_domain_tables  # noqa: F401


INPUT_DIR = os.environ.get("APEX_FIT_VERIFICATION_DIR")
FILES = sorted(Path(INPUT_DIR).glob("*.fit")) if INPUT_DIR else []


@pytest.mark.skipif(not INPUT_DIR, reason="private FIT recordings supplied only for opt-in verification")
async def test_original_recordings_preserve_all_recorded_rep_sets_and_samples(db_session):
    assert FILES, "APEX_FIT_VERIFICATION_DIR contains no .fit recordings"
    user = User(name=str(uuid4()), timezone="Europe/Rome")
    db_session.add(user)
    await db_session.commit()
    evidence = []
    for path in FILES:
        content = path.read_bytes()
        raw_sets, raw_records = [], []
        with fitdecode.FitReader(io.BytesIO(content), check_crc=fitdecode.CrcCheck.RAISE) as reader:
            for frame in reader:
                if frame.frame_type == fitdecode.FIT_FRAME_DATA and frame.name in ("set", "record"):
                    row = {field.name: field.value for field in frame.fields}
                    (raw_sets if frame.name == "set" else raw_records).append(row)
        active = [s for s in raw_sets if s.get("set_type") == "active"]
        expected = Counter((s["repetitions"], s.get("weight")) for s in active if s.get("repetitions") is not None)
        result = await import_original(db_session, user, path.name, content, parse_original(content))
        assert len(result["activity_ids"]) == 1
        activity = await db_session.get(Activity, result["activity_ids"][0])
        assert activity.user_id == user.id
        view = await activity_presentation(db_session, activity, "strength", [])
        displayed = Counter((s["reps"], s["weight_kg"]) for e in view["strength"] for s in e["recorded_sets"])
        assert displayed == expected, path.name
        # Independent expectation: every original record timestamp and HR.
        streams = (await db_session.scalars(select(ActivityStream).where(ActivityStream.activity_id == activity.id))).all()
        expected_hr = {round((r["timestamp"] - activity.start_time).total_seconds()): r.get("heart_rate") for r in raw_records}
        assert {s.t_offset_s: s.hr for s in streams} == expected_hr, path.name
        document = await db_session.get(LabDocument, result["original_document_id"])
        assert document.user_id == user.id and decrypt_bytes(document.ciphertext) == content
        repeat = await import_original(db_session, user, path.name, content, parse_original(content))
        assert repeat["already_imported"] and repeat["activity_ids"] == result["activity_ids"]
        detail = await activity_detail(activity.id, user, db_session)
        stream_view = await activity_streams(activity.id, user, db_session, max_points=1200)
        assert detail.presentation.model_dump() == view and stream_view.t[-1] == max(expected_hr)
        evidence.append({"file": path.name, "active_records": len(active), "rest_records": sum(s.get("set_type") == "rest" for s in raw_sets),
                         "sets": sum(displayed.values()), "reps": sum(reps * count for (reps, _), count in displayed.items()),
                         "missing_repetition_records": len(active) - sum(expected.values()), "samples": len(streams),
                         "unidentified_sets": sum(e["sets"] for e in view["strength"] if e["muscle_group"] is None), "presentation": view,
                         "activity": detail.model_dump(mode="json"), "stream_view": stream_view.model_dump(mode="json")})
    assert await db_session.scalar(select(func.count()).select_from(Activity).where(Activity.user_id == user.id)) == len(FILES)
    assert await db_session.scalar(select(func.count()).select_from(ActivitySourceLink).where(ActivitySourceLink.user_id == user.id)) == len(FILES)
    assert await db_session.scalar(select(func.count()).select_from(LabDocument).where(LabDocument.user_id == user.id)) == len(FILES)
    if output := os.environ.get("APEX_FIT_VERIFICATION_OUTPUT"):
        Path(output).write_text(json.dumps(evidence, indent=2))
