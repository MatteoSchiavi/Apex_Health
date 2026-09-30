"""Password hashing and session-token primitives.

- Passwords: argon2id (§2, auth_credentials.password_hash).
- Sessions: random 256-bit tokens; only the SHA-256 hash (peppered with
  SESSION_SECRET) is stored in sessions.token_hash — a DB leak must not
  yield usable session tokens.
"""

import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import (
    InvalidHashError,
    VerificationError,
    VerifyMismatchError,
)

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """F-06 audit: catch every argon2 exception surface — VerificationError,
    VerifyMismatchError, InvalidHashError, AND the generic TypeError argon2
    raises for non-string inputs. A malformed stored hash used to surface as
    a 500; now it returns False (auth failure) like every other bad credential.
    """
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError, TypeError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """F-06 audit: returns True when the stored hash's argon2 params are
    weaker than the current ``PasswordHasher`` defaults — the caller should
    re-hash on the next successful login so parameter upgrades are gradual.
    """
    try:
        return _hasher.check_needs_rehash(password_hash)
    except (InvalidHashError, TypeError, ValueError):
        # Malformed hash — cannot rehash, will fail verify_password anyway.
        return False


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_session_token(token: str, session_secret: str) -> str:
    return hashlib.sha256((session_secret + token).encode()).hexdigest()
