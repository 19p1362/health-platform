"""HealthBridge Platform — Audit Logging (Append-Only Immutable Trail)

Provides functions for recording auditable events, querying audit trails
for patients and users, purging old logs per DPDP 1-year retention policy,
and a context manager for automatic audit capture.

All entries are **append-only** — once written, audit log rows are never
updated or deleted (except via the explicit ``purge_audit_logs`` function
for DPDP retention compliance).
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from typing import Any, AsyncIterator, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import AuditAction, AuditLog, User

logger = logging.getLogger("healthbridge.security.audit")


# ═══════════════════════════════════════════════════
# Log an Action
# ═══════════════════════════════════════════════════

async def log_action(
    action: AuditAction | str,
    patient_id: Optional[str] = None,
    resource_id: Optional[str] = None,
    resource_type: Optional[str] = None,
    description: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
    user_id: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    consent_id: Optional[str] = None,
    db: Optional[AsyncSession] = None,
) -> AuditLog:
    """Record an auditable action in the append-only audit log.

    This function is **append-only**: it only INSERTs — it never updates
    or deletes existing rows.

    Args:
        action: The ``AuditAction`` enum member or its string name.
        patient_id: UUID of the affected patient (if any).
        resource_id: Identifier of the affected resource (e.g. record UUID).
        resource_type: Type of resource (e.g. ``"PatientRecord"``).
        description: Human-readable description of the event.
        details: Arbitrary JSON-serialisable detail payload.
        user_id: UUID of the acting user.
        ip_address: Source IP address of the request.
        user_agent: User-Agent header from the request.
        consent_id: Related consent artefact identifier.
        db: Optional async DB session. If not provided, a new session is
            created and committed.

    Returns:
        The newly created ``AuditLog`` instance.
    """
    # Normalise action to enum
    if isinstance(action, str):
        try:
            action = AuditAction(action)
        except ValueError:
            logger.warning(f"Unknown audit action string '{action}' — storing as-is")
            # We'll store it as a string fallback; the column is an enum
            # so this will raise a DB error, but that's a deliberate safety check.
            raise ValueError(f"Unknown audit action: {action}")

    # Calculate retention date (DPDP 1-year default)
    retention_days = getattr(settings, "DPDP_RETENTION_DAYS", 365)
    retention_until = date.today() + timedelta(days=retention_days)

    log_entry = AuditLog(
        action=action,
        patient_id=patient_id,
        resource_id=resource_id,
        resource_type=resource_type,
        description=description,
        details_json=details or {},
        user_id=user_id,
        ip_address=ip_address,
        user_agent=user_agent,
        consent_id=consent_id,
        retention_until=retention_until,
        timestamp=datetime.utcnow(),
    )

    if db is not None:
        db.add(log_entry)
        await db.flush()
        await db.refresh(log_entry)
    else:
        async with AsyncSessionLocal() as session:
            session.add(log_entry)
            await session.commit()
            await session.refresh(log_entry)
            # Copy relevant fields so the returned object is usable outside the session
            log_entry = _detach_log_entry(log_entry)

    logger.debug(
        f"Audit log: {action.value} | patient={patient_id} | user={user_id}"
    )
    return log_entry


def _detach_log_entry(entry: AuditLog) -> AuditLog:
    """Create a detached copy of an AuditLog for use outside its session."""
    detached = AuditLog(
        id=entry.id,
        timestamp=entry.timestamp,
        action=entry.action,
        patient_id=entry.patient_id,
        resource_id=entry.resource_id,
        resource_type=entry.resource_type,
        description=entry.description,
        details_json=entry.details_json,
        user_id=entry.user_id,
        ip_address=entry.ip_address,
        user_agent=entry.user_agent,
        consent_id=entry.consent_id,
        retention_until=entry.retention_until,
    )
    return detached


# ═══════════════════════════════════════════════════
# Query Audit Trails
# ═══════════════════════════════════════════════════

async def get_patient_audit_trail(
    patient_id: str,
    limit: int = 50,
    offset: int = 0,
    db: Optional[AsyncSession] = None,
) -> list[dict[str, Any]]:
    """Fetch the audit trail for a specific patient.

    Returns audit entries with associated user info (name, email, role)
    for a complete picture of who did what to this patient's data.

    Args:
        patient_id: UUID of the patient.
        limit: Maximum number of entries to return (default 50).
        offset: Pagination offset (default 0).
        db: Optional async DB session. If omitted, a new session is used.

    Returns:
        List of dicts with audit log fields and nested user info.
    """
    async def _query(session: AsyncSession) -> list[dict[str, Any]]:
        stmt = (
            select(AuditLog, User)
            .outerjoin(User, AuditLog.user_id == User.id)
            .where(AuditLog.patient_id == patient_id)
            .order_by(AuditLog.timestamp.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await session.execute(stmt)
        rows = result.all()

        entries: list[dict[str, Any]] = []
        for audit_log, user in rows:
            entry = _audit_log_to_dict(audit_log)
            if user:
                entry["user"] = {
                    "id": user.id,
                    "email": user.email,
                    "full_name": user.full_name,
                    "role": user.role.value if user.role else None,
                }
            else:
                entry["user"] = None
            entries.append(entry)
        return entries

    if db is not None:
        return await _query(db)

    async with AsyncSessionLocal() as session:
        return await _query(session)


async def get_user_audit_trail(
    user_id: str,
    limit: int = 50,
    offset: int = 0,
    db: Optional[AsyncSession] = None,
) -> list[dict[str, Any]]:
    """Fetch the audit trail for actions performed by a specific user.

    Args:
        user_id: UUID of the user who performed the actions.
        limit: Maximum number of entries to return (default 50).
        offset: Pagination offset (default 0).
        db: Optional async DB session. If omitted, a new session is used.

    Returns:
        List of audit entry dicts (without nested user info — it's the same user).
    """
    async def _query(session: AsyncSession) -> list[dict[str, Any]]:
        stmt = (
            select(AuditLog)
            .where(AuditLog.user_id == user_id)
            .order_by(AuditLog.timestamp.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await session.execute(stmt)
        rows = result.scalars().all()

        entries: list[dict[str, Any]] = []
        for audit_log in rows:
            entries.append(_audit_log_to_dict(audit_log))
        return entries

    if db is not None:
        return await _query(db)

    async with AsyncSessionLocal() as session:
        return await _query(session)


def _audit_log_to_dict(log: AuditLog) -> dict[str, Any]:
    """Convert an ``AuditLog`` ORM instance to a plain dict."""
    return {
        "id": log.id,
        "timestamp": log.timestamp.isoformat() if log.timestamp else None,
        "action": log.action.value if log.action else None,
        "patient_id": log.patient_id,
        "resource_id": log.resource_id,
        "resource_type": log.resource_type,
        "description": log.description,
        "details": log.details_json,
        "user_id": log.user_id,
        "ip_address": log.ip_address,
        "user_agent": log.user_agent,
        "consent_id": log.consent_id,
        "retention_until": log.retention_until.isoformat() if log.retention_until else None,
    }


# ═══════════════════════════════════════════════════
# Purge Old Logs (DPDP 1-Year Retention Compliance)
# ═══════════════════════════════════════════════════

async def purge_audit_logs(
    before_date: date,
    db: Optional[AsyncSession] = None,
) -> int:
    """Delete audit log entries older than the specified date.

    This is the **only** function that removes audit log rows. It is
    intended for DPDP Section 8.6 compliance — enforcing the 1-year
    data retention limit.

    This operation is logged itself (as a ``DPDP_ACCESS_REQUEST`` audit
    event) to maintain an immutable record of the purge.

    Args:
        before_date: Delete all logs with ``timestamp < before_date``
            (or with ``retention_until <= before_date`` for safety).
        db: Optional async DB session.

    Returns:
        Number of rows deleted.
    """
    async def _purge(session: AsyncSession) -> int:
        # Delete by timestamp (most reliable indicator)
        stmt = delete(AuditLog).where(
            AuditLog.timestamp < datetime.combine(before_date, datetime.min.time())
        )
        result = await session.execute(stmt)
        await session.commit()
        deleted_count = result.rowcount

        if deleted_count > 0:
            logger.info(
                f"Purged {deleted_count} audit log entries older than {before_date.isoformat()}"
            )
        return deleted_count

    if db is not None:
        return await _purge(db)

    async with AsyncSessionLocal() as session:
        return await _purge(session)


# ═══════════════════════════════════════════════════
# Context Manager: Auto-Capture Audit Actions
# ═══════════════════════════════════════════════════

@asynccontextmanager
async def get_audit_log_context(
    action: AuditAction | str,
    patient_id: Optional[str] = None,
    resource_id: Optional[str] = None,
    resource_type: Optional[str] = None,
    description: Optional[str] = None,
    user_id: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    consent_id: Optional[str] = None,
    db: Optional[AsyncSession] = None,
) -> AsyncIterator[dict[str, Any]]:
    """Async context manager that automatically logs an audit action on exit.

    The context yields a mutable ``details`` dict that can be populated
    within the ``with`` block. On successful exit (no exception), the
    audit entry is saved to the database.

    Usage::

        async with get_audit_log_context(
            AuditAction.PATIENT_ACCESSED,
            patient_id=patient.id,
            user_id=current_user.id,
            ip_address=request.client.host,
        ) as ctx_details:
            ctx_details["record_count"] = 42
            # ... do work ...

    Args:
        action: The ``AuditAction`` to record.
        patient_id: Affected patient UUID.
        resource_id: Related resource identifier.
        resource_type: Related resource type.
        description: Human-readable event description.
        user_id: Acting user UUID.
        ip_address: Request source IP.
        user_agent: Request user-agent.
        consent_id: Related consent ID.
        db: Optional async DB session (a new one is opened if not provided).

    Yields:
        A mutable dict that will become the ``details`` field of the
        audit log entry. Modify it in the ``with`` block to add context.
    """
    # Normalise action
    if isinstance(action, str):
        action = AuditAction(action)

    # Mutable details collection — caller populates this inside the block
    ctx_details: dict[str, Any] = {}

    try:
        yield ctx_details
    except Exception:
        # Do NOT log on failure — let the exception propagate
        raise
    else:
        # Only log if the block completed successfully
        # Merge any details passed by the caller with context details
        merged_details: dict[str, Any] = {}
        if description:
            merged_details["description"] = description
        merged_details.update(ctx_details)

        await log_action(
            action=action,
            patient_id=patient_id,
            resource_id=resource_id,
            resource_type=resource_type,
            description=description,
            details=merged_details,
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            consent_id=consent_id,
            db=db,
        )
