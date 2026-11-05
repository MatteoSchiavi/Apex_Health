"""Normalize a durably stored Garmin API original without creating a new activity."""
import base64
import binascii
import hashlib
import io
import zipfile
import zlib
from datetime import UTC
from sqlalchemy import select, func
from app.models.activity import Activity, ActivitySourceLink, ActivityStream

MAX_ARCHIVE_BYTES = 20 * 1024 * 1024
MAX_FIT_BYTES = 20 * 1024 * 1024


def decode_original(payload):
    from app.connectors.garmin.normalize import NormalizationError
    try:
        encoded = payload["content"]
        if not isinstance(encoded, str) or len(encoded) > 4 * ((MAX_ARCHIVE_BYTES + 2) // 3):
            raise ValueError
        content = base64.b64decode(encoded, validate=True)
        if len(content) > MAX_ARCHIVE_BYTES or hashlib.sha256(content).hexdigest() != payload["sha256"]:
            raise ValueError
        if content[8:12] == b".FIT":
            return content
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            entries = archive.infolist()
            fits = [e for e in entries if not e.is_dir() and e.filename.lower().endswith('.fit')]
            if len(entries) > 16 or len(fits) != 1:
                raise ValueError
            fit = fits[0]
            if fit.flag_bits & 1 or fit.file_size > MAX_FIT_BYTES or fit.file_size < 12:
                raise ValueError
            # Read a bounded member in memory; no paths are ever extracted.
            with archive.open(fit) as stream:
                result = stream.read(MAX_FIT_BYTES + 1)
            if len(result) > MAX_FIT_BYTES:
                raise ValueError
            return result
    except (ValueError, KeyError, TypeError, binascii.Error, zipfile.BadZipFile, RuntimeError, NotImplementedError, OSError, EOFError, zlib.error):
        raise NormalizationError("Invalid or unsupported Garmin API original archive; raw data retained") from None


async def normalize_original_archive(session, raw, stats):
    from app.connectors.garmin.normalize import NormalizationError
    from app.services.fit_import import parse_original, project_original
    from app.services.evidence import EvidenceError
    external = raw.payload_type.partition(':')[2]
    if not external.isdigit() or not isinstance(raw.raw_json, dict) or str(raw.raw_json.get('activity_id')) != external:
        raise NormalizationError("Garmin original identity mismatch")
    activity = await session.scalar(select(Activity).join(ActivitySourceLink, ActivitySourceLink.activity_id == Activity.id).where(
        Activity.user_id == raw.user_id, ActivitySourceLink.user_id == raw.user_id,
        ActivitySourceLink.source == 'garmin', ActivitySourceLink.external_id == external))
    if activity is None:
        raise NormalizationError("Garmin original has no owned activity")
    content = decode_original(raw.raw_json)
    try:
        summaries, records, laps = parse_original(content)
        if len(summaries) != 1:
            raise NormalizationError("Multisession original needs explicit session mapping; raw data retained")
        stamp = summaries[0]['start_time']
        stamp = stamp.replace(tzinfo=UTC) if stamp.tzinfo is None else stamp.astimezone(UTC)
        if abs((stamp - activity.start_time).total_seconds()) > 1:
            raise NormalizationError("Original FIT start does not match the selected Garmin activity")
        previous_hash = (activity.source_metrics or {}).get('garmin', {}).get('original_archive_sha256')
        previous_fit = (activity.source_metrics or {}).get('fit')
        sample_changes = await project_original(session, activity, content, summaries[0], records, laps, summaries, 0, fill_missing=True)
        stream_count = await session.scalar(select(func.count()).select_from(ActivityStream).where(ActivityStream.activity_id == activity.id))
        stats.activity_streams_upserted += sample_changes
        from app.services.derived_data import invalidate_calculation_dates
        if previous_hash != raw.raw_json['sha256'] or sample_changes or previous_fit != (activity.source_metrics or {}).get('fit'):
            await invalidate_calculation_dates(session, raw.user_id, {activity.local_date})
        if (activity.source_metrics or {}).get('fit', {}).get('exercises'):
            from app.services.evidence import update_feed
            from datetime import datetime
            await update_feed(session, raw.user_id, 'garmin', 'exercise_sets', 'available', datetime.now(UTC))
        metrics = dict(activity.source_metrics or {})
        metrics['garmin'] = {**metrics.get('garmin', {}), 'original_archive_raw_id': raw.id,
                            'original_archive_sha256': raw.raw_json['sha256'], 'original_archive_checked': True,
                            'streams_state': 'available' if stream_count else 'not_measured'}
        activity.source_metrics = metrics
    except EvidenceError:
        raise NormalizationError("Garmin API original failed FIT validation; raw data retained") from None
