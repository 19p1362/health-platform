"""
HealthBridge Platform — WhatsApp Bridge Service

Handles inbound WhatsApp messages with media attachments (photos, PDFs)
and processes them through the document ingestion pipeline.

Supports two webhook formats:
  - Meta Cloud API (WhatsApp Business API) — standard
  - Twilio WhatsApp Sandbox — alternative

When a user sends a prescription/lab report photo via WhatsApp:
  1. Webhook receives the message
  2. Media is downloaded (Meta or Twilio)
  3. Document goes through OCR + AI extraction + FHIR conversion
  4. A reply is sent back via WhatsApp with a summary
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from io import BytesIO
from typing import Literal

import httpx

from app.config import settings
from app.services.document_ingestion import process_document

logger = logging.getLogger("healthbridge.whatsapp_bridge")

# ── Webhook Verification ──

META_VERIFY_TOKEN = settings.WHATSAPP_VERIFY_TOKEN or "healthbridge-verify-2026"


def verify_meta_webhook(mode: str | None, token: str | None, challenge: str | None) -> tuple[int, dict | str]:
    """Handle Meta Cloud API webhook verification (GET /webhook).

    Returns (status_code, response_body_or_text).
    """
    if mode == "subscribe" and token == META_VERIFY_TOKEN and challenge:
        logger.info("WhatsApp webhook verified by Meta")
        return 200, challenge  # Meta expects raw challenge string
    return 403, {"error": "Verification failed"}


# ── Media Download ──


async def download_meta_media(media_id: str) -> bytes | None:
    """Download media from Meta Cloud API by media ID.

    Uses the configured WHATSAPP_ACCESS_TOKEN to authenticate.
    """
    if not settings.WHATSAPP_ACCESS_TOKEN:
        logger.warning("WHATSAPP_ACCESS_TOKEN not configured — cannot download media")
        return None

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            # Step 1: Get media URL
            resp = await client.get(
                f"https://graph.facebook.com/v21.0/{media_id}",
                headers={"Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}"},
            )
            resp.raise_for_status()
            media_info = resp.json()
            media_url = media_info.get("url")
            if not media_url:
                logger.error(f"No URL in Meta media info: {media_info}")
                return None

            # Step 2: Download actual media bytes
            media_resp = await client.get(
                media_url,
                headers={"Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}"},
            )
            media_resp.raise_for_status()
            logger.info(f"Downloaded media {media_id} ({len(media_resp.content)} bytes)")
            return media_resp.content
    except Exception as e:
        logger.error(f"Failed to download Meta media {media_id}: {e}")
        return None


async def download_twilio_media(media_url: str) -> bytes | None:
    """Download media from Twilio by media URL."""
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
        logger.warning("Twilio credentials not configured — cannot download media")
        return None

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                media_url,
                auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
            )
            resp.raise_for_status()
            logger.info(f"Downloaded Twilio media ({len(resp.content)} bytes)")
            return resp.content
    except Exception as e:
        logger.error(f"Failed to download Twilio media: {e}")
        return None


# ── Send Reply (Meta Cloud API) ──


async def send_meta_text(to: str, text: str) -> bool:
    """Send a text message reply via Meta Cloud API.

    Uses the phone-number-id to send from.
    """
    if not settings.WHATSAPP_PHONE_NUMBER_ID or not settings.WHATSAPP_ACCESS_TOKEN:
        logger.warning("WhatsApp not configured — cannot send reply")
        return False

    url = f"https://graph.facebook.com/v21.0/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"preview_url": False, "body": text},
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            logger.info(f"WhatsApp reply sent to {to}")
            return True
    except Exception as e:
        logger.error(f"Failed to send WhatsApp reply: {e}")
        return False


async def send_twilio_reply(to: str, body: str) -> bool:
    """Send a text reply via Twilio WhatsApp Sandbox."""
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
        logger.warning("Twilio not configured — cannot send reply")
        return False

    from_account = f"whatsapp:{settings.TWILIO_WHATSAPP_NUMBER}"
    to_account = f"whatsapp:{to}"

    url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Messages.json"

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                url,
                auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
                data={"From": from_account, "To": to_account, "Body": body},
            )
            resp.raise_for_status()
            logger.info(f"Twilio reply sent to {to}")
            return True
    except Exception as e:
        logger.error(f"Failed to send Twilio reply: {e}")
        return False


# ── Pipeline Handler ──


async def process_whatsapp_document(
    media_bytes: bytes,
    filename: str,
    sender: str,
    source: Literal["meta", "twilio"] = "meta",
) -> dict:
    """Run the full ingestion pipeline on a WhatsApp media attachment.

    Returns a summary dict suitable for the reply message.
    """
    logger.info(f"Processing WhatsApp document from {sender}: {filename}")

    # Determine document type from filename or default to general
    filename_lower = filename.lower()
    if any(kw in filename_lower for kw in ["presc", "rx"]):
        doc_type = "prescription"
    elif any(kw in filename_lower for kw in ["lab", "report", "test"]):
        doc_type = "lab_report"
    elif any(kw in filename_lower for kw in ["bill", "invoice", "pharmacy"]):
        doc_type = "pharmacy_bill"
    elif any(kw in filename_lower for kw in ["discharge", "summary"]):
        doc_type = "discharge_summary"
    else:
        doc_type = "general"

    # Run pipeline
    result = await process_document(
        image_bytes=media_bytes,
        filename=filename,
        document_type=doc_type,
    )

    # Build reply summary
    status = result.get("status", "FAILED")
    extracted = result.get("extracted", {})
    clinical = extracted.get("clinical", {})
    patient = extracted.get("patient", {})
    document = extracted.get("document", {})

    if status == "PROCESSED":
        patient_name = patient.get("name") or "Unknown"
        doc_date = document.get("date") or "Unknown date"
        medicines = clinical.get("medicines", [])
        diagnoses = clinical.get("diagnosis", [])
        lab_tests = clinical.get("lab_tests", [])

        lines = [f" HealthBridge - Document Processed"]
        lines.append(f" Patient: {patient_name}")
        lines.append(f" Date: {doc_date}")
        lines.append(f" Type: {document.get('type', 'unknown')}")

        if diagnoses:
            lines.append(f" Diagnosis: {', '.join(diagnoses[:3])}")

        if medicines:
            med_names = []
            for m in medicines[:5]:
                name = m.get("name", "")
                dose = m.get("dosage") or ""
                med_names.append(f"{name}" + (f" ({dose})" if dose else ""))
            lines.append(f" Medicines: {' | '.join(med_names)}")
            if len(medicines) > 5:
                lines.append(f" (+{len(medicines)-5} more)")

        if lab_tests:
            lab_summary = []
            for l in lab_tests[:4]:
                lab_summary.append(f"{l.get('name','?')}: {l.get('value','?')} {l.get('unit','')}")
            lines.append(f" Labs: {' | '.join(lab_summary)}")

        fhir_count = len(result.get("fhir_bundle", {}).get("entry", []))
        lines.append(f" FHIR: {fhir_count} resources created")
        lines.append(f" Confidence: {result.get('confidence_score', 0)}%")

        reply = "\n".join(lines)
    else:
        error = result.get("error_message", "Unknown error")
        reply = f" HealthBridge - Processing failed\nError: {error}\nPlease try sending the image again or contact support."

    return {
        "status": status,
        "reply_text": reply,
        "result": result,
    }


# ── Parse Incoming Messages ──


def parse_meta_message(payload: dict) -> list[dict]:
    """Parse a Meta Cloud API webhook payload into standardised message dicts.

    Each returned dict has:
      - sender: str (phone number)
      - message_id: str
      - media_id: str | None (if media message)
      - media_type: str | None (image, document, etc.)
      - filename: str | None
      - caption: str | None
      - text: str | None (if text message)
      - timestamp: str
    """
    messages: list[dict] = []

    entries = payload.get("entry", [])
    for entry in entries:
        changes = entry.get("changes", [])
        for change in changes:
            value = change.get("value", {})
            if "messages" not in value:
                continue

            for msg in value.get("messages", []):
                msg_type = msg.get("type", "text")
                sender = msg.get("from", "")
                msg_id = msg.get("id", "")
                timestamp = msg.get("timestamp", "")

                parsed: dict = {
                    "sender": sender,
                    "message_id": msg_id,
                    "timestamp": timestamp,
                    "media_id": None,
                    "media_type": None,
                    "filename": None,
                    "caption": None,
                    "text": None,
                }

                if msg_type == "text":
                    parsed["text"] = msg.get("text", {}).get("body", "")
                elif msg_type == "image":
                    parsed["media_id"] = msg.get("image", {}).get("id", "")
                    parsed["media_type"] = "image"
                    parsed["caption"] = msg.get("image", {}).get("caption", "")
                elif msg_type == "document":
                    parsed["media_id"] = msg.get("document", {}).get("id", "")
                    parsed["media_type"] = "document"
                    parsed["filename"] = msg.get("document", {}).get("filename", "")
                    parsed["caption"] = msg.get("document", {}).get("caption", "")
                elif msg_type == "audio":
                    parsed["media_id"] = msg.get("audio", {}).get("id", "")
                    parsed["media_type"] = "audio"

                messages.append(parsed)

    return messages


def parse_twilio_message(form_data: dict) -> dict | None:
    """Parse a Twilio WhatsApp webhook POST body into a standardised dict.

    Returns None if it's a status callback, not a user message.
    """
    # Filter out status callbacks
    if form_data.get("SmsStatus") or form_data.get("MessageStatus"):
        return None

    num_media = int(form_data.get("NumMedia", 0))
    sender = (form_data.get("From") or "").replace("whatsapp:", "").strip()
    body = form_data.get("Body", "")

    parsed: dict = {
        "sender": sender,
        "message_id": form_data.get("MessageSid", ""),
        "timestamp": form_data.get("", ""),
        "media": [],
        "text": body,
    }

    for i in range(num_media):
        media_url = form_data.get(f"MediaUrl{i}")
        media_type = form_data.get(f"MediaContentType{i}")
        if media_url:
            parsed["media"].append({
                "url": media_url,
                "content_type": media_type or "image/jpeg",
            })

    return parsed
