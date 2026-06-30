"""HealthBridge Platform — Authentication API Routes"""
from __future__ import annotations

from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, EmailStr

from app.database import get_db, AsyncSession
from app.config import settings
from app.security.auth import (
    authenticate_user, create_access_token, create_refresh_token,
    verify_refresh_token, get_current_active_user, hash_password
)
from app.security.audit import log_action
from app.models import User, UserRole, AuditAction

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


# ── Schemas ──

class LoginRequest(BaseModel):
    email: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict

class RefreshRequest(BaseModel):
    refresh_token: str

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


# ── Routes ──

@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, req: Request, db: AsyncSession = Depends(get_db)):
    """Authenticate user and return JWT tokens."""
    user = await authenticate_user(db, request.email, request.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_expires = timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email, "user_id": user.id, "role": user.role.value, "tenant_id": user.tenant_id},
        expires_delta=access_expires
    )
    refresh_token = create_refresh_token(data={"sub": user.email, "tenant_id": user.tenant_id})

    await log_action(
        action=AuditAction.LOGIN_SUCCESS,
        user_id=user.id,
        ip_address=req.client.host if req.client else None,
        user_agent=req.headers.get("user-agent"),
        description=f"User {user.email} logged in",
        db=db
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=int(access_expires.total_seconds()),
        user={
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role.value,
            "tenant_id": user.tenant_id,
        }
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(request: RefreshRequest, req: Request, db: AsyncSession = Depends(get_db)):
    """Refresh access token using refresh token."""
    payload = verify_refresh_token(request.refresh_token)
    email = payload.get("sub")

    from sqlalchemy import select
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    access_expires = timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    new_access = create_access_token(
        data={"sub": user.email, "user_id": user.id, "role": user.role.value, "tenant_id": user.tenant_id},
        expires_delta=access_expires
    )
    new_refresh = create_refresh_token(data={"sub": user.email, "tenant_id": user.tenant_id})

    return TokenResponse(
        access_token=new_access,
        refresh_token=new_refresh,
        expires_in=int(access_expires.total_seconds()),
        user={
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role.value,
        }
    )


@router.post("/register")
async def register(request: RegisterRequest, req: Request, db: AsyncSession = Depends(get_db)):
    """Register a new user.

    NOTE: New registrations default to READ_ONLY role.
    To create admin/doctor accounts, use the admin API (/api/v1/admin/users)
    after logging in with an existing admin account.
    """
    from sqlalchemy import select
    result = await db.execute(select(User).where(User.email == request.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        email=request.email,
        password_hash=hash_password(request.password),
        full_name=request.full_name,
        role=UserRole.READ_ONLY,
    )
    db.add(user)
    await db.flush()

    await log_action(
        action=AuditAction.USER_CREATED,
        user_id=user.id,
        ip_address=req.client.host if req.client else None,
        description=f"User registered: {request.email}",
        db=db
    )

    return {"id": user.id, "email": user.email, "full_name": user.full_name, "role": user.role.value}


@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Change current user's password."""
    from app.security.auth import verify_password
    if not verify_password(request.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    current_user.password_hash = hash_password(request.new_password)
    await db.flush()
    return {"message": "Password changed successfully"}


@router.post("/logout")
async def logout(current_user: User = Depends(get_current_active_user)):
    """Logout (client should discard tokens)."""
    return {"message": "Logged out successfully"}


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_active_user)):
    """Get current user profile."""
    return {
        "id": current_user.id,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "role": current_user.role.value,
        "tenant_id": current_user.tenant_id,
        "is_active": current_user.is_active,
        "last_login": current_user.last_login.isoformat() if current_user.last_login else None,
    }
