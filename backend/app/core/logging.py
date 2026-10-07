"""Structured JSON logging to stdout (MASTER_SPEC §21)."""

import logging
import sys

from pythonjsonlogger.json import JsonFormatter

_LOGFIELD_WHITELIST = [
    "levelname",
    "name",
    "message",
    "asctime",
]


def configure_logging() -> None:
    """Route all relevant loggers through a single JSON handler on stdout."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(_LOGFIELD_WHITELIST))

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    install_operational_buffer()

    # uvicorn installs its own handlers/config after import; make everything
    # propagate to the root JSON handler instead of formatting separately.
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(logger_name)
        logger.handlers = []
        logger.propagate = True


class OperationalBufferHandler(logging.Handler):
    """Bounded shared API/worker buffer; arbitrary text and tracebacks excluded.

    Event names are generated from severity. No record args, message, extras,
    exceptions, URLs, user IDs, health payloads or request headers are copied.
    """
    def __init__(self):
        super().__init__(logging.INFO)
        from redis import Redis
        from app.core.config import get_settings
        self.redis = Redis.from_url(get_settings().redis_url, socket_connect_timeout=0.15, socket_timeout=0.15)

    def emit(self, record):
        import json
        import uuid
        import re
        from datetime import UTC, datetime
        try:
            # HTTPX names are safe but its stdout message contains bot URLs;
            # exclude HTTP libraries entirely from operational logging.
            if record.name.startswith(('httpx','httpcore')):
                return
            source = record.name if re.fullmatch(r'[a-zA-Z0-9_.-]{1,80}',record.name) else 'application'
            explicit=getattr(record,'event_code',None)
            allowed={'task_failed','request_failed','connector_failed','startup_completed','maintenance_completed'}
            if explicit in allowed:
                event=explicit
            else:
                kind='connector' if source.startswith('connectors.') else 'task' if source.startswith('tasks.') else 'application'
                suffix='failed' if record.levelno>=logging.ERROR else 'warning' if record.levelno>=logging.WARNING else 'event'
                event=f'{kind}_{suffix}'
            row={'id':uuid.uuid4().hex,'timestamp':datetime.now(UTC).isoformat(),'level':record.levelname,'source':source,'event':event}
            pipe=self.redis.pipeline(transaction=True)
            pipe.lpush('apex:operational:logs',json.dumps(row))
            pipe.ltrim('apex:operational:logs',0,999)
            pipe.expire('apex:operational:logs',7*86400)
            if record.levelno>=logging.ERROR:
                pipe.lpush('apex:operational:critical',json.dumps(row))
                pipe.ltrim('apex:operational:critical',0,999)
                pipe.expire('apex:operational:critical',7*86400)
            pipe.execute()
        except Exception:
            pass  # Logging must never block application operations on Redis outage.


def install_operational_buffer():
    root=logging.getLogger()
    if not any(isinstance(h,OperationalBufferHandler) for h in root.handlers):
        root.addHandler(OperationalBufferHandler())
    # Bot API tokens are embedded in the request URL: suppress HTTP client's
    # request logs everywhere, including stdout.
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)
