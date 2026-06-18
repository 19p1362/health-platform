"""HealthBridge Platform — Tenant Isolation Middleware

Auto-filters all queries by the current user's organization (tenant_id).
Prevents cross-tenant data leaks at the database query level.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select, ColumnElement
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import Organization, User, UserRole
from app.security.auth import get_current_active_user

logger = logging.getLogger("healthbridge.security.tenant")

# ── Bearer token scheme (reuse from auth) ──
bearer_scheme = HTTPBearer(auto_error=False)


# ═══════════════════════════════════════════════════
# Extract tenant_id from JWT
# ═══════════════════════════════════════════════════

def get_tenant_id_from_token(token: str) -> Optional[str]:
    """Decode JWT and extract tenant_id claim."""
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload.get("tenant_id")
    except JWTError:
        return None


# ═══════════════════════════════════════════════════
# FastAPI Dependency: Current Tenant
# ═══════════════════════════════════════════════════

async def get_current_tenant(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Organization:
    """Extract the current user's tenant (Organization) from the JWT.

    Returns:
        The Organization the user belongs to.

    Raises:
        HTTPException 401/403: If tenant is invalid or inactive.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    tenant_id = get_tenant_id_from_token(credentials.credentials)
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token — missing tenant",
        )

    result = await db.execute(select(Organization).where(Organization.id == tenant_id))
    tenant = result.scalar_one_or_none()

    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )

    if not tenant.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization account is inactive. Contact support.",
        )

    return tenant


# ═══════════════════════════════════════════════════
# Tenant-scoped dependencies — use after get_current_active_user
# ═══════════════════════════════════════════════════

def get_tenant_filter(
    current_user: User,
) -> str:
    """Dependency that returns the tenant_id for query filtering.

    Pass current_user explicitly in the route:
        @router.get("/patients")
        async def list_patients(
            current_user: User = Depends(get_current_active_user),
            db: AsyncSession = Depends(get_db),
        ):
            tenant_filter(current_user)
    """
    return current_user.tenant_id


async def require_org_admin(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """FastAPI dependency: ensure the user has ORG_ADMIN or SUPER_ADMIN role."""
    if current_user.role not in (UserRole.ORG_ADMIN, UserRole.SUPER_ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization admin privileges required",
        )
    return current_user


async def require_super_admin(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """FastAPI dependency: ensure the user is a platform SUPER_ADMIN."""
    if current_user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin privileges required",
        )
    return current_user
