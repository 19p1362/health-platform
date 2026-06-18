"""auth — JWT token management and bcrypt password hashing.

Public functions:
    create_access_token(data, expires_delta=None)
    verify_token(token)
    hash_password(password)
    verify_password(password, password_hash)
    authenticate_user(email, password)
    get_current_user(token)
"""

import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

try:
    import jwt
except ImportError:
    jwt = None  # type: ignore[assignment]

try:
    from passlib.context import CryptContext
except ImportError:
    CryptContext = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration (mirrors config.py but with safe defaults)
# ---------------------------------------------------------------------------

SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "change-me-in-production-use-a-256-bit-key")
ALGORITHM: str = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))

# bcrypt context — rounds=12 is the current OWASP recommendation
_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto") if CryptContext else None

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ensure_jwt() -> None:
    """Raise ImportError if the ``jwt`` (PyJWT) library is missing."""
    if jwt is None:
        raise ImportError(
            "PyJWT is required for JWT support. Install with: pip install pyjwt"
        )


def _ensure_bcrypt() -> None:
    """Raise ImportError if passlib (with bcrypt) is missing."""
    if CryptContext is None:
        raise ImportError(
            "passlib[bcrypt] is required for password hashing. "
            "Install with: pip install passlib[bcrypt] bcrypt==4.2.1"
        )


# ---------------------------------------------------------------------------
# Public API — JWT
# ---------------------------------------------------------------------------

def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a signed JWT access token.

    Parameters
    ----------
    data : dict
        Claims payload.  Should include at least ``sub`` (user identifier)
        and may include ``user_id``, ``role``, etc.
    expires_delta : timedelta, optional
        Token lifetime.  Defaults to ``ACCESS_TOKEN_EXPIRE_MINUTES``.

    Returns
    -------
    str
        Encoded JWT string.
    """
    _ensure_jwt()
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str) -> dict:
    """Decode and validate a JWT access token.

    Parameters
    ----------
    token : str
        The encoded JWT string.

    Returns
    -------
    dict
        Decoded payload (contains ``sub``, ``exp``, and any custom claims).

    Raises
    ------
    jwt.ExpiredSignatureError
        If the token has expired.
    jwt.InvalidTokenError
        If the token is malformed or signature is invalid.
    """
    _ensure_jwt()
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])


# ---------------------------------------------------------------------------
# Public API — bcrypt password hashing
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt (12 rounds).

    Parameters
    ----------
    password : str
        Plaintext password.

    Returns
    -------
    str
        bcrypt hash string (``$2b$12$...``).
    """
    _ensure_bcrypt()
    return _pwd_ctx.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a plaintext password against a bcrypt hash.

    Parameters
    ----------
    password : str
        Plaintext password to check.
    password_hash : str
        Stored bcrypt hash.

    Returns
    -------
    bool
        True if the password matches.
    """
    _ensure_bcrypt()
    return _pwd_ctx.verify(password, password_hash)


# ---------------------------------------------------------------------------
# Public API — authentication helper
# ---------------------------------------------------------------------------

# Simple in-memory user store for the prototype.
# In production this would be replaced by a database query.
_LOCAL_USERS: dict = {
    "admin": {
        "password_hash": None,  # set on first call to _init_local_users()
        "role": "admin",
        "user_id": "user-001",
        "email": "admin@healthcare-orchestra.local",
    },
}


def _init_local_users() -> None:
    """Lazily hash the default admin password."""
    if _LOCAL_USERS["admin"]["password_hash"] is None:
        _LOCAL_USERS["admin"]["password_hash"] = hash_password("health2026")


def authenticate_user(email: str, password: str) -> Optional[dict]:
    """Authenticate a user by email and password.

    Parameters
    ----------
    email : str
        User email address.
    password : str
        Plaintext password.

    Returns
    -------
    dict or None
        User record dict (``user_id``, ``email``, ``role``) on success,
        or None on failure.
    """
    _init_local_users()
    user = _LOCAL_USERS.get(email.split("@")[0])
    if user is None:
        return None
    if not verify_password(password, user["password_hash"]):
        return None
    return {
        "user_id": user["user_id"],
        "email": user["email"],
        "role": user["role"],
    }


def get_current_user(token: str) -> Optional[dict]:
    """Extract the current user from a JWT token (dependency helper).

    Parameters
    ----------
    token : str
        Bearer token string.

    Returns
    -------
    dict or None
        User info dict (``user_id``, ``email``, ``role``) or None.
    """
    try:
        payload = verify_token(token)
        return {
            "user_id": payload.get("user_id", ""),
            "email": payload.get("sub", ""),
            "role": payload.get("role", ""),
        }
    except Exception:
        logger.warning("get_current_user: token verification failed", exc_info=True)
        return None
