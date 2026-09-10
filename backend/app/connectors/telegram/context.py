"""Bot runtime context: dependency container passed to every handler.

Production wiring lives in the polling entrypoint (live Telegram client +
Celery voice dispatch); tests inject fixture clients and an inline voice
dispatcher so the full handler pipeline runs deterministically (§0/§20).
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker

logger = logging.getLogger("connectors.telegram.context")

# VoiceDispatcher: hands a voice message off to background processing
# (§10.2: handler acknowledges, hands off to Celery). Awaitable, fire-safe.
VoiceDispatcher = Callable[..., Awaitable[None]]


@dataclass
class BotContext:
    telegram: Any  # TelegramClient (Protocol; Any keeps dataclass lean)
    sessionmaker: async_sessionmaker
    redis: Redis  # one-time link codes + edit-flow state (§10.3)
    dispatch_voice: VoiceDispatcher
    # LLM/embedding clients are built lazily (§8.1): only flows that actually
    # call the model pay the construction cost, and tests inject fixtures.
    llm_factory: Callable[[], Any] = lambda: _missing_llm()
    embeddings_factory: Callable[[], Any] | None = None  # None = embeddings off

    def embeddings_client(self) -> Any | None:
        """Embedding client for this turn (§8.3 search_context, §6.2 pinned
        model) — or None when the runtime has no OPENAI_API_KEY; the agent
        loop degrades search_context to a readable result."""
        if self.embeddings_factory is None:
            return None
        return self.embeddings_factory()

    async def enqueue_voice(self, **kwargs: Any) -> None:
        """Fire-and-forget voice hand-off so polling continues immediately."""
        task = asyncio.create_task(self.dispatch_voice(**kwargs))
        task.add_done_callback(_log_task_failure)


def _missing_llm() -> Any:
    raise RuntimeError("BotContext.llm_factory not configured by this runtime")


def _log_task_failure(task: asyncio.Task) -> None:
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error("voice pipeline task failed: %s", exc, exc_info=exc)
