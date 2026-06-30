"""HealthBridge Platform — EHR Connector Management API Routes

Provides CRUD operations for external EHR connector configurations,
connection testing, and sync triggering.  Connectors are persisted
in-memory (dict by connector ID).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.connectors import (
    ABDMConnector,
    BaseEHRConnector,
    FHIRStandardConnector,
    OpenMRSConnector,
)
from app.database import get_db, AsyncSession
from app.security.audit import log_action
from app.security.rbac import require_permission

logger = logging.getLogger("healthbridge.connectors.api")

router = APIRouter(prefix="/api/v1/connectors", tags=["EHR Connectors"])

# ── In-memory connector store ──
_CONNECTORS: dict[str, dict[str, Any]] = {}

# ── Supported connector types ──
SUPPORTED_CONNECTOR_TYPES = {
    "abdm": {
        "name": "ABDM (Ayushman Bharat Digital Mission)",
        "description": "India's national digital health ecosystem connector using ABHA numbers.",
        "config_schema": {
            "type": "object",
            "properties": {
                "abha_api_base_url": {
                    "type": "string",
                    "description": "ABDM API base URL (defaults to sandbox).",
                },
            },
        },
    },
    "openmrs": {
        "name": "OpenMRS",
        "description": "Open-source medical record system connector.",
        "config_schema": {
            "type": "object",
            "properties": {
                "base_url": {"type": "string", "description": "OpenMRS server base URL."},
                "username": {"type": "string", "description": "API username."},
                "password": {"type": "string", "description": "API password."},
            },
            "required": ["base_url"],
        },
    },
    "fhir": {
        "name": "FHIR R4",
        "description": "Generic FHIR R4 compliant server connector.",
        "config_schema": {
            "type": "object",
            "properties": {
                "fhir_base_url": {"type": "string", "description": "FHIR server base URL."},
                "auth_token": {"type": "string", "description": "Bearer token (optional)."},
            },
            "required": ["fhir_base_url"],
        },
    },
}


# ═══════════════════════════════════════════════════
# Schemas
# ═══════════════════════════════════════════════════


class RegisterConnectorRequest(BaseModel):
    """Request body to register a new EHR connector."""

    type: str  # abdm, openmrs, fhir
    name: str
    config: dict[str, Any] = {}


class ConnectorResponse(BaseModel):
    """Response model for a connector."""

    id: str
    type: str
    name: str
    connected: bool
    last_sync: Optional[str] = None
    error_count: int = 0
    last_error: Optional[str] = None
    created_at: str
    config: dict[str, Any] = {}


# ═══════════════════════════════════════════════════
# Helper
# ═══════════════════════════════════════════════════


def _create_connector_instance(
    connector_type: str, config: dict[str, Any]
) -> BaseEHRConnector:
    """Factory: create a connector instance from type string and config."""
    mapping = {
        "abdm": ABDMConnector,
        "openmrs": OpenMRSConnector,
        "fhir": FHIRStandardConnector,
    }
    cls = mapping.get(connector_type)
    if cls is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported connector type '{connector_type}'. "
            f"Supported: {', '.join(SUPPORTED_CONNECTOR_TYPES.keys())}",
        )
    return cls(config=config)


def _connector_to_dict(
    connector_id: str,
    connector_type: str,
    name: str,
    config: dict[str, Any],
    instance: BaseEHRConnector,
    created_at: str,
) -> dict[str, Any]:
    """Serialize a connector entry to a dict."""
    return {
        "id": connector_id,
        "type": connector_type,
        "name": name,
        "connected": instance.status.connected,
        "last_sync": instance.status.last_sync.isoformat() if instance.status.last_sync else None,
        "error_count": instance.status.error_count,
        "last_error": instance.status.last_error,
        "created_at": created_at,
        "config": config,
    }


# ═══════════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════════


@router.get("/types")
async def list_connector_types():
    """List all supported EHR connector types with their schemas.

    This endpoint is **public** — no authentication required.
    """
    return SUPPORTED_CONNECTOR_TYPES


@router.get("")
async def list_connectors(
    current_user=Depends(require_permission("patient.view")),
):
    """List all registered connectors."""
    return {
        "connectors": list(_CONNECTORS.values()),
        "count": len(_CONNECTORS),
    }


@router.post("", status_code=201)
async def register_connector(
    request: Request,
    body: RegisterConnectorRequest,
    current_user=Depends(require_permission("system.admin")),
):
    """Register a new EHR connector.

    The connector is created with its configuration and stored in memory.
    Use the ``/test`` endpoint to verify connectivity after registration.
    """
    connector_type = body.type.lower()

    if connector_type not in SUPPORTED_CONNECTOR_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported connector type '{connector_type}'. "
            f"Supported: {', '.join(SUPPORTED_CONNECTOR_TYPES.keys())}",
        )

    connector_id = str(uuid.uuid4())
    created_at = datetime.utcnow().isoformat()

    instance = _create_connector_instance(connector_type, body.config)

    entry = _connector_to_dict(
        connector_id=connector_id,
        connector_type=connector_type,
        name=body.name,
        config=body.config,
        instance=instance,
        created_at=created_at,
    )
    entry["_instance"] = instance  # Store the instance for operations

    _CONNECTORS[connector_id] = entry

    logger.info(
        f"Connector registered: {connector_id} ({connector_type}) by user {current_user.id}"
    )

    return {
        "id": connector_id,
        "type": connector_type,
        "name": body.name,
        "message": f"Connector '{body.name}' registered successfully",
        "created_at": created_at,
    }


@router.post("/{connector_id}/test")
async def test_connector(
    request: Request,
    connector_id: str,
    current_user=Depends(require_permission("system.admin")),
):
    """Test the connection to an external EHR system."""
    entry = _CONNECTORS.get(connector_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Connector not found")

    instance: BaseEHRConnector = entry["_instance"]

    try:
        # Ensure connected
        if not instance.status.connected:
            await instance.connect()

        result = await instance.test_connection()

        # Update stored status
        entry["connected"] = result.get("connected", False)
        if not result.get("connected"):
            entry["last_error"] = result.get("error", "Connection test failed")
            entry["error_count"] = instance.status.error_count

        logger.info(
            f"Connector test: {connector_id} -> connected={result.get('connected')} "
            f"latency={result.get('latency_ms')}ms"
        )

        return {
            "connector_id": connector_id,
            "connector_type": entry["type"],
            "test_result": result,
        }

    except Exception as exc:
        entry["connected"] = False
        entry["last_error"] = str(exc)
        entry["error_count"] = instance.status.error_count + 1

        logger.error(f"Connector test failed: {connector_id}: {exc}")
        raise HTTPException(
            status_code=502,
            detail=f"Connection test failed: {exc}",
        )


@router.post("/{connector_id}/sync")
async def sync_connector(
    request: Request,
    connector_id: str,
    current_user=Depends(require_permission("system.admin")),
    db: AsyncSession = Depends(get_db),
):
    """Trigger a sync operation that pulls patients and records from the external EHR."""
    entry = _CONNECTORS.get(connector_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Connector not found")

    instance: BaseEHRConnector = entry["_instance"]

    try:
        if not instance.status.connected:
            connected = await instance.connect()
            if not connected:
                raise HTTPException(
                    status_code=502,
                    detail=f"Could not connect to {entry['type']} connector. "
                    f"Last error: {instance.status.last_error}",
                )

        result = await instance.sync_patients()

        # Update sync timestamp
        instance.status.last_sync = datetime.utcnow()
        entry["last_sync"] = instance.status.last_sync.isoformat()

        # Audit log
        await log_action(
            action="DATA_INGESTED",
            description=f"Sync triggered for {entry['type']} connector '{entry['name']}'",
            user_id=current_user.id,
            ip_address=request.client.host if request.client else None,
            details={
                "connector_id": connector_id,
                "connector_type": entry["type"],
                "patients_pulled": result.get("patients_pulled", 0),
                "records_pulled": result.get("records_pulled", 0),
            },
            db=db,
        )

        return {
            "connector_id": connector_id,
            "connector_type": entry["type"],
            "sync_result": result,
            "message": f"Sync completed for '{entry['name']}'",
        }

    except HTTPException:
        raise
    except Exception as exc:
        entry["last_error"] = str(exc)
        entry["error_count"] = instance.status.error_count + 1
        logger.error(f"Connector sync failed: {connector_id}: {exc}")
        raise HTTPException(
            status_code=502,
            detail=f"Sync failed: {exc}",
        )


@router.delete("/{connector_id}")
async def remove_connector(
    request: Request,
    connector_id: str,
    current_user=Depends(require_permission("system.admin")),
    db: AsyncSession = Depends(get_db),
):
    """Remove a registered connector."""
    entry = _CONNECTORS.pop(connector_id, None)
    if not entry:
        raise HTTPException(status_code=404, detail="Connector not found")

    instance: BaseEHRConnector = entry["_instance"]
    try:
        await instance.disconnect()
    except Exception:
        pass  # Graceful degradation on disconnect failure

    await log_action(
        action="USER_CREATED",
        description=f"Connector '{entry['name']}' ({entry['type']}) removed",
        user_id=current_user.id,
        ip_address=request.client.host if request.client else None,
        details={"connector_id": connector_id, "connector_type": entry["type"]},
        db=db,
    )

    return {
        "message": f"Connector '{entry['name']}' removed successfully",
        "connector_id": connector_id,
    }


@router.get("/{connector_id}/status")
async def get_connector_status(
    connector_id: str,
    current_user=Depends(require_permission("patient.view")),
):
    """Get detailed health status of a registered connector."""
    entry = _CONNECTORS.get(connector_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Connector not found")

    instance: BaseEHRConnector = entry["_instance"]

    # Gather live status from the instance
    return {
        "connector_id": connector_id,
        "connector_type": entry["type"],
        "name": entry["name"],
        "connected": instance.status.connected,
        "last_sync": instance.status.last_sync.isoformat() if instance.status.last_sync else None,
        "error_count": instance.status.error_count,
        "last_error": instance.status.last_error,
        "last_error_at": instance.status.last_error_at.isoformat() if instance.status.last_error_at else None,
        "created_at": entry.get("created_at"),
    }
