"""HealthBridge Platform — Organization (Tenant) API Routes

Multi-tenant signup, onboarding, staff management, and subscription.
"""
from __future__ import annotations

import logging
import re
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field

from app.database import get_db, AsyncSession
from app.config import settings
from app.security.auth import (
    create_access_token, create_refresh_token, hash_password,
    get_current_active_user
)
from app.security.tenant import get_current_tenant, require_org_admin, require_super_admin
from app.security.audit import log_action
from app.models import (
    Organization, User, UserRole, SubscriptionTier, Patient,
    AuditAction
)

logger = logging.getLogger("healthbridge.api.organizations")
router = APIRouter(prefix="/api/v1/organizations", tags=["Organizations"])


# ── Schemas ──

class OrgRegisterRequest(BaseModel):
    """Step 1: Clinic signs up with org details + admin user."""
    organization_name: str = Field(..., min_length=2, max_length=255)
    organization_email: Optional[EmailStr] = None
    organization_phone: Optional[str] = None
    address: Optional[str] = None
    registration_number: Optional[str] = None

    admin_email: EmailStr
    admin_password: str = Field(..., min_length=8)
    admin_full_name: str = Field(..., min_length=1, max_length=255)


class OrgRegisterResponse(BaseModel):
    org_id: str
    org_name: str
    org_slug: str
    user_id: str
    user_email: str
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    message: str


class OrgResponse(BaseModel):
    id: str
    name: str
    slug: str
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    registration_number: Optional[str] = None
    subscription_tier: str
    is_active: bool
    onboarding_completed: bool
    max_staff: int
    max_patients: int
    staff_count: int = 0
    patient_count: int = 0
    created_at: str


class OrgUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=255)
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    registration_number: Optional[str] = None


