from __future__ import annotations
"""
WhatsApp client — supports two providers:

  • "greenapi"  — Green API (QR-based, no Facebook Business needed, free 3 months)
                  Sign up: green-api.com
  • "meta"      — Meta WhatsApp Cloud API (requires Facebook Business Portfolio)

Switch by setting WHATSAPP_PROVIDER in .env.
"""

import logging
from typing import Any

import httpx

from config import get_settings

logger = logging.getLogger(__name__)

_http_client: httpx.AsyncClient | None = None


def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=30.0)
    return _http_client


# ------------------------------------------------------------------
# Green API sender
# ------------------------------------------------------------------

async def _send_greenapi(phone: str, message: str) -> dict[str, Any]:
    """Send via Green API (instance-based, QR scan auth)."""
    settings = get_settings()
    if not settings.green_api_instance_id or not settings.green_api_token:
        logger.warning("Green API credentials not configured — message not sent")
        return {"error": True, "detail": "Green API credentials not configured"}

    # Green API expects phone as "919876543210@c.us"
    chat_id = f"{phone}@c.us"
    url = (
        f"https://api.green-api.com/waInstance{settings.green_api_instance_id}"
        f"/sendMessage/{settings.green_api_token}"
    )
    payload = {"chatId": chat_id, "message": message}

    client = _get_http_client()
    try:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        logger.info("Green API message sent: %s", data.get("idMessage", "?"))
        return data
    except httpx.HTTPStatusError as exc:
        logger.error("Green API HTTP error %s: %s", exc.response.status_code, exc.response.text)
        return {"error": True, "status": exc.response.status_code, "detail": exc.response.text}
    except httpx.RequestError as exc:
        logger.error("Green API request failed: %s", exc)
        return {"error": True, "detail": str(exc)}


# ------------------------------------------------------------------
# Meta Cloud API sender
# ------------------------------------------------------------------

async def _send_meta(phone: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Send via Meta WhatsApp Cloud API."""
    settings = get_settings()
    if not settings.whatsapp_phone_number_id or not settings.whatsapp_access_token:
        logger.warning("Meta WhatsApp credentials not configured — message not sent")
        return {"error": True, "detail": "Meta credentials not configured"}

    url = (
        f"https://graph.facebook.com/{settings.whatsapp_api_version}"
        f"/{settings.whatsapp_phone_number_id}/messages"
    )
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.whatsapp_access_token}",
    }

    client = _get_http_client()
    try:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        logger.info("Meta message sent: %s", data.get("messages", [{}])[0].get("id", "?"))
        return data
    except httpx.HTTPStatusError as exc:
        logger.error("Meta API HTTP error %s: %s", exc.response.status_code, exc.response.text)
        return {"error": True, "status": exc.response.status_code, "detail": exc.response.text}
    except httpx.RequestError as exc:
        logger.error("Meta API request failed: %s", exc)
        return {"error": True, "detail": str(exc)}


# ------------------------------------------------------------------
# Public API — provider-agnostic
# ------------------------------------------------------------------

async def send_text_message(phone: str, message: str) -> dict[str, Any]:
    """Send a plain text WhatsApp message.

    Args:
        phone: Recipient phone in E.164 without '+' (e.g. "919876543210").
        message: The text body.
    """
    settings = get_settings()

    if settings.whatsapp_provider == "greenapi":
        return await _send_greenapi(phone, message)

    # Meta Cloud API
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": phone,
        "type": "text",
        "text": {"preview_url": False, "body": message},
    }
    return await _send_meta(phone, payload)


async def send_interactive_message(
    phone: str,
    body_text: str,
    buttons: list[dict[str, str]],
) -> dict[str, Any]:
    """Send quick-reply buttons.

    Green API does not support interactive messages — falls back to plain text.
    Meta supports up to 3 buttons.
    """
    settings = get_settings()

    if settings.whatsapp_provider == "greenapi":
        # Green API has no button support — format as numbered text
        options = "\n".join(
            f"{i+1}. {btn['title']}" for i, btn in enumerate(buttons)
        )
        return await _send_greenapi(phone, f"{body_text}\n\n{options}")

    if len(buttons) > 3:
        buttons = buttons[:3]

    reply_buttons = [
        {"type": "reply", "reply": {"id": btn["id"], "title": btn["title"][:20]}}
        for btn in buttons
    ]
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": phone,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": body_text},
            "action": {"buttons": reply_buttons},
        },
    }
    return await _send_meta(phone, payload)


async def close_http_client() -> None:
    """Close the shared httpx.AsyncClient. Call during application shutdown."""
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None
        logger.info("httpx AsyncClient closed")


async def send_list_message(
    phone: str,
    body_text: str,
    button_text: str,
    sections: list[dict[str, Any]],
) -> dict[str, Any]:
    """Send a list-picker message.

    Green API does not support list messages — falls back to plain text.
    """
    settings = get_settings()

    if settings.whatsapp_provider == "greenapi":
        # Flatten all rows into a numbered list
        lines = [body_text, ""]
        n = 1
        for section in sections:
            for row in section.get("rows", []):
                lines.append(f"{n}. {row.get('title', '')}")
                n += 1
        return await _send_greenapi(phone, "\n".join(lines))

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": phone,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {"text": body_text},
            "action": {"button": button_text[:20], "sections": sections},
        },
    }
    return await _send_meta(phone, payload)
