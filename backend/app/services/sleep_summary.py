"""Read missing Garmin awake totals from recorded epochs without changing source rows."""
from datetime import UTC, datetime
from sqlalchemy import select
from app.models.integration import RawIngest
from app.connectors.garmin.stages import extract_sleep_stage_segments


def awake_seconds(payload, start, end):
    """Union awake intervals, clipped to the actual night; gaps are unknown."""
    intervals = []
    for segment in extract_sleep_stage_segments(payload) or []:
        if segment['stage'] != 'awake':
            continue
        left = datetime.fromisoformat(segment['t_start'])
        right = datetime.fromisoformat(segment['t_end'])
        if left.tzinfo is None:
            left = left.replace(tzinfo=UTC)
        if right.tzinfo is None:
            right = right.replace(tzinfo=UTC)
        left, right = max(start, left), min(end, right)
        if right > left:
            intervals.append((left, right))
    if not intervals:
        return None
    intervals.sort()
    total, left, right = 0, *intervals[0]
    for following_left, following_right in intervals[1:]:
        if following_left <= right:
            right = max(right, following_right)
        else:
            total += (right - left).total_seconds()
            left, right = following_left, following_right
    return round(total + (right - left).total_seconds())


async def recorded_awake_totals(session, nights):
    """One bounded query for exact source starts; never borrow another night's data."""
    starts = {str(round(n.start_time.timestamp() * 1000)): n for n in nights if n.origin == "garmin"}
    if not starts:
        return {}
    rows = (await session.scalars(select(RawIngest).where(
        RawIngest.user_id == nights[0].user_id,
        RawIngest.source == 'garmin', RawIngest.payload_type == 'sleep',
        RawIngest.raw_json['dailySleepDTO', 'sleepStartTimestampGMT'].astext.in_(starts),
    ).order_by(RawIngest.fetched_at.desc(), RawIngest.id.desc()))).all()
    result = {}
    for raw in rows:
        key = str(raw.raw_json['dailySleepDTO']['sleepStartTimestampGMT'])
        if key in result:
            continue
        night = starts[key]
        value = awake_seconds(raw.raw_json, night.start_time, night.end_time)
        if value is not None:
            result[key] = value
    return {starts[key].start_time: value for key, value in result.items()}


def summary_awake(night, recorded=None):
    if night.awake_s is not None and (night.awake_s != 0 or recorded is None):
        return night.awake_s
    if recorded is not None:
        return recorded
    if night.total_sleep_s is not None:
        return max(0, round((night.end_time - night.start_time).total_seconds()) - night.total_sleep_s)
    return None