class StaffMemberResponse(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    is_active: bool
    last_login: Optional[str] = None
    created_at: str


class InviteStaffRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(..., min_length=1, max_length=255)
    role: UserRole = UserRole.READ_ONLY


# ── Helpers ──

def _generate_slug(name: str) -> str:
    """Generate a URL-safe slug from organization name."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s-]+", "-", slug)
    slug = slug.strip("-")[:64]
    if not slug:
        slug = "clinic"
    return slug


# ═══════════════════════════════════════════════════
# Routes
# ═══════════════════════════════════════════════════

@router.post("/register", response_model=OrgRegisterResponse, status_code=201)
async def register_organization(
    request: OrgRegisterRequest,
    req: Request,
    db: AsyncSession = Depends(get_db),
):
    """Register a new clinic/hospital + create admin user in one step.

    This is the primary SaaS signup flow:
    1. Creates the Organization (tenant)
    2. Creates the admin User scoped to that tenant
    3. Returns JWT tokens so they're logged in immediately
    """
    from sqlalchemy import select, func

    # Check if admin email already exists
    existing = await db.execute(select(User).where(User.email == request.admin_email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    # Check org email uniqueness
    if request.organization_email:
        org_check = await db.execute(
            select(Organization).where(Organization.email == request.organization_email)
        )
        if org_check.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Organization email already registered")

    # Generate unique slug
    base_slug = _generate_slug(request.organization_name)
    slug = base_slug
    counter = 1
    while True:
        slug_check = await db.execute(select(Organization).where(Organization.slug == slug))
        if not slug_check.scalar_one_or_none():
            break
        slug = f"{base_slug}-{counter}"
        counter += 1

    # Create organization
    org = Organization(
        name=request.organization_name,
        slug=slug,
        address=request.address,
        phone=request.organization_phone,
        email=request.organization_email,
        registration_number=request.registration_number,
        subscription_tier=SubscriptionTier.FREE,
        max_staff=5,
        max_patients=100,
        is_active=True,
    )
    db.add(org)
    await db.flush()

    # Create admin user
    admin = User(
        email=request.admin_email,
        password_hash=hash_password(request.admin_password),
        full_name=request.admin_full_name,
        role=UserRole.ORG_ADMIN,
        tenant_id=org.id,
        is_active=True,
    )
    db.add(admin)
    await db.flush()

    # Generate JWT tokens with tenant_id
    access_expires = timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(data={
        "sub": admin.email,
        "user_id": admin.id,
        "role": admin.role.value,
        "tenant_id": org.id,
    }, expires_delta=access_expires)
    refresh_token = create_refresh_token(data={"sub": admin.email, "tenant_id": org.id})

    # Audit log
    await log_action(
        action=AuditAction.USER_CREATED,
        user_id=admin.id,
        ip_address=req.client.host if req.client else None,
        description=f"Organization '{org.name}' registered by {admin.email}",
        db=db,
    )

    return OrgRegisterResponse(
        org_id=org.id,
        org_name=org.name,
        org_slug=org.slug,
        user_id=admin.id,
        user_email=admin.email,
        access_token=access_token,
        refresh_token=refresh_token,
        message="Organization created successfully. Welcome to HealthBridge!",
    )


@router.get("/me", response_model=OrgResponse)
async def get_my_organization(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the current user's organization details."""
    from sqlalchemy import select, func

    org = await db.execute(select(Organization).where(Organization.id == current_user.tenant_id))
    org = org.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    # Count staff and patients
    staff_count_result = await db.execute(
        select(func.count(User.id)).where(User.tenant_id == org.id)
    )
    patient_count_result = await db.execute(
        select(func.count(Patient.id)).where(Patient.tenant_id == org.id)
    )

    return OrgResponse(
        id=org.id,
        name=org.name,
        slug=org.slug,
        address=org.address,
        phone=org.phone,
        email=org.email,
        registration_number=org.registration_number,
        subscription_tier=org.subscription_tier.value,
        is_active=org.is_active,
        onboarding_completed=org.onboarding_completed,
        max_staff=org.max_staff,
        max_patients=org.max_patients,
        staff_count=staff_count_result.scalar() or 0,
        patient_count=patient_count_result.scalar() or 0,
        created_at=org.created_at.isoformat() if org.created_at else "",
    )


@router.put("/me", response_model=OrgResponse)
async def update_my_organization(
    request: OrgUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Update organization details (org admin only)."""
    if current_user.role not in (UserRole.ORG_ADMIN, UserRole.SUPER_ADMIN):
        raise HTTPException(status_code=403, detail="Organization admin privileges required")

    from sqlalchemy import select, func
    org = await db.execute(select(Organization).where(Organization.id == current_user.tenant_id))
    org = org.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    if request.name is not None:
        org.name = request.name
    if request.address is not None:
        org.address = request.address
    if request.phone is not None:
        org.phone = request.phone
    if request.email is not None:
        org.email = request.email
    if request.registration_number is not None:
        org.registration_number = request.registration_number

    await db.flush()

    # Count staff and patients
    staff_count_result = await db.execute(
        select(func.count(User.id)).where(User.tenant_id == org.id)
    )
    patient_count_result = await db.execute(
        select(func.count(Patient.id)).where(Patient.tenant_id == org.id)
    )

    return OrgResponse(
        id=org.id,
        name=org.name,
        slug=org.slug,
        address=org.address,
        phone=org.phone,
        email=org.email,
        registration_number=org.registration_number,
        subscription_tier=org.subscription_tier.value,
        is_active=org.is_active,
        onboarding_completed=org.onboarding_completed,
        max_staff=org.max_staff,
        max_patients=org.max_patients,
        staff_count=staff_count_result.scalar() or 0,
        patient_count=patient_count_result.scalar() or 0,
        created_at=org.created_at.isoformat() if org.created_at else "",
    )


@router.get("/me/staff", response_model=list[StaffMemberResponse])
async def list_staff(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """List all staff members in the organization."""
    from sqlalchemy import select
    result = await db.execute(
        select(User).where(User.tenant_id == current_user.tenant_id)
        .order_by(User.created_at)
    )
    staff = result.scalars().all()

    return [
        StaffMemberResponse(
            id=u.id,
            email=u.email,
            full_name=u.full_name,
            role=u.role.value,
            is_active=u.is_active,
            last_login=u.last_login.isoformat() if u.last_login else None,
            created_at=u.created_at.isoformat() if u.created_at else "",
        )
        for u in staff
    ]


@router.post("/me/invite", status_code=201)
async def invite_staff(
    request: InviteStaffRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Invite a new staff member to the organization (admin only)."""
    if current_user.role not in (UserRole.ORG_ADMIN, UserRole.SUPER_ADMIN):
        raise HTTPException(status_code=403, detail="Organization admin privileges required")

    from sqlalchemy import select, func

    # Check email uniqueness
    existing = await db.execute(select(User).where(User.email == request.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    # Check staff limit
    count_result = await db.execute(
        select(func.count(User.id)).where(User.tenant_id == current_user.tenant_id)
    )
    staff_count = count_result.scalar()

    org = await db.execute(select(Organization).where(Organization.id == current_user.tenant_id))
    org = org.scalar_one_or_none()
    if org and staff_count >= org.max_staff:
        raise HTTPException(
            status_code=402,
            detail=f"Staff limit ({org.max_staff}) reached. Upgrade your plan to add more staff.",
        )

    # Create user with a temporary password (should trigger password reset)
    import secrets
    temp_password = secrets.token_urlsafe(12)

    new_user = User(
        email=request.email,
        password_hash=hash_password(temp_password),
        full_name=request.full_name,
        role=request.role,
        tenant_id=current_user.tenant_id,
        is_active=True,
    )
    db.add(new_user)
    await db.flush()

    # TODO: Send invitation email with temp password

    return {
        "id": new_user.id,
        "email": new_user.email,
        "full_name": new_user.full_name,
        "role": new_user.role.value,
        "temporary_password": temp_password,
        "message": "Staff member added. Share the temporary password securely.",
    }


@router.put("/me/staff/{user_id}/deactivate")
async def deactivate_staff(
    user_id: str,
    current_user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_db),
):
    """Deactivate a staff member."""
    from sqlalchemy import select
    result = await db.execute(
        select(User).where(User.id == user_id, User.tenant_id == current_user.tenant_id)
    )
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Staff member not found")

    target.is_active = False
    await db.flush()
    return {"message": f"User {target.email} deactivated"}


# ── Super Admin Routes ──

@router.get("")
async def list_all_organizations(
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all organizations (super admin only)."""
    from sqlalchemy import select
    result = await db.execute(select(Organization).order_by(Organization.created_at.desc()))
    orgs = result.scalars().all()
    return [
        {
            "id": o.id,
            "name": o.name,
            "slug": o.slug,
            "tier": o.subscription_tier.value,
            "is_active": o.is_active,
            "staff_count": 0,
            "created_at": o.created_at.isoformat() if o.created_at else "",
        }
        for o in orgs
    ]


@router.put("/{org_id}/tier")
async def update_subscription_tier(
    org_id: str,
    tier: SubscriptionTier,
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update an organization's subscription tier (super admin only)."""
    from sqlalchemy import select
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    org.subscription_tier = tier
    # Update limits based on tier
    tier_limits = {
        SubscriptionTier.FREE: (5, 100),
        SubscriptionTier.STARTER: (15, 1000),
        SubscriptionTier.PROFESSIONAL: (50, 10000),
        SubscriptionTier.ENTERPRISE: (999, 999999),
    }
    org.max_staff, org.max_patients = tier_limits.get(tier, (5, 100))
    await db.flush()

    return {"message": f"Subscription updated to {tier.value}", "org_id": org_id}
