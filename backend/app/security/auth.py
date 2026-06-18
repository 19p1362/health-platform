"""HealthBridge Platform — Authentication & JWT Token Management

Provides JWT token creation/verification, password hashing via bcrypt,
FastAPI dependency injection for protected routes, and brute-force
login protection with account lockout.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import User

logger = logging.getLogger("healthbridge.security.auth")

# ── Password hashing context ──
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12,
)

# ── Bearer token scheme ──
bearer_scheme = HTTPBearer(auto_error=False)

# ── In-memory login attempt tracker (use Redis in production) ──
# Structure: {email: {"attempts": int, "locked_until": datetime | None}}
_login_attempts: dict[str, dict[str, Any]] = {}


# ═══════════════════════════════════════════════════
# Password Hashing & Verification
# ═══════════════════════════════════════════════════

def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    return pwd_context.verify(plain_password, hashed_password)


# ═══════════════════════════════════════════════════
# JWT Token Creation & Verification
# ═══════════════════════════════════════════════════

def create_access_token(
    data: dict[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a signed JWT access token.

    Args:
        data: Payload claims to encode (must include at least 'sub').
        expires_delta: Token lifetime override (defaults to config value).

    Returns:
        Encoded JWT string.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta
        or timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc), "type": "access"})
    encoded = jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return encoded


def create_refresh_token(
    data: dict[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a signed JWT refresh token with longer expiry.

    Args:
        data: Payload claims (must include 'sub').
        expires_delta: Override lifetime (defaults to config JWT_REFRESH_TOKEN_EXPIRE_DAYS).

    Returns:
        Encoded JWT refresh token string.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta
        or timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    )
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc), "type": "refresh"})
    encoded = jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return encoded


def verify_token(token: str) -> dict[str, Any]:
    """Verify and decode a JWT token.

    Args:
        token: The JWT string to verify.

    Returns:
        Decoded payload dictionary.

    Raises:
        HTTPException 401: If token is invalid, expired, or tampered with.
    """
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except JWTError as exc:
        logger.warning(f"JWT verification failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def verify_refresh_token(token: str) -> dict[str, Any]:
    """Verify a refresh token and ensure it is of type 'refresh'.

    Args:
        token: The refresh JWT string.

    Returns:
        Decoded payload if valid.

    Raises:
        HTTPException 401: If token is not a refresh token or is invalid.
    """
    payload = verify_token(token)
    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type — expected refresh token",
        )
    return payload


# ═══════════════════════════════════════════════════
# Login Attempt Tracking & Brute Force Protection
# ═══════════════════════════════════════════════════

def _check_lockout(email: str) -> None:
    """Check if the account is currently locked due to too many failed attempts.

    Raises:
        HTTPException 423: If account is locked.
    """
    record = _login_attempts.get(email)
    if record and record.get("locked_until"):
        if datetime.now(timezone.utc) < record["locked_until"]:
            remaining = (record["locked_until"] - datetime.now(timezone.utc)).seconds
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail=f"Account locked due to too many failed login attempts. "
                       f"Try again in {remaining} seconds.",
            )
        else:
            # Lockout period expired — reset
            del _login_attempts[email]


def _record_failed_attempt(email: str) -> None:
    """Record a failed login attempt and lock the account if threshold exceeded."""
    now = datetime.now(timezone.utc)
    record = _login_attempts.setdefault(email, {"attempts": 0, "locked_until": None})
    record["attempts"] += 1

    if record["attempts"] >= settings.MAX_LOGIN_ATTEMPTS:
        lockout_duration = timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)
        record["locked_until"] = now + lockout_duration
        logger.warning(
            f"Account {email} locked for {settings.LOGIN_LOCKOUT_MINUTES} minutes "
            f"after {record['attempts']} failed attempts."
        )


def _reset_attempts(email: str) -> None:
    """Clear the failed-attempt counter on successful login."""
    _login_attempts.pop(email, None)


# ═══════════════════════════════════════════════════
# User Authentication
# ═══════════════════════════════════════════════════

async def authenticate_user(
    db: AsyncSession,
    email: str,
    password: str,
) -> Optional[User]:
    """Authenticate a user by email and password.

    Checks account lockout, verifies credentials, and tracks login attempts.
    Resets attempt counter on success.

    Args:
        db: Async database session.
        email: User email address.
        password: Plaintext password.

    Returns:
        Authenticated User object, or None if credentials are invalid.
    """
    # Check lockout before even attempting lookup
    _check_lockout(email)

    # Fetch user
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None:
        # Record a failed attempt even for unknown emails (prevents enumeration)
        _record_failed_attempt(email)
        logger.info(f"Login attempt for non-existent user: {email}")
        return None

    # Check if account is already locked at DB level
    if user.is_locked:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Account is locked. Contact an administrator.",
        )

    # Verify password
    if not verify_password(password, user.password_hash):
        _record_failed_attempt(email)

        # Persist lock state to DB if threshold crossed
        if _login_attempts.get(email, {}).get("locked_until"):
            user.is_locked = True
            db.add(user)

        logger.info(f"Failed login attempt for {email}")
        return None

    # Success — reset attempts
    _reset_attempts(email)

    # Update user record
    user.last_login = datetime.utcnow()
    user.login_attempts = 0
    user.is_locked = False
    db.add(user)

    return user


# ═══════════════════════════════════════════════════
# FastAPI Dependency: Get Current User
# ═══════════════════════════════════════════════════

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """FastAPI dependency that extracts and validates the current user from a Bearer token.

    Expects the token in the ``Authorization: Bearer <token>`` header.

    Returns:
        The authenticated User object.

    Raises:
        HTTPException 401: If the token is missing, invalid, or the user is not found.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated — Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = verify_token(credentials.credentials)
    email: str | None = payload.get("sub")
    if email is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload — missing subject",
        )

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """FastAPI dependency that ensures the current user is active and not locked.

    Must be used after ``get_current_user`` (or chained via ``Depends``).

    Returns:
        The active User object.

    Raises:
        HTTPException 400: If the user account is inactive or locked.
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user account",
        )
    if current_user.is_locked:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Account is locked. Contact an administrator.",
        )
    return current_user
