"""HealthBridge Platform — Security Layer

Re-exports all security functions for convenient access.
"""

__all__ = [
    "create_access_token", "create_refresh_token", "verify_token",
    "verify_refresh_token", "hash_password", "verify_password",
    "authenticate_user", "get_current_user", "get_current_active_user",
    "encrypt_field", "decrypt_field", "encrypt_json", "decrypt_json",
    "mask_field", "get_encryption_key",
    "require_role", "require_permission", "check_permission", "RoleHierarchy",
    "log_action", "get_patient_audit_trail", "get_user_audit_trail",
    "purge_audit_logs", "get_audit_log_context",
]

from app.security.auth import (
    create_access_token,
    create_refresh_token,
    verify_token,
    verify_refresh_token,
    hash_password,
    verify_password,
    authenticate_user,
    get_current_user,
    get_current_active_user,
)
from app.security.encryption import (
    encrypt_field,
    decrypt_field,
    encrypt_json,
    decrypt_json,
    mask_field,
    get_encryption_key,
)
from app.security.rbac import (
    require_role,
    require_permission,
    check_permission,
    RoleHierarchy,
)
from app.security.audit import (
    log_action,
    get_patient_audit_trail,
    get_user_audit_trail,
    purge_audit_logs,
    get_audit_log_context,
)
