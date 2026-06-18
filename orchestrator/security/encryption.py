"""encryption — Fernet symmetric encryption, SHA-256 hashing, and PII masking.

Provides field-level at-rest encryption for sensitive personal data (PHI/PII)
compliant with DPDP 2025 Section 8 (Security Safeguards) and HIPAA Security Rule.

Public functions:
    encrypt_field(plaintext)     — Fernet-encrypt a single string value
    decrypt_field(ciphertext)    — Fernet-decrypt a single string value
    encrypt_json(data, fields)   — Deep-copy dict with specific fields encrypted
    decrypt_json(data, fields)   — Deep-copy dict with specific fields decrypted
    mask_field(value)            — Produce a ``a***n`` masked display value
    hash_value(value)            — SHA-256 hex digest (for irreversible storage)
    generate_encryption_key()    — Generate a new Fernet key (base64-encoded)
"""

import os
import json
import base64
import hashlib
import logging
from copy import deepcopy
from pathlib import Path
from typing import Any, Optional, Sequence, Union

try:
    from cryptography.fernet import Fernet, InvalidToken
except ImportError:
    Fernet = None        # type: ignore[assignment]
    InvalidToken = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Key resolution
# Priority: ENCRYPTION_KEY env var → ~/.healthcare-orchestra/encryption.key
#           → auto-generate with warning (dev only)
# ---------------------------------------------------------------------------

_KEY_PATH: Path = Path.home() / ".healthcare-orchestra" / "encryption.key"
_ENCRYPTION_KEY: Optional[str] = os.getenv("ENCRYPTION_KEY")


def _resolve_key() -> bytes:
    """Return the Fernet key as bytes, resolving via the priority chain."""
    global _ENCRYPTION_KEY

    # 1. Environment variable
    key_str = _ENCRYPTION_KEY
    if key_str:
        try:
            return key_str.encode("utf-8") if isinstance(key_str, str) else key_str
        except Exception:
            logger.warning("ENCRYPTION_KEY env var is invalid; trying file fallback")

    # 2. Key file on disk
    if _KEY_PATH.exists():
        try:
            key_bytes = _KEY_PATH.read_bytes().strip()
            # Validate key by trying to create a Fernet instance
            Fernet(key_bytes)
            return key_bytes
        except Exception:
            logger.warning("Key file %s is corrupt or invalid; regenerating", _KEY_PATH)

    # 3. Auto-generate (dev-only — prints loud warning)
    logger.warning(
        "No ENCRYPTION_KEY found in env or %s. "
        "Auto-generating an ephemeral key. "
        "Any encrypted data will be UNREADABLE after a server restart!",
        _KEY_PATH,
    )
    new_key = Fernet.generate_key()
    # Persist so at least we survive a hot reload
    _KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    _KEY_PATH.write_bytes(new_key + b"\n")
    _KEY_PATH.chmod(0o600)
    logger.info("Wrote auto-generated encryption key to %s", _KEY_PATH)
    return new_key


def _get_fernet() -> "Fernet":
    """Return a Fernet cipher instance (lazy init)."""
    if Fernet is None:
        raise ImportError(
            "cryptography is required for Fernet encryption. "
            "Install with: pip install cryptography"
        )
    return Fernet(_resolve_key())


# ---------------------------------------------------------------------------
# Public API — Fernet field-level encryption
# ---------------------------------------------------------------------------

def encrypt_field(plaintext: Optional[str]) -> Optional[str]:
    """Fernet-encrypt a single string value.

    Parameters
    ----------
    plaintext : str or None
        The text to encrypt.  ``None`` is passed through unchanged.

    Returns
    -------
    str or None
        Base64-encoded ciphertext string, or ``None``.
    """
    if plaintext is None:
        return None
    cipher = _get_fernet()
    return cipher.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_field(ciphertext: Optional[str]) -> Optional[str]:
    """Fernet-decrypt a single string value.

    Parameters
    ----------
    ciphertext : str or None
        The encrypted text (base64 Fernet token).  ``None`` is passed through.

    Returns
    -------
    str or None
        Original plaintext, or ``None``.

    Raises
    ------
    cryptography.fernet.InvalidToken
        If the ciphertext is corrupted or the key does not match.
    """
    if ciphertext is None:
        return None
    cipher = _get_fernet()
    return cipher.decrypt(ciphertext.encode("utf-8")).decode("utf-8")


