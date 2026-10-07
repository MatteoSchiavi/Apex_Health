"""Internal utility telemetry: fixed vocabulary, whitelisted minimal metadata."""
from app.models.alpha import AlphaEvent

EVENTS = frozenset({
    'integration_connected', 'integration_sync_success', 'integration_sync_failure',
    'overview_viewed', 'metric_explanation_opened', 'agent_question_asked',
    'agent_answer_completed', 'agent_answer_failed', 'analysis_started',
    'analysis_completed', 'change_proposed', 'change_accepted', 'change_edited',
    'change_rejected', 'decision_feedback_submitted', 'experiment_created',
    'experiment_completed',
})
_IDS = {'decision_id', 'draft_id', 'session_id', 'experiment_id', 'job_id'}
_PROVIDERS = {'garmin', 'whoop', 'oura', 'coros', 'strava', 'technogym', 'fitbit', 'apple_healthkit', 'apple_health'}
_ERRORS = {'authentication', 'permission', 'transport', 'normalization', 'timeout', 'unknown'}


def record_event(session, user_id: int, event: str, metadata: dict | None = None):
    if event not in EVENTS:
        raise ValueError('Unknown alpha event')
    clean = {}
    for key, value in (metadata or {}).items():
        if key in _IDS and isinstance(value, int) and not isinstance(value, bool) and value > 0:
            clean[key] = value
        elif key == 'provider' and isinstance(value, str) and value in _PROVIDERS:
            clean[key] = value
        elif key == 'error_class' and isinstance(value, str) and value in _ERRORS:
            clean[key] = value
        elif key == 'metric' and isinstance(value, str):
            from app.metrics.registry import METRIC_REGISTRY
            if value in METRIC_REGISTRY:
                clean[key] = value
    row = AlphaEvent(user_id=user_id, event=event, metadata_json=clean)
    session.add(row)
    return row
