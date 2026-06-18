"""roles — Role-Based Access Control (RBAC).

Defines the 5 user roles, a granular permission matrix, and helper
decorators / functions for enforcing access in route handlers.

Hierarchy (higher → lower):
    ADMIN (100)     — system administration, all permissions
    DOCTOR (80)     — clinical read/write, patient export
    NURSE (60)      — clinical read/write, limited export
    COORDINATOR (40) — operational read/write, communication
    READ_ONLY (20)  — view-only access
"""

import enum
import functools
import logging
from typing import Callable, Optional, Sequence, Set

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Role enumeration with integer weight (higher = more privileged)
# ---------------------------------------------------------------------------

class Role(enum.IntEnum):
    """User roles ordered by privilege level."""

    READ_ONLY = 20
    COORDINATOR = 40
    NURSE = 60
    DOCTOR = 80
    ADMIN = 100

    @classmethod
    def from_str(cls, name: str) -> "Role":
        """Case-insensitive lookup, e.g. ``Role.from_str('admin')`` → ``Role.ADMIN``."""
        try:
            return cls[name.upper()]
        except KeyError:
            raise ValueError(f"Unknown role: {name!r}. Valid: {[r.name.lower() for r in cls]}")


# ---------------------------------------------------------------------------
# Permission identifiers
# ---------------------------------------------------------------------------

class Permission(str, enum.Enum):
    """Granular action-based permissions.

    Naming convention: ``<domain>.<action>``.
    """

    # Patient data
    PATIENT_READ = "patient.read"
    PATIENT_WRITE = "patient.write"
    PATIENT_EXPORT = "patient.export"
    PATIENT_DELETE = "patient.delete"

    # Consent management (DPDP compliance)
    CONSENT_MANAGE = "consent.manage"

    # Audit & compliance
    AUDIT_VIEW = "audit.view"

    # User administration
    USER_MANAGE = "user.manage"

    # System-level
    SYSTEM_ADMIN = "system.admin"


# ---------------------------------------------------------------------------
# Permission matrix
# Each role maps to the set of permissions it grants.
# Higher roles inherit all permissions from lower roles.
# ---------------------------------------------------------------------------

_ROLE_BASE: dict[Role, set[Permission]] = {
    Role.READ_ONLY: {
        Permission.PATIENT_READ,
        Permission.AUDIT_VIEW,
    },
    Role.COORDINATOR: {
        Permission.PATIENT_READ,
        Permission.PATIENT_WRITE,
        Permission.AUDIT_VIEW,
    },
    Role.NURSE: {
        Permission.PATIENT_READ,
        Permission.PATIENT_WRITE,
        Permission.PATIENT_EXPORT,
        Permission.AUDIT_VIEW,
    },
    Role.DOCTOR: {
        Permission.PATIENT_READ,
        Permission.PATIENT_WRITE,
        Permission.PATIENT_EXPORT,
        Permission.AUDIT_VIEW,
        Permission.CONSENT_MANAGE,
    },
    Role.ADMIN: {
        Permission.PATIENT_READ,
        Permission.PATIENT_WRITE,
        Permission.PATIENT_EXPORT,
        Permission.PATIENT_DELETE,
        Permission.CONSENT_MANAGE,
        Permission.AUDIT_VIEW,
        Permission.USER_MANAGE,
        Permission.SYSTEM_ADMIN,
    },
}


def _build_role_permissions() -> dict[Role, set[Permission]]:
    """Compute the effective permission set for each role via inheritance.

    A role inherits permissions from all roles with a lower (or equal) weight.
    """
    sorted_roles = sorted(Role, key=lambda r: r.value)
    result: dict[Role, set[Permission]] = {}
    cumulative: set[Permission] = set()

    for role in sorted_roles:
        cumulative |= _ROLE_BASE.get(role, set())
        result[role] = frozenset(cumulative)  # immutable after construction

    return result


role_permissions: dict[Role, frozenset[Permission]] = _build_role_permissions()
"""Effective permissions per role after inheritance."""


# ---------------------------------------------------------------------------
# Permission helpers
# ---------------------------------------------------------------------------

