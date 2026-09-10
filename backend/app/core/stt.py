"""STT adapter (§2: OpenAI Whisper API — cheap, reliable, voice notes are
short). One interface, lazy provider; the fixture implementation in tests is
the only thing CI ever exercises (§0/§20)."""

import logging
from typing import Protocol

import httpx

from app.core.config import get_settings

logger = logging.getLogger("core.stt")


class STTError(Exception):
    pass


class STTClient(Protocol):
    async def transcribe(self, audio: bytes, filename: str = "voice.ogg") -> str: ...


class LiveWhisperSTT:
    """OpenAI audio/transcriptions (§5 OPENAI_API_KEY). Built only by the
    voice task in production."""

    def __init__(self, api_key: str | None = None, api_base: str | None = None, model: str | None = None) -> None:
        settings = get_settings()
        self._api_key = api_key or settings.openai_api_key
        self._api_base = (api_base or settings.openai_api_base).rstrip("/")
        self._model = model or settings.whisper_model
        self._client = httpx.AsyncClient(timeout=120.0)
        if not self._api_key:
            raise STTError("OPENAI_API_KEY is not set — live transcription is unavailable")

    async def transcribe(self, audio: bytes, filename: str = "voice.ogg") -> str:
        try:
            resp = await self._client.post(
                f"{self._api_base}/audio/transcriptions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                files={"file": (filename, audio, "audio/ogg")},
                data={"model": self._model},
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise STTError(f"Whisper transcription failed: {exc}") from exc
        return resp.json()["text"]


def build_stt_client() -> STTClient:
    """Production client from settings. Tests inject fixture STT instead."""
    return LiveWhisperSTT()
