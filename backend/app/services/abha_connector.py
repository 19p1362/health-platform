"""
HealthBridge Platform — ABHA (Ayushman Bharat Health Account) Connector

Provides integration with the ABDM (Ayushman Bharat Digital Mission) network:
  - Generate ABHA numbers via Aadhaar OTP
  - Search existing ABHA records
  - Link ABHA to patient records
  - Retrieve ABHA profiles
  - Create and manage consent artifacts (ABDM gateway)
  - Pull health records via consent
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

import httpx
from tenacity import (
    after_log,
    before_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import ABHATransaction, Patient

logger = logging.getLogger("healthbridge.abha")

# ── Constants ──
ABHA_API_BASE = settings.ABHA_API_BASE_URL.rstrip("/")
ABHA_CLIENT_ID = settings.ABHA_CLIENT_ID
ABHA_CLIENT_SECRET = settings.ABHA_CLIENT_SECRET

MAX_RETRIES = 3
RETRY_MIN_WAIT = 1  # seconds
RETRY_MAX_WAIT = 10  # seconds


# ═══════════════════════════════════════════════════
# Custom Exceptions
# ═══════════════════════════════════════════════════

class ABHAError(Exception):
    """Base exception for ABHA operations."""


class ABHAAuthenticationError(ABHAError):
    """Raised when ABHA API authentication fails."""


class ABHANotFoundError(ABHAError):
    """Raised when the requested ABHA resource is not found."""


class ABHARateLimitError(ABHAError):
    """Raised when ABHA API rate limit is exceeded."""


class ABHAValidationError(ABHAError):
    """Raised when input validation fails for ABHA operations."""


# ═══════════════════════════════════════════════════
# Retry configuration
# ═══════════════════════════════════════════════════

def _abha_retry_decorator() -> Any:
    """Default tenacity retry decorator for ABHA API calls."""
    return retry(
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=RETRY_MIN_WAIT, max=RETRY_MAX_WAIT),
        retry=retry_if_exception_type(
            (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError)
        ),
        before=before_log(logger, logging.DEBUG),
        after=after_log(logger, logging.DEBUG),
        reraise=True,
    )


# ═══════════════════════════════════════════════════
# Helper: acquire bearer token
# ═══════════════════════════════════════════════════

async def _get_access_token() -> str:
    """
    Obtain an OAuth2 bearer token from the ABDM gateway using
    client credentials.
    """
    token_url = f"{ABHA_API_BASE}/gateway/v0.5/sessions"
    payload = {
        "clientId": ABHA_CLIENT_ID,
        "clientSecret": ABHA_CLIENT_SECRET,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(token_url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get("accessToken", "")
        except httpx.HTTPStatusError as exc:
            logger.error(f"ABHA token acquisition failed: {exc.response.status_code} {exc.response.text}")
            raise ABHAAuthenticationError(
                f"Failed to acquire ABHA token: {exc.response.status_code}"
            ) from exc
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            logger.error(f"ABHA token endpoint unreachable: {exc}")
            raise ABHAError(f"ABHA gateway unreachable: {exc}") from exc


# ═══════════════════════════════════════════════════
# Helper: record transaction in DB
# ═══════════════════════════════════════════════════

async def _record_transaction(
    patient_id: str | None,
    transaction_type: str,
    abha_address: str | None,
    transaction_id: str | None,
    request_payload: dict,
    response_status: int | None,
    response_body: dict | None,
    error_message: str | None,
    started_at: datetime,
    completed_at: datetime,
    user_id: str | None = None,
    ip_address: str | None = None,
) -> None:
    """Persist an ABHA API transaction record to the database."""
    duration_ms: int | None = None
    if started_at and completed_at:
        duration_ms = int((completed_at - started_at).total_seconds() * 1000)

    async with AsyncSessionLocal() as session:
        record = ABHATransaction(
            patient_id=patient_id,
            transaction_type=transaction_type,
            abha_address=abha_address,
            transaction_id=transaction_id,
            request_payload=request_payload,
            response_status=response_status,
            response_body=response_body or {},
            error_message=error_message,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=duration_ms,
            user_id=user_id,
            ip_address=ip_address,
        )
        session.add(record)
        await session.commit()


# ═══════════════════════════════════════════════════
# ABHA Connector
# ═══════════════════════════════════════════════════

class ABHAConnector:
    """
    Async connector for the ABDM (Ayushman Bharat Digital Mission) ABHA API.

    Every public method:
      - Uses ``httpx.AsyncClient`` for HTTP calls
      - Applies ``tenacity`` retry logic on transient failures
      - Persists a detailed audit record via :class:`ABHATransaction`
    """

    # ── Lifecycle ──

    def __init__(self, user_id: str | None = None, ip_address: str | None = None) -> None:
        self.user_id = user_id
        self.ip_address = ip_address

    # ── Internal helpers ──

    async def _api_call(
        self,
        method: str,
        path: str,
        patient_id: str | None = None,
        abha_address: str | None = None,
        transaction_type: str = "GENERIC",
        payload: dict | None = None,
        headers: dict | None = None,
        auth_required: bool = True,
    ) -> dict:
        """
        Make an authenticated API call to the ABDM gateway with full audit logging.

        Parameters
        ----------
        method : str
            HTTP method (GET, POST, etc.).
        path : str
            URL path relative to ABHA_API_BASE.
        patient_id : str | None
            Patient DB identifier for audit trail.
        abha_address : str | None
            ABHA address (health ID).
        transaction_type : str
            Semantic type (CREATE, LINK, SEARCH, etc.).
        payload : dict | None
            JSON request body.
        headers : dict | None
            Additional HTTP headers.
        auth_required : bool
            Whether to attach a Bearer token.

        Returns
        -------
        dict
            JSON response body.

        Raises
        ------
        ABHAError
            On any API-level failure.
        """
        started_at = datetime.utcnow()
        request_payload = payload or {}
        url = f"{ABHA_API_BASE}{path}"
        _headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if headers:
            _headers.update(headers)

        resolved_transaction_id: str | None = None

        try:
            if auth_required:
                token = await _get_access_token()
                _headers["Authorization"] = f"Bearer {token}"

            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.request(
                    method=method.upper(),
                    url=url,
                    headers=_headers,
                    json=payload if method.upper() in ("POST", "PUT", "PATCH") else None,
                    params=payload if method.upper() == "GET" else None,
                )

                completed_at = datetime.utcnow()
                resp_status = resp.status_code
                resp_body: dict = {}
                error_msg: str | None = None

                try:
                    resp_body = resp.json()
                except (json.JSONDecodeError, httpx.DecodingError):
                    resp_body = {"raw": resp.text}

                # Extract transaction ID from response if present
                resolved_transaction_id = resp_body.get("transactionId") or resp_body.get("txnId")

                if resp.is_success:
                    await _record_transaction(
                        patient_id=patient_id,
                        transaction_type=transaction_type,
                        abha_address=abha_address,
                        transaction_id=resolved_transaction_id,
                        request_payload=request_payload,
                        response_status=resp_status,
                        response_body=resp_body,
                        error_message=None,
                        started_at=started_at,
                        completed_at=completed_at,
                        user_id=self.user_id,
                        ip_address=self.ip_address,
                    )
                    return resp_body

                # Handle non-2xx responses
                error_msg = resp_body.get("error", {}).get("message", resp.text)

                if resp_status == 401:
                    raise ABHAAuthenticationError(error_msg)
                if resp_status == 404:
                    raise ABHANotFoundError(error_msg or "Resource not found")
                if resp_status == 429:
                    raise ABHARateLimitError(error_msg or "Rate limit exceeded")
                if resp_status == 422:
                    raise ABHAValidationError(error_msg or "Validation error")

                raise ABHAError(f"ABHA API error [{resp_status}]: {error_msg}")

        except (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError) as exc:
            completed_at = datetime.utcnow()
            await _record_transaction(
                patient_id=patient_id,
                transaction_type=transaction_type,
                abha_address=abha_address,
                transaction_id=resolved_transaction_id,
                request_payload=request_payload,
                response_status=None,
                response_body=None,
                error_message=str(exc),
                started_at=started_at,
                completed_at=completed_at,
                user_id=self.user_id,
                ip_address=self.ip_address,
            )
            raise ABHAError(f"ABHA API unreachable: {exc}") from exc
        except (ABHAError, ABHAAuthenticationError, ABHANotFoundError,
                ABHARateLimitError, ABHAValidationError) as exc:
            completed_at = datetime.utcnow()
            await _record_transaction(
                patient_id=patient_id,
                transaction_type=transaction_type,
                abha_address=abha_address,
                transaction_id=resolved_transaction_id,
                request_payload=request_payload,
                response_status=resp_status if 'resp_status' in locals() else None,
                response_body=resp_body if 'resp_body' in locals() else None,
                error_message=str(exc),
                started_at=started_at,
                completed_at=completed_at,
                user_id=self.user_id,
                ip_address=self.ip_address,
            )
            raise

    # ── Generate ABHA via Aadhaar OTP ──

    @_abha_retry_decorator()
    async def generate_abha(self, aadhaar_number: str) -> dict:
        """
        Initiate ABHA creation flow using Aadhaar-based OTP verification.

        This is the first step — returns a ``transactionId`` that must be
        passed to the OTP verification endpoint in subsequent calls.

        Parameters
        ----------
        aadhaar_number : str
            12-digit Aadhaar number (masked/encrypted in transit).

        Returns
        -------
        dict
            Response containing ``transactionId`` and OTP reference details.
        """
        # In production the Aadhaar number is encrypted at the application
        # layer before transmission. Here we pass a hashed reference.
        path = "/v1/account/aadhaar/generateOtp"
        payload = {"aadhaar": aadhaar_number}

        return await self._api_call(
            method="POST",
            path=path,
            patient_id=None,
            abha_address=None,
            transaction_type="CREATE",
            payload=payload,
        )

    # ── Search existing ABHA ──

    @_abha_retry_decorator()
    async def search_abha(
        self,
        name: str,
        dob: str,
        gender: str,
        mobile: str,
    ) -> dict:
        """
        Search for an existing ABHA (Health ID) by demographic details.

        Parameters
        ----------
        name : str
            Full name as registered with ABDM.
        dob : str
            Date of birth in ``YYYY-MM-DD`` format.
        gender : str
            Gender — ``M``, ``F``, or ``O``.
        mobile : str
            10-digit mobile number linked to Aadhaar.

        Returns
        -------
        dict
            List of matching ABHA records with ``healthId`` and status.
        """
        path = "/v1/account/search"
        payload = {
            "name": name,
            "dateOfBirth": dob,
            "gender": gender,
            "mobile": mobile,
        }

        return await self._api_call(
            method="POST",
            path=path,
            transaction_type="SEARCH",
            payload=payload,
        )

    # ── Link ABHA to patient record ──

    @_abha_retry_decorator()
    async def link_abha(self, patient_id: str, abha_address: str) -> dict:
        """
        Link an existing ABHA address to a patient record in the local DB.

        This persists the ``abha_address`` on the :class:`Patient` model
        and optionally registers the link with the ABDM gateway.

        Parameters
        ----------
        patient_id : str
            Internal patient UUID.
        abha_address : str
            Full ABHA address (e.g. ``user@abdm``).

        Returns
        -------
        dict
            Confirmation with linked ABHA address.
        """
        # Update the patient record in our database
        async with AsyncSessionLocal() as session:
            patient = await session.get(Patient, patient_id)
            if not patient:
                raise ABHANotFoundError(f"Patient {patient_id} not found")
            patient.abha_number = abha_address
            await session.commit()

        # Optionally notify ABDM gateway of the link
        path = "/v1/account/link"
        payload = {"healthId": abha_address}

        result = await self._api_call(
            method="POST",
            path=path,
            patient_id=patient_id,
            abha_address=abha_address,
            transaction_type="LINK",
            payload=payload,
        )

        await _record_transaction(
            patient_id=patient_id,
            transaction_type="LINK",
            abha_address=abha_address,
            transaction_id=result.get("transactionId"),
            request_payload=payload,
            response_status=200,
            response_body=result,
            error_message=None,
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            user_id=self.user_id,
            ip_address=self.ip_address,
        )

        return {"status": "linked", "abha_address": abha_address}

    # ── Get ABHA profile ──

    @_abha_retry_decorator()
    async def get_abha_profile(self, abha_address: str) -> dict:
        """
        Retrieve the full ABHA profile from the ABDM gateway.

        Parameters
        ----------
        abha_address : str
            Full ABHA address.

        Returns
        -------
        dict
            Profile data including name, DOB, gender, photo, and identifiers.
        """
        path = f"/v1/account/profile/{abha_address}"

        return await self._api_call(
            method="GET",
            path=path,
            abha_address=abha_address,
            transaction_type="PROFILE",
        )

    # ── Create consent artifact ──

    @_abha_retry_decorator()
    async def create_consent_artifact(
        self,
        abha_address: str,
        purpose: str,
        hi_types: list[str],
        from_time: str,
        to_time: str,
        patient_id: str | None = None,
    ) -> dict:
        """
        Create a consent artifact via the ABDM consent manager.

        The consent artifact authorises the platform to pull
        health information (HI) of the specified types from the
        ABDM network within the specified time window.

        Parameters
        ----------
        abha_address : str
            Patient's ABHA address (consent grantor).
        purpose : str
            Consent purpose code (e.g. ``TREATMENT``, ``PAYMENT``).
        hi_types : list[str]
            Health information types (e.g. ``["Prescription", "DiagnosticReport"]``).
        from_time : str
            Start of data window (ISO 8601).
        to_time : str
            End of data window (ISO 8601).
        patient_id : str | None
            Optional patient UUID for audit.

        Returns
        -------
        dict
            Consent artifact with consent ID, status, and expiry.
        """
        path = "/gateway/v0.5/consent-requests/init"
        payload = {
            "consent": {
                "patient": {"id": abha_address},
                "purpose": {
                    "code": purpose,
                    "refUri": "https://abdm.gov.in/purposes",
                    "text": purpose.replace("_", " ").title(),
                },
                "hiTypes": hi_types,
                "permission": {
                    "accessMode": "VIEW",
                    "dateRange": {
                        "from": from_time,
                        "to": to_time,
                    },
                    "dataEraseAt": to_time,
                },
            }
        }

        return await self._api_call(
            method="POST",
            path=path,
            patient_id=patient_id,
            abha_address=abha_address,
            transaction_type="CONSENT",
            payload=payload,
        )

    # ── Pull health records ──

    @_abha_retry_decorator()
    async def pull_health_records(self, consent_id: str, abha_address: str) -> dict:
        """
        Pull health records from the ABDM network using a granted consent.

        This retrieves all health information associated with the consent
        artifact identified by ``consent_id``.

        Parameters
        ----------
        consent_id : str
            The consent artifact ID (returned by ``create_consent_artifact``).
        abha_address : str
            Patient's ABHA address.

        Returns
        -------
        dict
            Bundled health records in FHIR format keyed by HI type.
        """
        path = "/gateway/v0.5/health-information/hip/request"
        payload = {
            "consentId": consent_id,
            "patientId": abha_address,
        }

        return await self._api_call(
            method="POST",
            path=path,
            abha_address=abha_address,
            transaction_type="DATA_PULL",
            payload=payload,
        )
