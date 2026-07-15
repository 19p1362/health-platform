"""HealthBridge Platform — Role-Based Access Control (RBAC)

Provides a hierarchical RBAC system with role-level and action-level
permission checks. Supports FastAPI dependency injection via
``require_role`` and ``require_permission``.

Role Hierarchy (higher number = more privilege):
    ADMIN(100) > DOCTOR(80) > NURSE(60) > COORDINATOR(40) > READ_ONLY(20)

Inherited permissions: higher roles automatically inherit all permissions
of roles below them.
"""
from __future__ import annotations

import logging
from enum import IntEnum
from typing import Any, Callable

from fastapi import Depends, HTTPException, status

from app.models import User, UserRole
from app.security.auth import get_current_active_user

logger = logging.getLogger("healthbridge.security.rbac")


# ═══════════════════════════════════════════════════
# Role Hierarchy (integer weights)
# ═══════════════════════════════════════════════════

class RoleHierarchy(IntEnum):
    """Numerical weights for the role hierarchy.
    Higher weight = more privileges. Roles inherit the permissions
    of all roles with lower or equal weight.
    """
    READ_ONLY = 20
    COORDINATOR = 40
    NURSE = 60
    DOCTOR = 80
    ORG_ADMIN = 100
    SUPER_ADMIN = 120

    @classmethod
    def from_user_role(cls, role: UserRole) -> "RoleHierarchy":
        mapping = {
            UserRole.READ_ONLY: cls.READ_ONLY,
            UserRole.COORDINATOR: cls.COORDINATOR,
            UserRole.NURSE: cls.NURSE,
            UserRole.DOCTOR: cls.DOCTOR,
            UserRole.ORG_ADMIN: cls.ORG_ADMIN,
            UserRole.SUPER_ADMIN: cls.SUPER_ADMIN,
        }
        if role not in mapping:
            raise ValueError(f"Unknown role: {role}")
        return mapping[role]

    def __ge__(self, other: Any) -> bool:
        if isinstance(other, str):
            try:
                other = RoleHierarchy[other.upper()]
            except KeyError:
                return NotImplemented
        return super().__ge__(other)

    def __le__(self, other: Any) -> bool:
        if isinstance(other, str):
            try:
                other = RoleHierarchy[other.upper()]
            except KeyError:
                return NotImplemented
        return super().__le__(other)


# ═══════════════════════════════════════════════════
# Permission Matrix
# ═══════════════════════════════════════════════════
# Actions:
#   patient.read, patient.write, patient.export, patient.delete,
#   vital_sign.read, vital_sign.write,
#   consent.manage, audit.view, user.manage, system.admin,
#   clinical.soap.read, clinical.soap.write, clinical.icd10.search

_PERMISSION_MATRIX: dict[str, set[str]] = {
    "READ_ONLY": {"patient.read", "vital_sign.read", "clinical.icd10.search"},
    "COORDINATOR": {"patient.read", "patient.write", "vital_sign.read", "vital_sign.write", "consent.manage", "audit.view", "opd.register", "opd.queue.read", "clinical.icd10.search"},
    "NURSE": {"patient.read", "patient.write", "vital_sign.read", "vital_sign.write", "consent.manage", "audit.view", "opd.register", "opd.queue.read", "opd.queue.write", "clinical.icd10.search"},
    "DOCTOR": {"patient.read", "patient.write", "patient.export", "vital_sign.read", "vital_sign.write", "consent.manage", "audit.view", "opd.register", "opd.queue.read", "opd.queue.write", "clinical.soap.read", "clinical.soap.write", "clinical.icd10.search"},
    "ORG_ADMIN": {
        "patient.read", "patient.write", "patient.export", "patient.delete",
        "vital_sign.read", "vital_sign.write",
        "consent.manage", "audit.view", "user.manage", "system.admin",
        "opd.register", "opd.queue.read", "opd.queue.write", "opd.register.read",
        "clinical.soap.read", "clinical.soap.write", "clinical.icd10.search",
    },
    "SUPER_ADMIN": {
        "patient.read", "patient.write", "patient.export", "patient.delete",
        "vital_sign.read", "vital_sign.write",
        "consent.manage", "audit.view", "user.manage", "system.admin",
        "opd.register", "opd.queue.read", "opd.queue.write", "opd.register.read",
        "clinical.soap.read", "clinical.soap.write", "clinical.icd10.search",
    },
}

# ── Build inherited permission sets ──
_ROLE_FULL_PERMISSIONS: dict[str, set[str]] = {}
_hierarchy_order = sorted(RoleHierarchy, key=lambda x: x.value)

for role_enum in _hierarchy_order:
    role_name = role_enum.name
    own = _PERMISSION_MATRIX.get(role_name, set())
    inherited: set[str] = set()
    for lower_enum in _hierarchy_order:
        if lower_enum.value < role_enum.value:
            inherited |= _PERMISSION_MATRIX.get(lower_enum.name, set())
    _ROLE_FULL_PERMISSIONS[role_name] = own | inherited


# ═══════════════════════════════════════════════════
# Permission Check
# ═══════════════════════════════════════════════════

def check_permission(user_role: UserRole, action: str) -> bool:
    """Check whether a user role is permitted to perform an action.
    Respects role inheritance.
    """
    role_name = user_role.name if isinstance(user_role, UserRole) else str(user_role)
    permissions = _ROLE_FULL_PERMISSIONS.get(role_name, set())
    return action in permissions


# ═══════════════════════════════════════════════════
# FastAPI Dependencies
# ═══════════════════════════════════════════════════

def require_role(minimum_role: UserRole) -> Callable:
    """FastAPI dependency factory — require a minimum role hierarchy level."""
    minimum_weight = RoleHierarchy.from_user_role(minimum_role).value

    async def _role_checker(
        current_user: User = Depends(get_current_active_user),
    ) -> User:
        user_weight = RoleHierarchy.from_user_role(current_user.role).value
        if user_weight < minimum_weight:
            logger.warning(
                f"User {current_user.id} ({current_user.role}) denied access — "
                f"requires at least {minimum_role}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient role. Required: {minimum_role.value} "
                       f"or higher. Your role: {current_user.role.value}.",
            )
        return current_user

    return _role_checker


def require_permission(action: str) -> Callable:
    """FastAPI dependency factory — require a specific action permission."""

    async def _permission_checker(
        current_user: User = Depends(get_current_active_user),
    ) -> User:
        if not check_permission(current_user.role, action):
            logger.warning(
                f"User {current_user.id} ({current_user.role}) denied action '{action}'"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied. Action '{action}' requires a role with "
                       f"the '{action}' permission. Your role: {current_user.role.value}.",
            )
        return current_user

    return _permission_checker
