"""HealthBridge Platform — Generic FHIR R4 EHR Connector

Implements :class:`BaseEHRConnector` for any FHIR R4 compliant server.

Supports standard FHIR operations:
  - Search (``GET /{resourceType}?{params}``)
  - Read (``GET /{resourceType}/{id}``)
  - Create (``POST /{resourceType}``)
  - CapabilityStatement (metadata) for connection testing

Works with any FHIR R4 server (HAPI FHIR, IBM FHIR, Google Healthcare API, …).
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Optional

import httpx

from app.connectors.base import BaseEHRConnector

logger = logging.getLogger("healthbridge.connectors.fhir")

DEFAULT_PAGE_SIZE = 50


class FHIRStandardConnector(BaseEHRConnector):
    """Generic FHIR R4 connector.

    Configuration keys (passed via ``config`` dict):
        ``fhir_base_url``: Base URL of the FHIR server (e.g. ``https://hapi.fhir.org/baseR4``).
        ``auth_token``: Optional Bearer token for authentication.
        ``headers``: Optional dict of additional HTTP headers.
        ``page_size``: Max number of resources per page (default 50).
    """

    def __init__(self, config: Optional[dict[str, Any]] = None) -> None:
        merged = dict(config or {})
        merged.setdefault("fhir_base_url", "http://localhost:8080/fhir")
        merged.setdefault("auth_token", "")
        merged.setdefault("headers", {})
        merged.setdefault("page_size", DEFAULT_PAGE_SIZE)
        super().__init__(merged)
        self._client: Optional[httpx.AsyncClient] = None

    # ── Lifecycle ──

    async def connect(self) -> bool:
        """Initialise the HTTP client and verify connectivity."""
        try:
            headers: dict[str, str] = {
                "Accept": "application/fhir+json",
                "Content-Type": "application/fhir+json",
            }
            # Apply custom headers
            headers.update(self.config.get("headers", {}))

            token = self.config.get("auth_token", "")
            if token:
                headers["Authorization"] = f"Bearer {token}"

            self._client = httpx.AsyncClient(
                base_url=self.config["fhir_base_url"].rstrip("/"),
                timeout=30.0,
                headers=headers,
            )

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
        """Search for Patient resources using FHIR search syntax.

        The query string is passed directly as the ``_search`` parameter
        or as query parameters.  Supports formats like:
          - ``name=John&birthdate=1990-01-01``
          - ``_id=123``
          - ``identifier=http://hospital.org|MRC-12345``
        """
        params = self._parse_query(query)
        params.setdefault("_count", self.config["page_size"])

        data = await self._read_resource("Patient", params=params)
        return self._extract_patients(data)

    async def get_patient(self, patient_id: str) -> Optional[dict[str, Any]]:
        """Read a single Patient resource by its FHIR logical ID."""
        try:
            data = await self._read_resource(f"Patient/{patient_id}")
            return self._fhir_patient_to_bridge(data)
        except Exception:
            return None

    async def get_patient_records(
        self,
        patient_id: str,
        record_type: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Fetch clinical resources associated with a patient.

        Supported record types (mapped to FHIR resource types):
          - ``"CONDITION"`` → ``Condition``
          - ``"OBSERVATION"`` → ``Observation``
          - ``"ENCOUNTER"`` → ``Encounter``
          - ``"MEDICATION_REQUEST"`` → ``MedicationRequest``
          - ``"IMMUNIZATION"`` → ``Immunization``
          - ``"ALLERGY_INTOLERANCE"`` → ``AllergyIntolerance``
          - ``"DOCUMENT_REFERENCE"`` → ``DocumentReference``
          - ``"PROCEDURE"`` → ``Procedure``
          - ``"DIAGNOSTIC_REPORT"`` → ``DiagnosticReport``
          ``None`` returns all of the above.
        """
        fhir_type_map: dict[str, str] = {
            "CONDITION": "Condition",
            "OBSERVATION": "Observation",
            "ENCOUNTER": "Encounter",
            "MEDICATION_REQUEST": "MedicationRequest",
            "IMMUNIZATION": "Immunization",
            "ALLERGY_INTOLERANCE": "AllergyIntolerance",
            "DOCUMENT_REFERENCE": "DocumentReference",
            "PROCEDURE": "Procedure",
            "DIAGNOSTIC_REPORT": "DiagnosticReport",
            "MEDICATION_STATEMENT": "MedicationStatement",
        }

        if record_type and record_type not in fhir_type_map:
            raise ValueError(
                f"Unsupported record type '{record_type}'. "
                f"Supported: {', '.join(fhir_type_map.keys())}"
            )

        types_to_fetch = (
            [record_type] if record_type else list(fhir_type_map.keys())
        )

        all_records: list[dict[str, Any]] = []
        for bridge_type in types_to_fetch:
            fhir_type = fhir_type_map[bridge_type]
            params = {"patient": patient_id, "_count": self.config["page_size"]}
            try:
                data = await self._read_resource(fhir_type, params=params)
                entries = data.get("entry", [])
                for entry in entries:
                    resource = entry.get("resource", {})
                    all_records.append(self._fhir_resource_to_record(resource, bridge_type))
            except Exception as exc:
                logger.warning(
                    f"Failed to fetch {fhir_type} for patient {patient_id}: {exc}"
                )

        return all_records

    async def push_record(
        self,
        patient_id: str,
        record_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Create a FHIR resource on the server.

        ``record_data`` should contain:
          - ``resourceType`` (required, e.g. ``"Observation"``)
          - ``resource`` (the FHIR resource JSON body)
        """
        resource_type = record_data.get("resourceType", "Observation")
        resource_body = record_data.get("resource", record_data)

        # Ensure patient reference is set
        if "subject" not in resource_body and patient_id:
            resource_body["subject"] = {"reference": f"Patient/{patient_id}"}

        return await self._create_resource(resource_type, resource_body)

    # ── Sync & Health ──

    async def sync_patients(self) -> dict[str, Any]:
        """Bulk-pull Patient resources (paginated via ``_getpages``)."""
        start = time.monotonic()
        url = "Patient"
        params: dict[str, Any] = {
            "_count": self.config["page_size"],
            "_sort": "_lastUpdated",
        }
        patients_pulled = 0
        records_pulled = 0
        errors: list[str] = []

        while True:
            try:
                data = await self._read_resource(url, params=params if url == "Patient" else None)
                entries = data.get("entry", [])
                for entry in entries:
                    resource = entry.get("resource", {})
                    if resource.get("resourceType") == "Patient":
                        patients_pulled += 1
                        patient_id = resource.get("id", "")
                        if patient_id:
                            try:
                                recs = await self.get_patient_records(patient_id)
                                records_pulled += len(recs)
                            except Exception as exc:
                                errors.append(f"Records for {patient_id}: {exc}")

                # Follow the next link (FHIR paging)
                link = data.get("link", [])
                next_url = None
                for ln in link:
                    if ln.get("relation") == "next":
                        next_url = ln.get("url", "")
                        break

                if not next_url:
                    break

                # For the next iteration, use the relative path from the next URL
                # If it's absolute, extract the path
                if "://" in next_url:
                    from urllib.parse import urlparse

                    parsed = urlparse(next_url)
                    url = parsed.path + ("?" + parsed.query if parsed.query else "")
                    params = {}  # params are now in the URL
                else:
                    url = next_url
                    params = {}

            except Exception as exc:
                errors.append(str(exc))
                break

        duration = time.monotonic() - start
        return {
            "connector": "fhir",
            "patients_pulled": patients_pulled,
            "records_pulled": records_pulled,
            "errors": errors,
            "duration_seconds": round(duration, 2),
        }

    async def test_connection(self) -> dict[str, Any]:
        """Verify connectivity by reading the server's CapabilityStatement."""
        start = time.monotonic()
        try:
            data = await self._read_resource("metadata")
            latency = (time.monotonic() - start) * 1000

            fhir_version = data.get("fhirVersion", "unknown")
            publisher = data.get("publisher", "unknown")
            return {
                "connected": True,
                "latency_ms": round(latency, 2),
                "fhir_version": fhir_version,
                "publisher": publisher,
                "connector": "fhir",
                "base_url": self.config["fhir_base_url"],
            }
        except Exception as exc:
            latency = (time.monotonic() - start) * 1000
            self._record_error(str(exc))
            return {
                "connected": False,
                "latency_ms": round(latency, 2),
                "error": str(exc),
                "connector": "fhir",
            }

    # ── Internal helpers ──

    async def _read_resource(
        self,
        path: str,
        params: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """GET a FHIR resource endpoint."""
        if not self._client:
            raise RuntimeError("Connector not connected.  Call connect() first.")

        resp = await self._client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()

    async def _create_resource(
        self,
        resource_type: str,
        resource_body: dict[str, Any],
    ) -> dict[str, Any]:
        """POST a new FHIR resource."""
        if not self._client:
            raise RuntimeError("Connector not connected.  Call connect() first.")

        resp = await self._client.post(resource_type, json=resource_body)
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _parse_query(query: str) -> dict[str, str]:
        """Parse a simple query string into a dict of FHIR search parameters.

        Supports ``key=value`` pairs separated by ``&``.
        """
        params: dict[str, str] = {}
        for part in query.split("&"):
            part = part.strip()
            if "=" in part:
                key, value = part.split("=", 1)
                params[key.strip()] = value.strip()
        return params

    @staticmethod
    def _extract_patients(data: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract patient dicts from a FHIR Bundle search result."""
        entries = data.get("entry", [])
        patients: list[dict[str, Any]] = []
        for entry in entries:
            resource = entry.get("resource", {})
            if resource.get("resourceType") == "Patient":
                patients.append(FHIRStandardConnector._fhir_patient_to_bridge(resource))
        return patients

    @staticmethod
    def _fhir_patient_to_bridge(resource: dict[str, Any]) -> dict[str, Any]:
        """Map a FHIR R4 Patient resource to canonical HealthBridge format."""
        name = (resource.get("name") or [{}])[0]
        given = " ".join(name.get("given", []))
        family = name.get("family", "")
        identifier = (resource.get("identifier") or [{}])[0]
        address = (resource.get("address") or [{}])[0]
        telecom = resource.get("telecom", [])

        phone = ""
        email = ""
        for t in telecom:
            if t.get("system") == "phone":
                phone = t.get("value", phone)
            elif t.get("system") == "email":
                email = t.get("value", email)

        return {
            "external_id": resource.get("id", ""),
            "mrn": identifier.get("value", ""),
            "first_name": given,
            "last_name": family,
            "name": f"{given} {family}".strip(),
            "date_of_birth": resource.get("birthDate", ""),
            "gender": resource.get("gender", "UNKNOWN").upper() or "UNKNOWN",
            "phone": phone,
            "email": email,
            "address": address.get("text", address.get("line", [""])[0]) if address else "",
            "city": address.get("city", "") if address else "",
            "state": address.get("state", "") if address else "",
            "pincode": address.get("postalCode", "") if address else "",
            "source_system": "FHIR_R4",
            "raw_resource": resource,
        }

    @staticmethod
    def _fhir_resource_to_record(
        resource: dict[str, Any],
        bridge_type: str,
    ) -> dict[str, Any]:
        """Map any FHIR resource to a canonical record dict."""
        return {
            "external_id": resource.get("id", ""),
            "record_type": bridge_type,
            "fhir_resource_type": resource.get("resourceType", ""),
            "fhir_resource_json": resource,
            "display_name": resource.get("code", {}).get("text", "")
            or (resource.get("code", {}).get("coding", [{}])[0].get("display", "")
                if resource.get("code") else ""),
            "recorded_date": resource.get("recordedDate", resource.get("occurrenceDateTime", "")),
            "status": resource.get("status", ""),
            "source_system": "FHIR_R4",
        }
