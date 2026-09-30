"""Application-layer symmetric encryption (§17).

`integrations.credentials_encrypted` and later `lab_panels` are encrypted here
BEFORE they touch disk — the DB stores opaque bytes, never plaintext secrets.
The key is derived from ENCRYPTION_KEY (§5) via SHA-256, presented to Fernet in
the urlsafe-base64 form it requires.
"""

import base64
import hashlib
import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken


class EncryptionError(Exception):
    """Raised when ciphertext cannot be decrypted (wrong key or corrupt data)."""


def _fernet() -> Fernet:
    key = get_key_bytes()
    return Fernet(base64.urlsafe_b64encode(key))


def get_key_bytes() -> bytes:
    from app.core.config import get_settings

    return hashlib.sha256(get_settings().encryption_key.encode("utf-8")).digest()


def encrypt_bytes(plaintext: bytes) -> bytes:
    return _fernet().encrypt(plaintext)


def decrypt_bytes(ciphertext: bytes) -> bytes:
    try:
        return _fernet().decrypt(ciphertext)
    except InvalidToken as exc:
        raise EncryptionError("decryption failed: wrong key or corrupt ciphertext") from exc


def encrypt_json(obj: Any) -> bytes:
    return encrypt_bytes(json.dumps(obj, separators=(",", ":")).encode("utf-8"))


def decrypt_json(ciphertext: bytes) -> Any:
    return json.loads(decrypt_bytes(ciphertext))
