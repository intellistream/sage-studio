from __future__ import annotations

import base64
import hashlib
import os
import threading

from cryptography.fernet import Fernet, InvalidToken

_SECRET_KEY_ENV = "STUDIO_ENDPOINT_SECRET_KEY"
_CIPHERTEXT_PREFIX = "enc:v1:"

_FERNET_LOCK = threading.Lock()
_FERNET: Fernet | None = None


def encrypt_endpoint_secret(secret: str | None) -> str | None:
    normalized = _normalize(secret)
    if not normalized:
        return None
    if normalized.startswith(_CIPHERTEXT_PREFIX):
        return normalized
    token = _get_fernet().encrypt(normalized.encode("utf-8")).decode("utf-8")
    return f"{_CIPHERTEXT_PREFIX}{token}"


def decrypt_endpoint_secret(secret: str | None) -> str | None:
    normalized = _normalize(secret)
    if not normalized:
        return None
    if not normalized.startswith(_CIPHERTEXT_PREFIX):
        # Backward compatibility for legacy plaintext values.
        return normalized

    token = normalized[len(_CIPHERTEXT_PREFIX) :]
    try:
        decrypted = _get_fernet().decrypt(token.encode("utf-8"))
    except InvalidToken as exc:
        raise ValueError("failed to decrypt endpoint secret") from exc
    return decrypted.decode("utf-8")


def mask_endpoint_secret(secret: str | None) -> str | None:
    normalized = _normalize(secret)
    if not normalized:
        return None
    if normalized.startswith(_CIPHERTEXT_PREFIX):
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:6]
        return f"enc:***{digest}"
    if len(normalized) <= 4:
        return "*" * len(normalized)
    return f"{normalized[:2]}***{normalized[-2:]}"


def _normalize(secret: str | None) -> str | None:
    if secret is None:
        return None
    stripped = secret.strip()
    if not stripped:
        return None
    return stripped


def _get_fernet() -> Fernet:
    global _FERNET
    with _FERNET_LOCK:
        if _FERNET is not None:
            return _FERNET

        configured_key = _resolve_key_from_env()
        if configured_key is not None:
            _FERNET = Fernet(configured_key)
            return _FERNET

        # Development fallback: process-local key when env key is not provided.
        _FERNET = Fernet(Fernet.generate_key())
        return _FERNET


def _resolve_key_from_env() -> bytes | None:
    raw = os.environ.get(_SECRET_KEY_ENV)
    if not raw or not raw.strip():
        return None
    value = raw.strip()
    try:
        decoded = base64.urlsafe_b64decode(value.encode("utf-8") + b"==")
        if len(decoded) == 32:
            return base64.urlsafe_b64encode(decoded)
    except Exception:
        pass
    try:
        decoded = base64.urlsafe_b64decode(value)
        if len(decoded) == 32:
            return value.encode("utf-8")
    except Exception:
        pass
    return None


__all__ = ["decrypt_endpoint_secret", "encrypt_endpoint_secret", "mask_endpoint_secret"]
