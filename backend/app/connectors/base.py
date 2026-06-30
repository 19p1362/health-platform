"""HealthBridge Platform — Abstract Base EHR Connector

Defines the interface that all EHR connector implementations must satisfy.
Each connector manages its own connection lifecycle, error tracking, and
synchronisation state.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


# ═══════════════════════════════════════════════════
# Connection Status
# ═══════════════════════════════════════════════════


@dataclass
class ConnectionStatus:
    """Tracks the health and activity state of an EHR connector instance."""

    connector_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    connected: bool = False
    last_sync: Optional[datetime] = None
    error_count: int = 0
    last_error: Optional[str] = None
    last_error_at: Optional[datetime] = None


# ═══════════════════════════════════════════════════
# Abstract Base Connector
# ═══════════════════════════════════════════════════


class BaseEHRConnector(ABC):
    """Abstract base for all EHR system connectors.

    Subclasses **must** implement every abstract method.  Concrete
    implementations are responsible for their own HTTP client lifecycle,
    authentication, and data mapping.
    """

    def __init__(self, config: Optional[dict[str, Any]] = None) -> None:
        self.config: dict[str, Any] = config or {}
        self.status: ConnectionStatus = ConnectionStatus()

    # ── Lifecycle ──

    @abstractmethod
    async def connect(self) -> bool:
        """Establish a connection to the external EHR system.

        Returns:
            ``True`` on success, ``False`` otherwise.  On failure the
            ``status`` fields (``last_error``, ``error_count``) are
            updated automatically.
        """
        ...

    @abstractmethod
    async def disconnect(self) -> bool:
        """Tear down the connection gracefully.

        Returns:
            ``True`` if the disconnection was successful.
        """
        ...

    # ── Patient Operations ──

    @abstractmethod
    async def search_patients(self, query: str) -> list[dict[str, Any]]:
        """Search for patients by a free-text query (name, ID, MRN, …).

        Args:
            query: Search string (e.g. ``"John Doe"`` or ``"MRC-12345"``).

        Returns:
            A list of patient dicts in a canonical HealthBridge format.
        """
        ...

    @abstractmethod
    async def get_patient(self, patient_id: str) -> Optional[dict[str, Any]]:
        """Retrieve a single patient by its external ID.

        Args:
            patient_id: The patient's identifier in the external system.

        Returns:
            A patient dict, or ``None`` if not found.
        """
        ...

    @abstractmethod
    async def get_patient_records(
        self,
        patient_id: str,
        record_type: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Fetch clinical records for a patient.

        Args:
            patient_id: External patient identifier.
            record_type: Optional filter (e.g. ``"OBSERVATION"``,
                ``"CONDITION"``).  ``None`` means all types.

        Returns:
            A list of record dicts.
        """
        ...

    @abstractmethod
    async def push_record(
        self,
        patient_id: str,
        record_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Push a clinical record to the external EHR system.

        Args:
            patient_id: External patient identifier.
            record_data: Record payload (canonical HealthBridge format or
                native FHIR JSON).

        Returns:
            The response from the external system (typically the created
            resource with its server-assigned ID).
        """
        ...

    # ── Sync & Health ──

    @abstractmethod
    async def sync_patients(self) -> dict[str, Any]:
        """Pull new / updated patients and records from the external system.

        Returns:
            A summary dict with keys such as ``patients_pulled``,
            ``records_pulled``, ``errors``, and ``duration_seconds``.
        """
        ...

    @abstractmethod
    async def test_connection(self) -> dict[str, Any]:
        """Verify connectivity and return a health report.

        Returns:
            A dict like ``{"connected": True, "latency_ms": 123,
            "version": "v2.4.1", …}``.
        """
        ...

    # ── Utility ──

    def _record_error(self, error: str) -> None:
        """Increment the error counter and store the latest error message."""
        self.status.error_count += 1
        self.status.last_error = error
        self.status.last_error_at = datetime.utcnow()
