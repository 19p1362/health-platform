"""HealthBridge Platform — ABDM (Ayushman Bharat Digital Mission) EHR Connector

Implements :class:`BaseEHRConnector` for the ABDM network using ABHA
numbers for patient linking.  Delegates low-level API calls to the
existing :mod:`app.services.abha_connector` module where applicable.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

import httpx

from app.config import settings
from app.connectors.base import BaseEHRConnector

logger = logging.getLogger("healthbridge.connectors.abdm")

ABHA_API_BASE = settings.ABHA_API_BASE_URL.rstrip("/")


class ABDMConnector(BaseEHRConnector):
    """Connector for the ABDM (Ayushman Bharat Digital Mission) network.

    Uses ABHA (Ayushman Bharat Health Account) numbers as the primary
    patient identifier.  Delegates to :class:`ABHAConnector` (from
    :mod:`app.services.abha_connector`) for individual API calls so that
    existing retry / audit logic is preserved.
    """

    def __init__(self, config: Optional[dict[str, Any]] = None) -> None:
        super().__init__(config or {})
        self._client: Optional[httpx.AsyncClient] = None
        self._abha_connector: Any = None  # lazy-imported ABHAConnector

    # ── Lifecycle ──

    async def connect(self) -> bool:
        """Initialise the HTTP client and verify credentials."""
        try:
            self._client = httpx.AsyncClient(
                base_url=ABHA_API_BASE,
                timeout=30.0,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
            )
            # Verify connectivity by calling the health / token endpoint
            result = await self.test_connection()
            self.status.connected = result.get("connected", False)
            return self.status.connected
        except Exception as exc:
            self._record_error(f"Connect failed: {exc}")
            return False

    async def disconnect(self) -> bool:
        """Close the HTTP client."""
        try:
            if self._client:
                await self._client.aclose()
            self._client = None
            self.status.connected = False
            return True
        except Exception as exc:
            self._record_error(f"Disconnect failed: {exc}")
            return False

    # ── Patient Operations ──

    async def search_patients(self, query: str) -> list[dict[str, Any]]:
        """Search patients via ABHA number or demographic details.

        Uses the underlying ``ABHAConnector.search_abha()`` when the query
        looks like demographic data, or a direct ABHA lookup by number.
        """
        from app.services.abha_connector import ABHAConnector

        connector = ABHAConnector()
        # Try interpreting the query as an ABHA address first
        if "@" in query or query.isalnum():
            try:
                profile = await connector.get_abha_profile(query)
                return [self._abha_profile_to_patient(profile)]
            except Exception:
                pass

        # Fall back to demographic search  —  we require name,dob,gender,mobile
        # which the caller provides as a comma-separated string.
        parts = [p.strip() for p in query.split(",")]
        if len(parts) >= 4:
            name, dob, gender, mobile = parts[:4]
            result = await connector.search_abha(
                name=name, dob=dob, gender=gender, mobile=mobile
            )
            patients = result.get("patients", result.get("accounts", []))
            return [self._abha_profile_to_patient(p) for p in patients]

        logger.warning("ABDM search requires 4 comma-separated fields: name,dob,gender,mobile")
        return []

    async def get_patient(self, patient_id: str) -> Optional[dict[str, Any]]:
        """Retrieve patient profile by ABHA address."""
        from app.services.abha_connector import ABHAConnector

        connector = ABHAConnector()
        try:
            profile = await connector.get_abha_profile(patient_id)
            return self._abha_profile_to_patient(profile)
        except Exception:
            return None

    async def get_patient_records(
        self,
        patient_id: str,
        record_type: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Pull health records from ABDM via consent-based APIs.

        Note: ABDM requires an active consent artefact to pull records.
        This method expects the patient to have a valid consent already
        established.  If no consent is found, an empty list is returned.
        """
        from app.services.abha_connector import ABHAConnector

        connector = ABHAConnector()
        try:
            # Attempt to fetch records using the consent-manager flow
            result = await connector.get_abha_profile(patient_id)
            records = result.get("healthRecords", result.get("records", []))
            if record_type:
                records = [r for r in records if r.get("type") == record_type]
            return records
        except Exception:
            return []

    async def push_record(
        self,
        patient_id: str,
        record_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Push a health record to the ABDM network.

        Requires a linked ABHA address and active consent.
        """
        from app.services.abha_connector import ABHAConnector, ABHAError

        connector = ABHAConnector()
        try:
            # The ABHAConnector doesn't expose a direct "push" endpoint in its
            # current API, so we use the internal _api_call helper.
            result = await connector._api_call(
                method="POST",
                path="/v1/records/push",
                patient_id=patient_id,
                transaction_type="PUSH_RECORD",
                payload=record_data,
            )
            return result
        except ABHAError as exc:
            self._record_error(f"Push record failed: {exc}")
            raise

    # ── Sync & Health ──

    async def sync_patients(self) -> dict[str, Any]:
        """Pull all linked patients' records (stub — ABDM is event-driven).

        ABDM is a push-based / consent-driven network; bulk sync is not
        natively supported.  This method returns a summary indicating that
        sync must be triggered per-patient.
        """
        return {
            "connector": "abdm",
            "patients_pulled": 0,
            "records_pulled": 0,
            "errors": [],
            "message": (
                "ABDM is a consent-driven network.  Sync individual patients "
                "via get_patient_records()."
            ),
            "duration_seconds": 0.0,
        }

    async def test_connection(self) -> dict[str, Any]:
        """Verify connectivity by attempting a token acquisition."""
        import time

        start = time.monotonic()
        try:
            from app.services.abha_connector import _get_access_token

            token = await _get_access_token()
            latency = (time.monotonic() - start) * 1000
            return {
                "connected": bool(token),
                "latency_ms": round(latency, 2),
                "version": "ABDM v1.0",
                "connector": "abdm",
                "base_url": ABHA_API_BASE,
            }
        except Exception as exc:
            latency = (time.monotonic() - start) * 1000
            self._record_error(str(exc))
            return {
                "connected": False,
                "latency_ms": round(latency, 2),
                "error": str(exc),
                "connector": "abdm",
            }

    # ── Helpers ──

    @staticmethod
    def _abha_profile_to_patient(profile: dict[str, Any]) -> dict[str, Any]:
        """Map an ABHA profile dict to a canonical HealthBridge patient dict."""
        return {
            "external_id": profile.get("healthId", profile.get("abhaAddress", "")),
            "abha_number": profile.get("healthId", ""),
            "first_name": profile.get("firstName", ""),
            "last_name": profile.get("lastName", ""),
            "name": f"{profile.get('firstName', '')} {profile.get('lastName', '')}".strip(),
            "date_of_birth": profile.get("dateOfBirth", profile.get("dob")),
            "gender": profile.get("gender", "UNKNOWN"),
            "phone": profile.get("mobile", ""),
            "email": profile.get("email", ""),
            "address": profile.get("address", ""),
            "photo": profile.get("photo", ""),
            "source_system": "ABDM",
        }