# ---------------------------------------------------------------------------
# Public API — dict-level encrypt/decrypt (deep-copy, field-targeted)
# ---------------------------------------------------------------------------

def encrypt_json(
    data: dict[str, Any],
    fields: Sequence[str],
) -> dict[str, Any]:
    """Return a deep copy of *data* with the named *fields* encrypted in-place.

    Non-existent fields are silently ignored.

    Parameters
    ----------
    data : dict
        Source dictionary (not mutated).
    fields : Sequence[str]
        Names of top-level fields to encrypt.

    Returns
    -------
    dict
        Deep copy with encrypted field values.
    """
    result = deepcopy(data)
    for field in fields:
        if field in result and result[field] is not None:
            try:
                result[field] = encrypt_field(str(result[field]))
            except Exception:
                logger.exception("Failed to encrypt field %r", field)
    return result


def decrypt_json(
    data: dict[str, Any],
    fields: Sequence[str],
) -> dict[str, Any]:
    """Return a deep copy of *data* with the named *fields* decrypted in-place.

    Non-existent fields are silently ignored.  Fields that are not valid
    Fernet tokens are passed through unchanged (so you can safely call
    this on partially-encrypted data).

    Parameters
    ----------
    data : dict
        Source dictionary (not mutated).
    fields : Sequence[str]
        Names of top-level fields to decrypt.

    Returns
    -------
    dict
        Deep copy with decrypted field values.
    """
    result = deepcopy(data)
    for field in fields:
        if field in result and isinstance(result[field], str):
            try:
                result[field] = decrypt_field(result[field])
            except (InvalidToken, Exception):
                pass  # not encrypted or wrong key — leave as-is
    return result


# ---------------------------------------------------------------------------
# Public API — PII masking (a***n style)
# ---------------------------------------------------------------------------

def mask_field(value: Optional[str], visible_chars: int = 1) -> Optional[str]:
    """Produce a masked display value (e.g. ``a***n`` or ``+**********0``).

    This is the **UIDAI-recommended** masking pattern for Aadhaar numbers
    and is appropriate for any PII/PHI displayed in dashboards, logs, or
    API responses returned to non-privileged roles.

    Parameters
    ----------
    value : str or None
        The original plaintext value.  ``None`` is passed through.

    visible_chars : int
        Number of leading and trailing characters to leave unmasked.
        Defaults to 1 (``a***z``).  Pass 2 for an ``ab**yz`` pattern.

    Returns
    -------
    str or None
        Masked string, or ``None``.
    """
    if value is None or visible_chars < 0:
        return None
    if not value:
        return value

    v = str(value)
    length = len(v)

    if length <= visible_chars * 2:
        # Too short to mask meaningfully — return the original
        return v

    prefix = v[:visible_chars]
    suffix = v[-visible_chars:]
    masked = "*" * (length - visible_chars * 2)
    return f"{prefix}{masked}{suffix}"


# ---------------------------------------------------------------------------
# Public API — SHA-256 hashing (irreversible)
# ---------------------------------------------------------------------------

def hash_value(value: str) -> str:
    """Return the SHA-256 hex digest of *value*.

    Use this for **irreversible** storage of identifiers such as Aadhaar
    numbers (per UIDAI guidance), session tokens, or API keys that you
    never need to recover in plaintext.

    The result is a 64-character lowercase hex string.

    Parameters
    ----------
    value : str
        The value to hash.

    Returns
    -------
    str
        ``sha256(value)`` hex digest.
    """
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Public API — key generation
# ---------------------------------------------------------------------------

def generate_encryption_key() -> str:
    """Generate a new Fernet-compatible 32-byte key as a base64-encoded string.

    Returns
    -------
    str
        Base64-encoded key (safe to store in ``.env`` as ``ENCRYPTION_KEY=...``).
    """
    if Fernet is None:
        raise ImportError("cryptography is required to generate Fernet keys")
    return Fernet.generate_key().decode("utf-8")
