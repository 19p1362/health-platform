"""HealthBridge Platform — Field-Level Encryption with Fernet

Provides symmetric encryption/decryption of sensitive patient fields
using the ``cryptography.fernet`` library. Supports encrypting individual
strings, JSON field subsets, and masking values for display.
"""
from __future__ import annotations

import base64
import logging
import warnings
from pathlib import Path
from typing import Any, Optional

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings

logger = logging.getLogger("healthbridge.security.encryption")

# ── Key file path ──
_KEY_DIR = Path.home() / ".healthbridge"
_KEY_FILE = _KEY_DIR / "encryption.key"


# ═══════════════════════════════════════════════════
# Key Management
# ═══════════════════════════════════════════════════

def _generate_and_save_key() -> bytes:
    """Generate a new Fernet key, save it to disk, and return the key bytes.

    The key is stored at ``~/.healthbridge/encryption.key``.

    Returns:
        32-byte url-safe-base64 encoded Fernet key.
    """
    _KEY_DIR.mkdir(parents=True, exist_ok=True)
    key = Fernet.generate_key()
    _KEY_FILE.write_bytes(key)
    # Restrict permissions (Unix only)
    try:
        _KEY_FILE.chmod(0o600)
    except PermissionError:
        pass
    logger.info(f"Generated new encryption key at {_KEY_FILE}")
    return key


def _load_key_from_file() -> Optional[bytes]:
    """Load the Fernet key from the local key file.

    Returns:
        The key bytes if the file exists and is valid, else None.
    """
    if _KEY_FILE.exists():
        try:
            key = _KEY_FILE.read_bytes()
            # Validate that it looks like a Fernet key (32-byte urlsafe-base64)
            decoded = base64.urlsafe_b64decode(key)
            if len(decoded) == 32:
                return key
            logger.warning(f"Key file {_KEY_FILE} contains an invalid key (wrong length)")
        except (ValueError, OSError) as exc:
            logger.warning(f"Could not read key file {_KEY_FILE}: {exc}")
    return None


def get_encryption_key() -> Fernet:
    """Get the Fernet cipher instance.

    Priority:
    1. ``settings.ENCRYPTION_KEY`` (from environment / .env)
    2. ``~/.healthbridge/encryption.key`` auto-generated file
    3. Auto-generate a new key (with warning)

    If ``settings.ENCRYPTION_KEY`` is the default placeholder, a warning is emitted
    and the key from the file (or a newly generated one) is used instead.

    Returns:
        A :class:`cryptography.fernet.Fernet` instance ready for encrypt/decrypt.
    """
    key: bytes | None = None

    # 1. Try configured key from settings
    configured_key = settings.ENCRYPTION_KEY
    if configured_key and configured_key not in ("", "change-me-in-production"):
        try:
            # Ensure the key is properly padded / decoded as needed
            key = configured_key.encode("utf-8") if isinstance(configured_key, str) else configured_key
            # Validate it's a proper Fernet key
            Fernet(key)
            return Fernet(key)
        except (ValueError, TypeError) as exc:
            logger.warning(
                f"settings.ENCRYPTION_KEY is invalid ({exc}). "
                f"Falling back to key file."
            )

    # 2. Try key file
    key = _load_key_from_file()
    if key is not None:
        try:
            Fernet(key)
            return Fernet(key)
        except ValueError:
            logger.warning("Key file content is not a valid Fernet key — regenerating")

    # 3. Generate fresh key (fallback)
    warnings.warn(
        "No ENCRYPTION_KEY configured in settings and no existing key file found. "
        "A new encryption key has been auto-generated at "
        f"{_KEY_FILE}. This key MUST be backed up or configured via "
        "the ENCRYPTION_KEY environment variable — data encrypted with "
        "this key will be unrecoverable if the file is lost.",
        RuntimeWarning,
        stacklevel=2,
    )
    key = _generate_and_save_key()
    return Fernet(key)


# ═══════════════════════════════════════════════════
# Field-Level Encryption / Decryption
# ═══════════════════════════════════════════════════

def encrypt_field(plaintext: str | None) -> str | None:
    """Encrypt a single plaintext string with Fernet symmetric encryption.

    The result is returned as a base64-encoded string suitable for storage
    in a ``TEXT`` column.

    Args:
        plaintext: The value to encrypt. ``None`` is passed through.

    Returns:
        Encrypted base64 string, or ``None`` if input was ``None``.
    """
    if plaintext is None:
        return None
    cipher = get_encryption_key()
    encrypted_bytes = cipher.encrypt(plaintext.encode("utf-8"))
    return encrypted_bytes.decode("utf-8")


