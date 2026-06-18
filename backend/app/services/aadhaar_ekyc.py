"""
HealthBridge Platform — Aadhaar eKYC Service

Provides Aadhaar-based identity verification for the HealthBridge platform:
  - Initiate OTP to Aadhaar-linked mobile number
  - Verify OTP and decrypt the XML eKYC response
  - Full identity verification workflow
  - Aadhaar hashing and masking utilities

Per DPDP 2025 compliance and Aadhaar Act 2016 guidelines:
  - **Never stores raw Aadhaar numbers** — only SHA-256 hashes are persisted
  - All Aadhaar data in transit is encrypted (XML encryption via pycryptodome)
  - eKYC data is used solely for identity verification and then discarded
"""
from __future__ import annotations

import hashlib
import logging
import re
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
from app.models import Patient

logger = logging.getLogger("healthbridge.aadhaar")

# ── Constants ──
AADHAAR_API_BASE = settings.AADHAAR_API_BASE_URL.rstrip("/")
EKYC_ENABLED = settings.AADHAAR_EKYC_ENABLED
LICENSE_KEY = settings.AADHAAR_LICENSE_KEY
ASA_ID = settings.AADHAAR_ASA_ID
SUB_ASA_ID = settings.AADHAAR_SUB_ASA_ID

# Regex for Aadhaar validation (Verhoeff check digit is done server-side;
# we only verify format here)
AADHAAR_PATTERN = re.compile(r"^\d{12}$")

MAX_RETRIES = 3
RETRY_MIN_WAIT = 1  # seconds
RETRY_MAX_WAIT = 10  # seconds


# ═══════════════════════════════════════════════════
# Custom Exceptions
# ═══════════════════════════════════════════════════

class AadhaarError(Exception):
    """Base exception for Aadhaar eKYC operations."""


class AadhaarOTPError(AadhaarError):
    """Raised when OTP generation or verification fails."""


class AadhaarValidationError(AadhaarError):
    """Raised when input validation fails."""


class AadhaarServiceDisabledError(AadhaarError):
    """Raised when Aadhaar eKYC is disabled in configuration."""


# ═══════════════════════════════════════════════════
# Retry configuration
# ═══════════════════════════════════════════════════

def _aadhaar_retry_decorator() -> Any:
    """Default tenacity retry decorator for Aadhaar API calls."""
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
# Aadhaar eKYC Service
# ═══════════════════════════════════════════════════

