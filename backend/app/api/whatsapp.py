"""
HealthBridge Platform — WhatsApp Webhook API Routes

Provides endpoints for WhatsApp message ingestion from multiple providers:

  Meta Cloud API (WhatsApp Business API)
    GET  /api/v1/whatsapp/webhook   ← verification
    POST /api/v1/whatsapp/webhook   ← incoming messages

  Twilio WhatsApp Sandbox
    POST /api/v1/whatsapp/twilio-webhook  ← incoming messages

When a user sends a photo/PDF of a medical document via WhatsApp,
the webhook processes it through the ingestion pipeline and sends
a summary reply back.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import PlainTextResponse, JSONResponse

from app.services.whatsapp_bridge import (
    META_VERIFY_TOKEN,
    verify_meta_webhook,
    parse_meta_message,
    parse_twilio_message,
    download_meta_media,
    download_twilio_media,
    process_whatsapp_document,
    send_meta_text,
    send_twilio_reply,
)

logger = logging.getLogger("healthbridge.api.whatsapp")

router = APIRouter(prefix="/api/v1/whatsapp", tags=["WhatsApp Webhook"])


# ══════════════════════════════════════════════════
# Meta Cloud API — Webhook Verification (GET)
# ══════════════════════════════════════════════════


@router.get("/webhook", include_in_schema=False)
async def meta_webhook_verify(
    request: Request,
):
    """Handle Meta Cloud API webhook verification.

    Meta sends a GET request with ?hub.mode=subscribe&hub.verify_token=...&hub.challenge=...
    We must echo back the challenge if the token matches.
    """
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    status_code, response = verify_meta_webhook(mode, token, challenge)

    if status_code == 200:
        # Meta expects the raw challenge string, not JSON
        from fastapi.responses import Response
        return Response(content=challenge, media_type="text/plain")

    return JSONResponse(
        status_code=status_code,
        content=response if isinstance(response, dict) else {"error": response},
    )


# ══════════════════════════════════════════════════
# Meta Cloud API — Incoming Messages (POST)
# ══════════════════════════════════════════════════


@router.post("/webhook")
async def meta_webhook_message(request: Request):
    """Receive incoming WhatsApp messages via Meta Cloud API webhook.

    Processes image/document messages through the ingestion pipeline
    and replies with a structured summary.
    """
    body = await request.json()
    logger.debug(f"Meta webhook received: {json.dumps(body)[:500]}...")

    # Parse messages
    messages = parse_meta_message(body)
    if not messages:
        # Not a message notification (status update, etc.) — still return 200
        logger.debug("No user messages in webhook payload")
        return {"status": "ok"}

    # Process each message (usually 1 at a time from WhatsApp)
    for msg in messages:
        sender = msg["sender"]
        media_id = msg.get("media_id")
        media_type = msg.get("media_type")
        filename = msg.get("filename") or f"whatsapp_media.{media_type or 'jpg'}"
        caption = msg.get("caption")

        if not media_id:
            # Text message without media — nothing to process
            logger.info(f"Ignoring text-only message from {sender}: {msg.get('text','')[:50]}")
            continue

        # Only process images and documents (PDF)
        if media_type not in ("image", "document"):
            logger.info(f"Ignoring unsupported media type from {sender}: {media_type}")
            continue

        # Download media
        media_bytes = await download_meta_media(media_id)
        if media_bytes is None:
            logger.error(f"Failed to download media {media_id} from {sender}")
            continue

        # Run ingestion pipeline
        result = await process_whatsapp_document(
            media_bytes=media_bytes,
            filename=filename,
            sender=sender,
            source="meta",
        )

        # Send reply
        reply_text = result.get("reply_text", "Processing completed.")
        await send_meta_text(sender, reply_text)

    # Always return 200 to Meta (even if processing fails — they'll retry otherwise)
    return {"status": "ok"}


# ══════════════════════════════════════════════════
# Twilio WhatsApp Sandbox — Incoming Messages (POST)
# ══════════════════════════════════════════════════


@router.post("/twilio-webhook")
async def twilio_webhook_message(request: Request):
    """Receive incoming WhatsApp messages via Twilio webhook.

    Twilio sends form-encoded POST data with media URLs.
    """
    form = await request.form()
    form_dict = dict(form)
    logger.debug(f"Twilio webhook received: {json.dumps(form_dict, default=str)[:500]}...")

    msg = parse_twilio_message(form_dict)
    if msg is None:
        # Status callback — ignore
        return PlainTextResponse("OK")

    sender = msg.get("sender", "")
    text_body = msg.get("text", "")
    media_items = msg.get("media", [])

    if not media_items:
        logger.info(f"Ignoring text-only message from {sender}: {text_body[:50]}")
        return PlainTextResponse("OK")

    for media in media_items:
        media_url = media.get("url", "")
        content_type = media.get("content_type", "image/jpeg")

        if "pdf" in content_type:
            filename = f"twilio_document_{sender}.pdf"
        else:
            filename = f"twilio_image_{sender}.jpg"

        # Download media
        media_bytes = await download_twilio_media(media_url)
        if media_bytes is None:
            logger.error(f"Failed to download Twilio media from {sender}")
            continue

        # Run ingestion pipeline
        result = await process_whatsapp_document(
            media_bytes=media_bytes,
            filename=filename,
            sender=sender,
            source="twilio",
        )

        # Send reply
        reply_text = result.get("reply_text", "Processing completed.")
        await send_twilio_reply(sender, reply_text)

    return PlainTextResponse("OK")


# ══════════════════════════════════════════════════
# Status & Health
# ══════════════════════════════════════════════════


@router.get("/status")
async def whatsapp_status():
    """Check WhatsApp bridge configuration status."""
    from app.config import settings

    meta_configured = bool(settings.WHATSAPP_ACCESS_TOKEN and settings.WHATSAPP_PHONE_NUMBER_ID)
    twilio_configured = bool(settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN)

    return {
        "meta_cloud_api": {
            "configured": meta_configured,
            "phone_number_id": settings.WHATSAPP_PHONE_NUMBER_ID[:10] + "..." if settings.WHATSAPP_PHONE_NUMBER_ID else None,
            "webhook_url": "/api/v1/whatsapp/webhook",
        },
        "twilio": {
            "configured": twilio_configured,
            "webhook_url": "/api/v1/whatsapp/twilio-webhook",
        },
        "ocr_enabled": settings.OCR_ENABLED,
        "ai_extraction_configured": bool(settings.AI_EXTRACTION_API_KEY),
    }
