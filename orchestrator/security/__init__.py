"""security — Layer 7: Authentication, RBAC, and Encryption.

Modules:
    auth       — JWT token creation/verification + bcrypt password hashing
    roles      — Role-Based Access Control (admin, doctor, nurse, coordinator)
    encryption — Fernet symmetric encryption + SHA-256 hashing + PII masking
"""

from .auth import (
    create_access_token,
    verify_token,
    hash_password,
    verify_password,
    authenticate_user,
    get_current_user,
)
from .roles import (
    Role,
    Permission,
    role_permissions,
    has_permission,
    require_role,
    require_permission,
)
from .encryption import (
    encrypt_field,
    decrypt_field,
    encrypt_json,
    decrypt_json,
    mask_field,
    hash_value,
    generate_encryption_key,
)

__all__ = [
    # auth
    "create_access_token",
    "verify_token",
    "hash_password",
    "verify_password",
    "authenticate_user",
    "get_current_user",
    # roles
    "Role",
    "Permission",
    "role_permissions",
    "has_permission",
    "require_role",
    "require_permission",
    # encryption
    "encrypt_field",
    "decrypt_field",
    "encrypt_json",
    "decrypt_json",
    "mask_field",
    "hash_value",
    "generate_encryption_key",
]