def has_permission(user_role: Role, permission: Permission) -> bool:
    """Check whether a role has a specific permission.

    Parameters
    ----------
    user_role : Role
        The user's role.
    permission : Permission
        The permission to check.

    Returns
    -------
    bool
    """
    return permission in role_permissions.get(user_role, frozenset())


def has_any_permission(user_role: Role, permissions: Sequence[Permission]) -> bool:
    """Check whether a role has at least one of the given permissions."""
    perms = role_permissions.get(user_role, frozenset())
    return any(p in perms for p in permissions)


def has_all_permissions(user_role: Role, permissions: Sequence[Permission]) -> bool:
    """Check whether a role has all of the given permissions."""
    perms = role_permissions.get(user_role, frozenset())
    return all(p in perms for p in permissions)


# ---------------------------------------------------------------------------
# Decorator-based enforcement (for Flask route handlers)
# ---------------------------------------------------------------------------

def require_role(min_role: Role) -> Callable:
    """Decorator that checks the caller has at least *min_role* weight.

    Usage::

        @app.route("/admin/panel")
        @require_role(Role.ADMIN)
        def admin_panel(current_user):
            ...

    The wrapped handler MUST accept a ``current_user`` keyword argument
    (a dict with ``role`` key) provided by the auth middleware.

    Returns a 403 JSON response on failure.
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, current_user: Optional[dict] = None, **kwargs):
            from flask import jsonify  # lazy import to keep module load fast

            if current_user is None:
                return jsonify({"detail": "Authentication required"}), 401

            user_role_str = current_user.get("role", "read_only")
            try:
                user_role = Role.from_str(user_role_str)
            except ValueError:
                logger.warning("Unknown role %r in token", user_role_str)
                return jsonify({"detail": "Invalid role in token"}), 403

            if user_role.value < min_role.value:
                logger.info(
                    "Access denied: role %s < required %s",
                    user_role.name,
                    min_role.name,
                )
                return jsonify({"detail": "Insufficient permissions"}), 403

            return func(*args, current_user=current_user, **kwargs)

        return wrapper

    return decorator


def require_permission(permission: Permission) -> Callable:
    """Decorator that checks the caller has a specific permission.

    Usage::

        @app.route("/patients/<id>/export")
        @require_permission(Permission.PATIENT_EXPORT)
        def export_patient(current_user, patient_id):
            ...
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, current_user: Optional[dict] = None, **kwargs):
            from flask import jsonify

            if current_user is None:
                return jsonify({"detail": "Authentication required"}), 401

            user_role_str = current_user.get("role", "read_only")
            try:
                user_role = Role.from_str(user_role_str)
            except ValueError:
                return jsonify({"detail": "Invalid role in token"}), 403

            if not has_permission(user_role, permission):
                logger.info(
                    "Access denied: role %s lacks permission %s",
                    user_role.name,
                    permission.value,
                )
                return jsonify({"detail": "Insufficient permissions"}), 403

            return func(*args, current_user=current_user, **kwargs)

        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# Lookup helper (for route-level checks without decorator)
# ---------------------------------------------------------------------------

def check_access(
    user_role: Role,
    required_role: Optional[Role] = None,
    required_permission: Optional[Permission] = None,
) -> bool:
    """Inline permission check — useful for conditional logic in handlers.

    Parameters
    ----------
    user_role : Role
    required_role : Role, optional
        Minimum role weight required.
    required_permission : Permission, optional
        Specific permission required.

    Returns
    -------
    bool
    """
    if required_role and user_role.value < required_role.value:
        return False
    if required_permission and not has_permission(user_role, required_permission):
        return False
    return True


# ---------------------------------------------------------------------------
# Quick list helpers
# ---------------------------------------------------------------------------

def permissions_for(role: Role) -> Set[Permission]:
    """Return the set of permissions granted to *role*."""
    return set(role_permissions.get(role, frozenset()))


def roles_with_permission(permission: Permission) -> Sequence[Role]:
    """Return all roles that have a given permission."""
    return [r for r in Role if has_permission(r, permission)]