def decrypt_field(ciphertext: str | None) -> str | None:
    """Decrypt a Fernet-encrypted field back to its original plaintext.

    Args:
        ciphertext: The base64-encoded encrypted string. ``None`` passes through.

    Returns:
        Decrypted plaintext string, or ``None`` if input was ``None``.

    Raises:
        ValueError: If the ciphertext is malformed or the key is wrong.
    """
    if ciphertext is None:
        return None
    try:
        cipher = get_encryption_key()
        decrypted_bytes = cipher.decrypt(ciphertext.encode("utf-8"))
        return decrypted_bytes.decode("utf-8")
    except InvalidToken as exc:
        logger.error("Failed to decrypt field — invalid token or wrong key")
        raise ValueError("Decryption failed — data may have been tampered with or re-encrypted with a different key") from exc
    except Exception as exc:
        logger.error(f"Unexpected decryption error: {exc}")
        raise


# ═══════════════════════════════════════════════════
# JSON Field Encryption
# ═══════════════════════════════════════════════════

def _set_nested(d: dict[str, Any], keys: list[str], value: Any) -> None:
    """Set a value at a nested key path within a dictionary, creating intermediates.

    Args:
        d: The dict to mutate.
        keys: Path segments, e.g. ``["patient", "phone"]``.
        value: Value to set at the leaf.
    """
    for key in keys[:-1]:
        d = d.setdefault(key, {})
    d[keys[-1]] = value


def _get_nested(d: dict[str, Any], keys: list[str]) -> Any:
    """Get a value from a nested key path.

    Args:
        d: The dict to traverse.
        keys: Path segments.

    Returns:
        Value at the leaf, or ``None`` if any intermediate key is missing.
    """
    for key in keys:
        if isinstance(d, dict):
            d = d.get(key)
        else:
            return None
    return d


def encrypt_json(data: dict[str, Any], fields: list[str]) -> dict[str, Any]:
    """Encrypt specified fields within a JSON-serializable dictionary.

    Supports dot-notation for nested fields, e.g. ``"demographics.phone"``.

    Args:
        data: The source dictionary (not mutated — a copy is returned).
        fields: List of field names (or dot-notation paths) to encrypt.

    Returns:
        A new dictionary with the specified fields replaced by their
        encrypted (base64) representations.
    """
    result = __import__("copy").deepcopy(data)

    for field_path in fields:
        parts = field_path.split(".")
        value = _get_nested(result, parts)
        if value is not None and isinstance(value, str):
            encrypted = encrypt_field(value)
            _set_nested(result, parts, encrypted)

    return result


def decrypt_json(data: dict[str, Any], fields: list[str]) -> dict[str, Any]:
    """Decrypt previously encrypted fields within a dictionary.

    The reverse of :func:`encrypt_json`.

    Args:
        data: The dictionary containing encrypted fields.
        fields: List of field names (or dot-notation paths) to decrypt.

    Returns:
        A new dictionary with the specified fields decrypted back to plaintext.
    """
    result = __import__("copy").deepcopy(data)

    for field_path in fields:
        parts = field_path.split(".")
        value = _get_nested(result, parts)
        if value is not None and isinstance(value, str):
            try:
                decrypted = decrypt_field(value)
                _set_nested(result, parts, decrypted)
            except ValueError:
                # If it can't be decrypted (e.g., already plaintext), leave as-is
                logger.warning(f"Field '{field_path}' could not be decrypted — leaving unchanged")
                continue

    return result


# ═══════════════════════════════════════════════════
# Data Masking
# ═══════════════════════════════════════════════════

def mask_field(value: str) -> str:
    """Mask a sensitive value showing only the first and last characters.

    Follows a UIDAI/Aadhaar-style masking pattern: ``a***n``.
    - Single character -> ``*``
    - Two characters -> ``a*``
    - Three characters -> ``a**c``
    - Four or more -> ``a***n`` (first char + '***' + last char)

    Args:
        value: The original string to mask.

    Returns:
        Masked string.
    """
    if not value:
        return ""
    if len(value) == 1:
        return "*"
    if len(value) == 2:
        return f"{value[0]}*"
    if len(value) == 3:
        return f"{value[0]}**{value[-1]}"
    # Four or more characters: show first and last, mask middle
    return f"{value[0]}{'*' * (len(value) - 2)}{value[-1]}"