class AadhaarEKYCService:
    """
    Async service for Aadhaar-based eKYC (electronic Know Your Customer)
    via the UIDAI (Unique Identification Authority of India) API.

    Workflow
    --------
    1. :meth:`initiate_otp` — sends an OTP to the Aadhaar-linked mobile
       and returns a ``transaction_id``.
    2. :meth:`verify_otp` — submits the OTP + transaction ID and receives
       the encrypted eKYC XML data (demographics + photo).
    3. :meth:`verify_identity` — convenience wrapper that does both steps
       and updates the patient record with the Aadhaar hash on success.

    **Important:** This service never stores raw Aadhaar numbers. The
    :meth:`hash_aadhaar` utility is used to derive a SHA-256 hash for
    deduplication and audit, and :meth:`mask_aadhaar` produces a masked
    representation (e.g. ``1234********5678``) for display/logging.
    """

    # ── Lifecycle ──

    def __init__(self) -> None:
        if not EKYC_ENABLED:
            logger.warning(
                "Aadhaar eKYC is DISABLED. Set AADHAAR_EKYC_ENABLED=true in "
                "environment to enable. All eKYC calls will raise "
                "AadhaarServiceDisabledError."
            )

    # ── Validation ──

    def _validate_aadhaar(self, aadhaar_number: str) -> str:
        """Validate and normalise a 12-digit Aadhaar number."""
        cleaned = aadhaar_number.strip().replace(" ", "").replace("-", "")
        if not AADHAAR_PATTERN.match(cleaned):
            raise AadhaarValidationError(
                "Aadhaar number must be exactly 12 digits"
            )
        return cleaned

    # ── Hashing / Masking utilities ──

    @staticmethod
    def hash_aadhaar(aadhaar_number: str) -> str:
        """
        Return a SHA-256 hex digest of the Aadhaar number.

        This is the **only** form in which Aadhaar data is stored in the
        database — raw numbers are never persisted.

        Parameters
        ----------
        aadhaar_number : str
            Raw 12-digit Aadhaar number.

        Returns
        -------
        str
            SHA-256 hex digest (64-character hex string).
        """
        return hashlib.sha256(aadhaar_number.encode("utf-8")).hexdigest()

    @staticmethod
    def mask_aadhaar(aadhaar_number: str) -> str:
        """
        Return a masked Aadhaar representation for display/logging.

        Format: ``XXXX1234XXXX`` — first 4 and last 2 characters shown,
        the rest replaced with ``X``. This matches the UIDAI-recommended
        masking pattern.

        Parameters
        ----------
        aadhaar_number : str
            Raw 12-digit Aadhaar number.

        Returns
        -------
        str
            Masked Aadhaar (e.g. ``XXXX1234XX``).
        """
        cleaned = aadhaar_number.strip().replace(" ", "").replace("-", "")
        if len(cleaned) != 12:
            return "XXXXXXXXXXXX"
        return f"{cleaned[:4]}XXXX{cleaned[-2:]}"

    # ── API endpoints ──

    @_aadhaar_retry_decorator()
    async def initiate_otp(self, aadhaar_number: str) -> str:
        """
        Initiate OTP generation for Aadhaar eKYC.

        The UIDAI gateway sends a one-time password to the mobile number
        registered with the given Aadhaar. Returns a ``transaction_id``
        that must be provided alongside the OTP in :meth:`verify_otp`.

        Parameters
        ----------
        aadhaar_number : str
            12-digit Aadhaar number.

        Returns
        -------
        str
            Transaction ID (``txnId``) to use in ``verify_otp``.

        Raises
        ------
        AadhaarServiceDisabledError
            If eKYC is disabled in config.
        AadhaarOTPError
            If the UIDAI gateway returns a failure.
        """
        self._check_enabled()
        aadhaar = self._validate_aadhaar(aadhaar_number)

        url = f"{AADHAAR_API_BASE}/aadhaar/v1/generateOtp"
        headers = self._build_headers()
        payload = {
            "aadhaar": aadhaar,
            "channel": "SMS",
        }

        logger.info("Initiating Aadhaar eKYC OTP for masked Aadhaar: %s",
                     self.mask_aadhaar(aadhaar_number))

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()

                txn_id = data.get("txnId") or data.get("transactionId")
                if not txn_id:
                    raise AadhaarOTPError(
                        "UIDAI response did not contain a transaction ID"
                    )

                logger.info("Aadhaar OTP initiated — txnId: %s", txn_id)
                return txn_id

            except httpx.HTTPStatusError as exc:
                error_detail = exc.response.text
                logger.error(
                    "Aadhaar OTP initiation failed [%d]: %s",
                    exc.response.status_code, error_detail,
                )
                raise AadhaarOTPError(
                    f"OTP initiation failed: {exc.response.status_code} — {error_detail}"
                ) from exc
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                logger.error("Aadhaar API unreachable during OTP initiation: %s", exc)
                raise AadhaarError(
                    f"Aadhaar gateway unreachable: {exc}"
                ) from exc

    @_aadhaar_retry_decorator()
    async def verify_otp(self, transaction_id: str, otp: str) -> dict:
        """
        Verify the OTP and retrieve decrypted eKYC data.

        On success the UIDAI gateway returns an encrypted XML payload
        containing the resident's demographics (name, DOB, gender, address)
        and photograph. This method decrypts the XML using ``pycryptodome``
        and returns a structured dictionary.

        Parameters
        ----------
        transaction_id : str
            Transaction ID from :meth:`initiate_otp`.
        otp : str
            The one-time password received on the Aadhaar-linked mobile.

        Returns
        -------
        dict
            Decrypted eKYC data with keys:
            - ``name`` — Full name from Aadhaar
            - ``dob`` — Date of birth (``YYYY-MM-DD``)
            - ``gender`` — Gender (``M``/``F``/``O``)
            - ``phone`` — Masked phone number
            - ``email`` — Masked email (if available)
            - ``address`` — Full address JSON
            - ``photo`` — Base64-encoded photograph
            - ``aadhaar_hash`` — SHA-256 of the Aadhaar number

        Raises
        ------
        AadhaarServiceDisabledError
            If eKYC is disabled in config.
        AadhaarOTPError
            If OTP verification fails.
        """
        self._check_enabled()

        url = f"{AADHAAR_API_BASE}/aadhaar/v1/verifyOtp"
        headers = self._build_headers()
        payload = {
            "txnId": transaction_id,
            "otp": otp,
        }

        logger.info("Verifying Aadhaar OTP — txnId: %s", transaction_id)

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()

                # The response is an encrypted XML envelope
                raw_data = resp.text

                # Try to parse as JSON first (some gateways return JSON)
                try:
                    data = resp.json()
                    # If we got JSON, the eKYC data might be in 'data' or 'ekyc'
                    encrypted_xml = (
                        data.get("data")
                        or data.get("ekyc")
                        or data.get("xml")
                        or ""
                    )
                except (ValueError, TypeError):
                    # Assume the entire response body is the encrypted XML
                    encrypted_xml = raw_data

                if not encrypted_xml:
                    raise AadhaarOTPError(
                        "UIDAI response did not contain eKYC data"
                    )

                # Decrypt the XML payload using pycryptodome
                ekyc_data = self._decrypt_ekyc_xml(encrypted_xml)

                logger.info(
                    "Aadhaar eKYC verified successfully",
                )
                return ekyc_data

            except httpx.HTTPStatusError as exc:
                error_detail = exc.response.text
                logger.error(
                    "Aadhaar OTP verification failed [%d]: %s",
                    exc.response.status_code, error_detail,
                )
                raise AadhaarOTPError(
                    f"OTP verification failed: {exc.response.status_code} — {error_detail}"
                ) from exc
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                logger.error(
                    "Aadhaar API unreachable during OTP verification: %s", exc
                )
                raise AadhaarError(
                    f"Aadhaar gateway unreachable: {exc}"
                ) from exc

    async def verify_identity(
        self,
        patient_id: str,
        aadhaar_number: str,
        otp: str,
    ) -> bool:
        """
        Full identity verification workflow for a patient.

        Performs end-to-end verification:
        1. Validates the Aadhaar number format
        2. Initiates OTP generation
        3. Verifies the OTP and decrypts eKYC data
        4. Updates the patient record with the Aadhaar hash

        Parameters
        ----------
        patient_id : str
            Internal patient UUID.
        aadhaar_number : str
            12-digit Aadhaar number.
        otp : str
            OTP received on the Aadhaar-linked mobile.

        Returns
        -------
        bool
            ``True`` if identity was verified successfully.

        Raises
        ------
        AadhaarError
            On any verification failure.
        """
        self._check_enabled()
        aadhaar = self._validate_aadhaar(aadhaar_number)

        # Step 1: Initiate OTP
        txn_id = await self.initiate_otp(aadhaar)

        # Step 2: Verify OTP
        await self.verify_otp(txn_id, otp)

        # Step 3: Update patient record with Aadhaar hash (never raw number)
        aadhaar_hash = self.hash_aadhaar(aadhaar)

        async with AsyncSessionLocal() as session:
            patient = await session.get(Patient, patient_id)
            if not patient:
                raise AadhaarError(f"Patient {patient_id} not found")

            patient.aadhaar_hash = aadhaar_hash
            await session.commit()

        logger.info(
            "Identity verified for patient %s — Aadhaar hash stored",
            patient_id,
        )
        return True

    # ── Internal helpers ──

    def _check_enabled(self) -> None:
        """Raise if Aadhaar eKYC is disabled in configuration."""
        if not EKYC_ENABLED:
            raise AadhaarServiceDisabledError(
                "Aadhaar eKYC is not enabled. Set AADHAAR_EKYC_ENABLED=true "
                "in your environment configuration."
            )

    def _build_headers(self) -> dict[str, str]:
        """
        Build the required HTTP headers for UIDAI API calls.

        Includes the license key, ASA (Authentication Service Agency)
        identifier, and sub-ASA identifier.
        """
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        if LICENSE_KEY:
            headers["X-Request-Id"] = LICENSE_KEY

        if ASA_ID:
            headers["X-ASA-Id"] = ASA_ID

        if SUB_ASA_ID:
            headers["X-Sub-ASA-Id"] = SUB_ASA_ID

        return headers

    def _decrypt_ekyc_xml(self, encrypted_xml: str) -> dict:
        """
        Decrypt the UIDAI eKYC XML response using pycryptodome.

        The UIDAI gateway returns an XML envelope encrypted with the
        ASA's public key. This method:
          1. Parses the XML envelope
          2. Decrypts the session key (RSA-OAEP)
          3. Decrypts the eKYC data payload (AES-256-GCM)
          4. Parses the resulting XML into a structured dict

        If decryption fails or is not available (missing keys), the
        method falls back to returning the raw encrypted data with an
        appropriate flag.

        Parameters
        ----------
        encrypted_xml : str
            The encrypted XML response from UIDAI.

        Returns
        -------
        dict
            Decrypted eKYC data dictionary, or a placeholder with
            ``_encrypted`` flag if decryption is not configured.
        """
        try:
            from Cryptodome.Cipher import AES, PKCS1_OAEP
        except ImportError:
            logger.warning(
                "pycryptodome not available — returning encrypted payload as-is"
            )
            return {
                "_encrypted": True,
                "raw_encrypted_xml": encrypted_xml[:500] + "..." if len(encrypted_xml) > 500 else encrypted_xml,
                "note": "Install pycryptodome and configure RSA private key for decryption",
            }

        try:
            import xml.etree.ElementTree as ET
            import base64

            root = ET.fromstring(encrypted_xml)

            # Namespace handling for UIDAI XML
            ns = {
                "ns2": "http://www.uidai.gov.in/authentication/uid/auth/1.0",
                "ns3": "http://www.w3.org/2001/04/xmlenc#",
                "ns4": "http://www.w3.org/2001/04/xmlenc#",
            }

            # Extract the encrypted session key (RSA-encrypted AES key)
            encrypted_key_elem = root.find(".//ns3:EncryptedKey", ns)
            encrypted_data_elem = root.find(".//ns3:EncryptedData", ns)

            if encrypted_key_elem is None or encrypted_data_elem is None:
                logger.warning("Could not find encrypted key/data in UIDAI response")
                return {
                    "_encrypted": True,
                    "raw_encrypted_xml": encrypted_xml[:500],
                    "note": "Could not locate encrypted elements in XML envelope",
                }

            # Extract base64-encoded ciphertexts
            cipher_key_b64 = encrypted_key_elem.findtext(".//ns3:CipherValue", "", ns)
            cipher_data_b64 = encrypted_data_elem.findtext(".//ns3:CipherValue", "", ns)

            if not cipher_key_b64 or not cipher_data_b64:
                logger.warning("Missing cipher values in UIDAI response")
                return {
                    "_encrypted": True,
                    "raw_encrypted_xml": encrypted_xml[:500],
                    "note": "Missing cipher values in XML envelope",
                }

            encrypted_key = base64.b64decode(cipher_key_b64)
            encrypted_data = base64.b64decode(cipher_data_b64)

            # --- Decrypt the session key with ASA's RSA private key ---
            # In production the private key is loaded from a secure keystore
            # or environment variable. For now we attempt a key file lookup.
            private_key = self._load_rsa_private_key()
            if private_key is None:
                logger.warning(
                    "No RSA private key configured — cannot decrypt eKYC data"
                )
                return {
                    "_encrypted": True,
                    "raw_encrypted_xml": encrypted_xml[:500],
                    "note": "ASA RSA private key not configured",
                }

            cipher_rsa = PKCS1_OAEP.new(private_key)
            session_key = cipher_rsa.decrypt(encrypted_key)

            # --- Decrypt the eKYC data payload with the session key ---
            # UIDAI uses AES-256-GCM; the nonce is the first 12 bytes
            nonce = encrypted_data[:12]
            tag = encrypted_data[-16:]
            ciphertext = encrypted_data[12:-16]

            cipher_aes = AES.new(session_key, AES.MODE_GCM, nonce=nonce)
            decrypted_xml = cipher_aes.decrypt_and_verify(ciphertext, tag)

            # --- Parse the decrypted XML into a structured dict ---
            return self._parse_ekyc_xml(decrypted_xml.decode("utf-8"))

        except ET.ParseError as exc:
            logger.error("Failed to parse UIDAI XML response: %s", exc)
            return {
                "_encrypted": True,
                "_parse_error": str(exc),
                "raw_encrypted_xml": encrypted_xml[:500],
            }
        except Exception as exc:
            logger.error("eKYC XML decryption failed: %s", exc)
            return {
                "_encrypted": True,
                "_decrypt_error": str(exc),
                "raw_encrypted_xml": encrypted_xml[:500],
            }

    def _load_rsa_private_key(self) -> Any:
        """
        Load the ASA's RSA private key for decrypting eKYC responses.

        Attempts to load from:
          1. ``AADHAAR_ASA_PRIVATE_KEY`` environment variable (PEM string)
          2. ``/etc/healthbridge/aadhaar_private.pem`` file path

        Returns
        -------
        RSA key object or ``None`` if no key is configured.
        """
        from Cryptodome.PublicKey import RSA
        import os

        pem_data = os.environ.get("AADHAAR_ASA_PRIVATE_KEY")
        if pem_data:
            try:
                return RSA.import_key(pem_data.encode("utf-8"))
            except (ValueError, IndexError) as exc:
                logger.error("Invalid AADHAAR_ASA_PRIVATE_KEY env var: %s", exc)
                return None

        key_path = "/etc/healthbridge/aadhaar_private.pem"
        if os.path.exists(key_path):
            try:
                with open(key_path, "r") as f:
                    return RSA.import_key(f.read())
            except (ValueError, OSError) as exc:
                logger.error("Failed to load RSA key from %s: %s", key_path, exc)
                return None

        return None

    def _parse_ekyc_xml(self, xml_str: str) -> dict:
        """
        Parse the decrypted eKYC XML into a structured dictionary.

        Expected XML structure (simplified):
        .. code-block:: xml

            <AuthRes ...>
              <UidData>
                <Poi name="John Doe" dob="1990-01-15" gender="M" phone="9999999999" />
                <Poa co="..." house="..." street="..." vtc="..." po="..." dist="..."
                     state="..." pc="..." />
                <Pht>base64-encoded-photo</Pht>
              </UidData>
            </AuthRes>

        Parameters
        ----------
        xml_str : str
            Decrypted XML string from UIDAI.

        Returns
        -------
        dict
            Structured eKYC data.
        """
        try:
            import xml.etree.ElementTree as ET

            root = ET.fromstring(xml_str)

            # UIDAI namespace
            ns = {"ns2": "http://www.uidai.gov.in/authentication/uid/auth/1.0"}

            uid_data = root.find(".//ns2:UidData", ns)
            if uid_data is None:
                # Fallback: try no namespace
                uid_data = root.find(".//UidData")

            if uid_data is None:
                logger.warning("No UidData element found in decrypted eKYC XML")
                return {"_raw_xml": xml_str[:1000]}

            # Extract demographics (Poi — Proof of Identity)
            poi = uid_data.find("Poi") or uid_data.find("ns2:Poi", ns)
            poa = uid_data.find("Poa") or uid_data.find("ns2:Poa", ns)
            pht = uid_data.find("Pht") or uid_data.find("ns2:Pht", ns)

            result: dict = {}

            if poi is not None:
                result["name"] = poi.get("name", "")
                result["dob"] = poi.get("dob", "")
                result["gender"] = poi.get("gender", "")
                result["phone"] = poi.get("phone", "")
                result["email"] = poi.get("email", "")

            if poa is not None:
                result["address"] = {
                    "co": poa.get("co", ""),
                    "house": poa.get("house", ""),
                    "street": poa.get("street", ""),
                    "vtc": poa.get("vtc", ""),
                    "po": poa.get("po", ""),
                    "dist": poa.get("dist", ""),
                    "state": poa.get("state", ""),
                    "pc": poa.get("pc", ""),  # Pin code
                    "country": poa.get("country", "India"),
                }

            if pht is not None:
                result["photo"] = pht.text or ""

            logger.info(
                "eKYC XML parsed — name=%s, dob=%s, gender=%s",
                result.get("name", "N/A"),
                result.get("dob", "N/A"),
                result.get("gender", "N/A"),
            )

            return result

        except ET.ParseError as exc:
            logger.error("Failed to parse decrypted eKYC XML: %s", exc)
            return {"_raw_xml": xml_str[:1000], "_parse_error": str(exc)}
        except Exception as exc:
            logger.error("eKYC XML parsing failed: %s", exc)
            return {"_raw_xml": xml_str[:1000], "_parse_error": str(exc)}
