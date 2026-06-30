"""HealthBridge Platform — OpenMRS EHR Connector

Implements :class:`BaseEHRConnector` for the OpenMRS (Open Medical Record
System) REST API.

Maps OpenMRS patient and observation resources to a canonical HealthBridge
format.  Supports searching by name / identifier, and fetching encounters
and observations.
"""

from __future__ import annotations

import base64
import logging
import time
from datetime import datetime, date
from typing import Any, Optional

import httpx

from app.connectors.base import BaseEHRConnector

logger = logging.getLogger("healthbridge.connectors.openmrs")

# ── OpenMRS API version constants ──
OPENMRS_REST_VERSION = "v1"
DEFAULT_PAGE_SIZE = 50


class OpenMRSConnector(BaseEHRConnector):
    """Connector for the OpenMRS REST API.

    Configuration keys (passed via ``config`` dict):
        ``base_url``: OpenMRS server base URL (e.g. ``https://demo.openmrs.org/openmrs``).
        ``username``: API username.
        ``password``: API password.
        ``page_size``: Number of results per page (default 50).
    """

    def __init__(self, config: Optional[dict[str, Any]] = None) -> None:
        merged = dict(config or {})
        merged.setdefault("base_url", "http://localhost:8080/openmrs")
        merged.setdefault("page_size", DEFAULT_PAGE_SIZE)
        super().__init__(merged)
        self._client: Optional[httpx.AsyncClient] = None

    # ── Lifecycle ──

    async def connect(self) -> bool:
        """Initialise the HTTP client with Basic Auth and verify connectivity."""
        try:
            auth_header = self._basic_auth_header()
            self._client = httpx.AsyncClient(
                base_url=self.config["base_url"].rstrip("/"),
                timeout=30.0,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "Authorization": auth_header,
                },
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
        """Search OpenMRS patients by name or identifier.

        Calls ``/ws/rest/v1/patient?q={query}``.
        """
        url = f"/ws/rest/{OPENMRS_REST_VERSION}/patient"
        params: dict[str, Any] = {"q": query, "v": "full", "limit": self.config["page_size"]}

        data = await self._get(url, params=params)
        results = data.get("results", [])
        return [self._openmrs_patient_to_bridge(patient) for patient in results]

    async def get_patient(self, patient_id: str) -> Optional[dict[str, Any]]:
        """Retrieve a single OpenMRS patient by UUID."""
        url = f"/ws/rest/{OPENMRS_REST_VERSION}/patient/{patient_id}"
        params = {"v": "full"}

        try:
            data = await self._get(url, params=params)
            return self._openmrs_patient_to_bridge(data)
        except Exception:
            return None

    async def get_patient_records(
        self,
        patient_id: str,
        record_type: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Fetch clinical records (encounters + observations) for a patient.

        Args:
            patient_id: OpenMRS patient UUID.
            record_type: If ``"ENCOUNTER"`` only encounters are returned;
                if ``"OBSERVATION"`` only observations; ``None`` returns both.

        Returns:
            A list of record dicts in canonical HealthBridge format.
        """
        records: list[dict[str, Any]] = []

        if record_type in (None, "ENCOUNTER"):
            records.extend(await self._fetch_encounters(patient_id))

        if record_type in (None, "OBSERVATION"):
            records.extend(await self._fetch_observations(patient_id))

        return records

    async def push_record(
        self,
        patient_id: str,
        record_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Push a record to OpenMRS as an observation or encounter.

        If ``record_data`` contains an ``"encounterType"`` key it is posted
        as an encounter; otherwise it is posted as an observation.
        """
        if "encounterType" in record_data:
            return await self._post_encounter(patient_id, record_data)

        return await self._post_observation(patient_id, record_data)

    # ── Sync & Health ──

    async def sync_patients(self) -> dict[str, Any]:
        """Pull all patients from OpenMRS (paginated)."""
        start = time.monotonic()
        url = "/ws/rest/v1/patient"
        params: dict[str, Any] = {"v": "full", "limit": self.config["page_size"]}
        patients_pulled = 0
        records_pulled = 0
        errors: list[str] = []

        while True:
            try:
                data = await self._get(url, params=params)
                results = data.get("results", [])
                patients_pulled += len(results)

                for patient in results:
                    try:
                        patient_id = patient.get("uuid", "")
                        patient_records = await self._fetch_encounters(patient_id)
                        records_pulled += len(patient_records)
                    except Exception as exc:
                        errors.append(f"Failed to fetch records for {patient.get('uuid', '')}: {exc}")

                # Pagination
                links = data.get("links", [])
                next_link = next(
                    (link["uri"] for link in links if link.get("rel") == "next"), None
                )
                if not next_link:
                    break
                # The next link is an absolute URL; we need to extract query params
                # For simplicity, increment offset
                params["startIndex"] = params.get("startIndex", 0) + self.config["page_size"]

            except Exception as exc:
                errors.append(str(exc))
                break

        duration = time.monotonic() - start
        return {
            "connector": "openmrs",
            "patients_pulled": patients_pulled,
            "records_pulled": records_pulled,
            "errors": errors,
            "duration_seconds": round(duration, 2),
        }

    async def test_connection(self) -> dict[str, Any]:
        """Verify connectivity by calling the OpenMRS server info endpoint."""
        start = time.monotonic()
        try:
            data = await self._get("/ws/rest/v1/systemsettings")
            latency = (time.monotonic() - start) * 1000
            return {
                "connected": True,
                "latency_ms": round(latency, 2),
                "connector": "openmrs",
                "base_url": self.config["base_url"],
            }
        except Exception as exc:
            latency = (time.monotonic() - start) * 1000
            self._record_error(str(exc))
            return {
                "connected": False,
                "latency_ms": round(latency, 2),
                "error": str(exc),
                "connector": "openmrs",
            }

    # ── Internal API helpers ──

    async def _get(self, url: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        """Make an authenticated GET request."""
        if not self._client:
            raise RuntimeError("Connector not connected.  Call connect() first.")

        resp = await self._client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()

    async def _post(
        self, url: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Make an authenticated POST request."""
        if not self._client:
            raise RuntimeError("Connector not connected.  Call connect() first.")

        resp = await self._client.post(url, json=payload)
        resp.raise_for_status()
        return resp.json()

    # ── Encounter / Observation fetchers ──

    async def _fetch_encounters(self, patient_id: str) -> list[dict[str, Any]]:
        """Fetch all encounters for an OpenMRS patient."""
        url = f"/ws/rest/v1/encounter"
        params = {
            "patient": patient_id,
            "v": "full",
            "limit": self.config["page_size"],
        }
        try:
            data = await self._get(url, params=params)
            results = data.get("results", [])
            return [self._openmrs_encounter_to_record(e) for e in results]
        except Exception as exc:
            logger.warning(f"Failed to fetch encounters for patient {patient_id}: {exc}")
            return []

    async def _fetch_observations(self, patient_id: str) -> list[dict[str, Any]]:
        """Fetch all observations for an OpenMRS patient."""
        url = f"/ws/rest/v1/obs"
        params = {
            "patient": patient_id,
            "v": "full",
            "limit": self.config["page_size"],
        }
        try:
            data = await self._get(url, params=params)
            results = data.get("results", [])
            return [self._openmrs_obs_to_record(o) for o in results]
        except Exception as exc:
            logger.warning(f"Failed to fetch observations for patient {patient_id}: {exc}")
            return []

    async def _post_encounter(
        self, patient_id: str, record_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Create an encounter in OpenMRS."""
        payload = {
            "patient": patient_id,
            "encounterType": record_data.get("encounterType", "NORMAL"),
            "encounterDatetime": record_data.get(
                "encounterDatetime", datetime.utcnow().isoformat()
            ),
            "location": record_data.get("location", ""),
            "encounterProviders": record_data.get("encounterProviders", []),
            "obs": record_data.get("obs", []),
            "orders": record_data.get("orders", []),
        }
        return await self._post("/ws/rest/v1/encounter", payload)

    async def _post_observation(
        self, patient_id: str, record_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Create an observation in OpenMRS."""
        payload = {
            "patient": patient_id,
            "concept": record_data.get("concept", record_data.get("code", "")),
            "obsDatetime": record_data.get(
                "obsDatetime", datetime.utcnow().isoformat()
            ),
            "value": record_data.get("value", record_data.get("display_name", "")),
        }
        return await self._post("/ws/rest/v1/obs", payload)

    # ── Data mapping helpers ──

    def _basic_auth_header(self) -> str:
        username = self.config.get("username", "")
        password = self.config.get("password", "")
        if not username or not password:
            logger.warning("OpenMRS credentials not configured — using empty auth")
        return "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode()

    @staticmethod
    def _openmrs_patient_to_bridge(patient: dict[str, Any]) -> dict[str, Any]:
        """Map an OpenMRS patient resource to canonical HealthBridge format."""
        person = patient.get("person", {})
        preferred_name = person.get("preferredName", person.get("names", [{}])[0])
        preferred_address = person.get("preferredAddress", {})
        identifiers = patient.get("identifiers", [])

        mrn = ""
        for ident in identifiers:
            if ident.get("identifierType", {}).get("name", "").upper() in (
                "MRN",
                "OPENMRS_ID",
                "PATIENT_IDENTIFIER",
            ):
                mrn = ident.get("identifier", "")
                break
        if not mrn and identifiers:
            mrn = identifiers[0].get("identifier", "")

        return {
            "external_id": patient.get("uuid", ""),
            "mrn": mrn,
            "first_name": preferred_name.get("givenName", ""),
            "last_name": preferred_name.get("familyName", ""),
            "name": f"{preferred_name.get('givenName', '')} {preferred_name.get('familyName', '')}".strip(),
            "date_of_birth": person.get("birthdate", ""),
            "gender": (person.get("gender", "UNKNOWN") or "UNKNOWN"),
            "address": preferred_address.get("display", ""),
            "phone": person.get("attributes", [{}])[0].get("value", "") if person.get("attributes") else "",
            "source_system": "OpenMRS",
        }

    @staticmethod
    def _openmrs_encounter_to_record(encounter: dict[str, Any]) -> dict[str, Any]:
        """Map an OpenMRS encounter to a canonical record dict."""
        return {
            "external_id": encounter.get("uuid", ""),
            "record_type": "ENCOUNTER",
            "encounter_type": encounter.get("encounterType", {}).get("display", ""),
            "encounter_datetime": encounter.get("encounterDatetime", ""),
            "location": encounter.get("location", {}).get("display", "") if encounter.get("location") else "",
            "provider": encounter.get("encounterProviders", [{}])[0].get("provider", {}).get("display", ""),
            "observations": [
                {
                    "uuid": obs.get("uuid", ""),
                    "concept": obs.get("concept", {}).get("display", ""),
                    "value": obs.get("value", ""),
                }
                for obs in encounter.get("obs", [])
            ],
            "source_system": "OpenMRS",
        }

    @staticmethod
    def _openmrs_obs_to_record(obs: dict[str, Any]) -> dict[str, Any]:
        """Map an OpenMRS observation to a canonical record dict."""
        return {
            "external_id": obs.get("uuid", ""),
            "record_type": "OBSERVATION",
            "concept": obs.get("concept", {}).get("display", ""),
            "value": obs.get("value", ""),
            "obs_datetime": obs.get("obsDatetime", ""),
            "status": obs.get("status", "FINAL"),
            "comment": obs.get("comment", ""),
            "source_system": "OpenMRS",
        }
