"""Startup secret validation (F-12 audit fix).

The audit (F-12) flagged that ``ensure_owner`` runs at boot with no
secret-strength validation: an unset/weak OWNER_PASSWORD silently creates
an owner from ``hash_password("")`` and SESSION_SECRET/ENCRYPTION_KEY typos
silently deploy guessable bootstrap credentials.

This module is invoked from the FastAPI lifespan BEFORE ``ensure_owner`` so
a misconfigured production boot fails loudly instead of creating a
compromised owner account. Dev/test environments are exempt (``environment``
setting) so local sandboxes still boot with the test defaults.
"""

from __future__ import annotations

import base64
import binascii
import logging
import os
import re

from app.core.config import get_settings

logger = logging.getLogger("core.secret_validation")


class SecretValidationError(RuntimeError):
    """Raised when a production boot would create guessable credentials."""


# Minimum entropy requirements (F-12).
MIN_SESSION_SECRET_LEN = 32  # 256 bits → 32 bytes of base64 entropy
MIN_OWNER_PASSWORD_LEN = 12  # OWASP minimum; argon2id makes brute force expensive
MIN_ENCRYPTION_KEY_BYTES = 32  # Fernet expects 32 bytes (urlsafe_b64 → 44 chars)

# Known-default / test-only values that must NEVER ship to production.
_KNOWN_BAD_SECRETS = frozenset(
    {
        "test-session-secret",
        "test-encryption-key",
        "changeme",
        "secret",
        "password",
        "",
    }
)


def _is_production() -> bool:
    """Production = environment is 'prod' OR OWNER_EMAIL/OWNER_PASSWORD look
    real (not the test defaults). Dev/test sandboxes stay exempt."""
    settings = get_settings()
    if settings.environment == "prod":
        return True
    # Heuristic: real OWNER_EMAIL has a real domain; test defaults use
    # apexhealth.dev (a reserved TLD that cannot ship to prod).
    if settings.owner_email and not settings.owner_email.endswith("@apexhealth.dev"):
        return True
    return False


def _is_strong_password(password: str) -> tuple[bool, str | None]:
    """OWASP-style strength check: ≥12 chars, ≥3 of {lower, upper, digit, symbol}."""
    if len(password) < MIN_OWNER_PASSWORD_LEN:
        return False, f"must be at least {MIN_OWNER_PASSWORD_LEN} characters"
    classes = sum(
        1
        for pattern in (
            re.compile(r"[a-z]"),
            re.compile(r"[A-Z]"),
            re.compile(r"[0-9]"),
            re.compile(r"[^a-zA-Z0-9]"),
        )
        if pattern.search(password)
    )
    if classes < 3:
        return False, "must contain at least 3 of: lowercase, uppercase, digit, symbol"
    return True, None


def _decode_key_length(key: str) -> int | None:
    """Return the byte length of a base64-encoded key, or None on parse error."""
    try:
        return len(base64.urlsafe_b64decode(key.encode("ascii")))
    except (binascii.Error, ValueError):
        return None


def validate_startup_secrets() -> None:
    """F-12 audit: refuse to boot in production with weak/default secrets.

    Raises ``SecretValidationError`` on failure; logs a warning on dev
    exemption. Called from the FastAPI lifespan before ``ensure_owner``.
    """
    settings = get_settings()
    if not _is_production():
        logger.info(
            "startup secret validation skipped (environment=%s, owner_email=%s)",
            settings.environment, settings.owner_email,
        )
        return

    problems: list[str] = []

    # SESSION_SECRET: ≥32 chars, not a known-bad default.
    if len(settings.session_secret) < MIN_SESSION_SECRET_LEN:
        problems.append(
            f"SESSION_SECRET too short ({len(settings.session_secret)} < "
            f"{MIN_SESSION_SECRET_LEN} chars)"
        )
    if settings.session_secret in _KNOWN_BAD_SECRETS:
        problems.append("SESSION_SECRET is a known default value")
    if settings.session_secret == settings.encryption_key:
        problems.append("SESSION_SECRET and ENCRYPTION_KEY must not be equal")

    # ENCRYPTION_KEY: must decode to ≥32 bytes (Fernet's requirement).
    key_len = _decode_key_length(settings.encryption_key)
    if key_len is None:
        problems.append("ENCRYPTION_KEY is not valid urlsafe-base64")
    elif key_len < MIN_ENCRYPTION_KEY_BYTES:
        problems.append(
            f"ENCRYPTION_KEY decodes to {key_len} bytes (< "
            f"{MIN_ENCRYPTION_KEY_BYTES})"
        )
    if settings.encryption_key in _KNOWN_BAD_SECRETS:
        problems.append("ENCRYPTION_KEY is a known default value")

    # OWNER_PASSWORD: strength check (also covers empty/blank).
    ok, reason = _is_strong_password(settings.owner_password)
    if not ok:
        problems.append(f"OWNER_PASSWORD {reason}")
    if settings.owner_password in _KNOWN_BAD_SECRETS:
        problems.append("OWNER_PASSWORD is a known default value")

    # OWNER_EMAIL: must look like an email.
    if not settings.owner_email or "@" not in settings.owner_email:
        problems.append("OWNER_EMAIL must be a valid email address")

    if problems:
        joined = "; ".join(problems)
        logger.error("startup secret validation FAILED: %s", joined)
        raise SecretValidationError(
            f"Refusing to boot production with weak/default secrets: {joined}. "
            "Set strong SESSION_SECRET (≥32 chars), ENCRYPTION_KEY (base64-encoded "
            "32 bytes), and OWNER_PASSWORD (≥12 chars, 3+ character classes) in "
            "the environment and restart."
        )
    logger.info("startup secret validation passed (production mode)")
