"""Password hashing and session-token primitives.

- Passwords: argon2id (§2, auth_credentials.password_hash).
- Sessions: random 256-bit tokens; only the SHA-256 hash (peppered with
  SESSION_SECRET) is stored in sessions.token_hash — a DB leak must not
  yield usable session tokens.
"""

import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        _hasher.verify(password_hash, password)
    except VerificationError:
        return False
    return True


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_session_token(token: str, session_secret: str) -> str:
    return hashlib.sha256((session_secret + token).encode()).hexdigest()
