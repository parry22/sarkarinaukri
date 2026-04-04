from __future__ import annotations
"""
FastAPI router for the WhatsApp webhook.

Handles verification (GET) and incoming messages (POST) from the
AiSensy / WhatsApp Cloud API.
"""

import logging
from typing import Any

from fastapi import APIRouter, Query, Request, Response

from config import get_settings
from database.connection import get_supabase
from database.models import Notification, OnboardingStep, UserProfile
from matching.eligibility_matcher import fetch_eligible_notifications_for_user
from bot.whatsapp_client import send_text_message
from bot.onboarding import handle_onboarding
from bot import message_templates as tpl

logger = logging.getLogger(__name__)

router = APIRouter()


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _get_or_create_user(phone: str) -> tuple[UserProfile, bool]:
    """Look up a user by phone; create a new row if not found.

    Returns (user, is_new).
    """
    supabase = get_supabase()
    response = (
        supabase.table("user_profiles")
        .select("*")
        .eq("phone", phone)
        .limit(1)
        .execute()
    )

    if response.data:
        return UserProfile(**response.data[0]), False

    # New user
    new_user = UserProfile(phone=phone)
    insert_data = new_user.model_dump(exclude_none=True)
    # Ensure date fields are serialised correctly
    for key in ("date_of_birth", "subscription_expires_at"):
        if key in insert_data and insert_data[key] is not None:
            insert_data[key] = str(insert_data[key])
    supabase.table("user_profiles").insert(insert_data).execute()

    return new_user, True


def _extract_message_greenapi(body: dict[str, Any]) -> tuple[str | None, str | None]:
    """Parse Green API webhook payload.

    Green API format:
        {
          "typeWebhook": "incomingMessageReceived",
          "senderData": {"chatId": "919876543210@c.us", "sender": "919876543210@c.us"},
          "messageData": {"typeMessage": "textMessage", "textMessageData": {"textMessage": "hello"}}
        }
    """
    try:
        if body.get("typeWebhook") != "incomingMessageReceived":
            return None, None

        sender_data = body.get("senderData", {})
        # chatId is "919876543210@c.us" — strip the suffix
        chat_id = sender_data.get("chatId", "")
        phone = chat_id.replace("@c.us", "").replace("@g.us", "")
        if not phone:
            return None, None

        msg_data = body.get("messageData", {})
        msg_type = msg_data.get("typeMessage", "")

        text = None
        if msg_type == "textMessage":
            text = msg_data.get("textMessageData", {}).get("textMessage", "")
        elif msg_type == "extendedTextMessage":
            text = msg_data.get("extendedTextMessageData", {}).get("text", "")

        return phone, text

    except (KeyError, TypeError):
        logger.exception("Failed to parse Green API payload")
        return None, None


def _extract_message_meta(body: dict[str, Any]) -> tuple[str | None, str | None]:
    """Parse Meta WhatsApp Cloud API webhook payload.

        {
          "entry": [{"changes": [{"value": {
            "messages": [{"from": "919876543210", "type": "text",
                          "text": {"body": "hello"}}]
          }}]}]
        }
    """
    try:
        entry = body.get("entry", [])
        if not entry:
            return None, None
        changes = entry[0].get("changes", [])
        if not changes:
            return None, None
        value = changes[0].get("value", {})
        messages = value.get("messages", [])
        if not messages:
            return None, None

        msg = messages[0]
        phone = msg.get("from")
        msg_type = msg.get("type", "")

        text = None
        if msg_type == "text":
            text = msg.get("text", {}).get("body", "")
        elif msg_type == "interactive":
            interactive = msg.get("interactive", {})
            int_type = interactive.get("type", "")
            if int_type == "button_reply":
                text = interactive.get("button_reply", {}).get("title", "")
            elif int_type == "list_reply":
                text = interactive.get("list_reply", {}).get("title", "")

        return phone, text

    except (KeyError, IndexError, TypeError):
        logger.exception("Failed to parse Meta webhook payload")
        return None, None


def _extract_message(body: dict[str, Any]) -> tuple[str | None, str | None]:
    """Auto-detect provider and extract (phone, text) from webhook payload."""
    # Green API payloads always have "typeWebhook"
    if "typeWebhook" in body:
        return _extract_message_greenapi(body)
    # Meta payloads always have "entry"
    return _extract_message_meta(body)


# ------------------------------------------------------------------
# Command handlers (for onboarded users)
# ------------------------------------------------------------------

async def _handle_status(phone: str, user: UserProfile) -> None:
    await send_text_message(phone, tpl.profile_summary(user))


async def _handle_alerts(phone: str, user: UserProfile) -> None:
    try:
        notifications = fetch_eligible_notifications_for_user(user)
    except Exception:
        logger.exception("Failed to fetch notifications for %s", phone)
        await send_text_message(phone, "Notifications fetch karne mein error aaya. Kripya baad mein try karein.")
        return

    if not notifications:
        await send_text_message(
            phone,
            "Abhi aapke liye koi nayi eligible notification nahi hai. Jaise hi aayegi, hum alert bhejenge! 🔔"
        )
        return

    await send_text_message(phone, tpl.format_weekly_digest(notifications, user))


async def _handle_help(phone: str) -> None:
    await send_text_message(phone, tpl.help_message())


# ------------------------------------------------------------------
# Webhook endpoints
# ------------------------------------------------------------------

@router.get("/webhook")
async def verify_webhook(
    hub_mode: str | None = Query(None, alias="hub.mode"),
    hub_verify_token: str | None = Query(None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(None, alias="hub.challenge"),
) -> Response:
    """WhatsApp webhook verification (challenge-response)."""
    settings = get_settings()

    if hub_mode == "subscribe" and hub_verify_token == settings.whatsapp_verify_token:
        logger.info("Webhook verified successfully")
        return Response(content=hub_challenge or "", media_type="text/plain")

    logger.warning("Webhook verification failed: token mismatch")
    return Response(content="Verification failed", status_code=403)


@router.post("/webhook")
async def handle_webhook(request: Request) -> dict[str, str]:
    """Process an incoming WhatsApp message."""
    # Optional webhook signature validation using WHATSAPP_VERIFY_TOKEN
    # Check for token in X-Webhook-Token header or 'token' query param
    settings = get_settings()
    expected_token = settings.whatsapp_verify_token
    incoming_token = (
        request.headers.get("x-webhook-token")
        or request.query_params.get("token")
    )
    if incoming_token:
        if incoming_token != expected_token:
            logger.warning("Webhook rejected: invalid token from %s", request.client.host if request.client else "unknown")
            return {"status": "error", "detail": "unauthorized"}
    else:
        logger.debug("No webhook token provided in request — skipping signature check")

    try:
        body = await request.json()
    except Exception:
        logger.exception("Could not parse webhook JSON body")
        return {"status": "error", "detail": "invalid json"}

    phone, text = _extract_message(body)

    if not phone or not text:
        # Could be a status update or delivery receipt — acknowledge silently
        return {"status": "ok"}

    text = text.strip()
    logger.info("Incoming message from %s: %s", phone, text[:100])

    try:
        user, is_new = _get_or_create_user(phone)
    except Exception:
        logger.exception("DB error for phone %s", phone)
        return {"status": "error", "detail": "db error"}

    # --- New user: kick off onboarding ---
    if is_new:
        await send_text_message(phone, tpl.welcome_message())
        return {"status": "ok"}

    # --- Onboarding in progress ---
    if user.onboarding_step != OnboardingStep.COMPLETED.value:
        await handle_onboarding(phone, text, user)
        return {"status": "ok"}

    # --- Onboarded user: handle commands ---
    command = text.lower()

    if command in ("status", "profile"):
        await _handle_status(phone, user)
    elif command == "alerts":
        await _handle_alerts(phone, user)
    elif command == "help":
        await _handle_help(phone)
    else:
        await send_text_message(phone, tpl.generic_response())

    return {"status": "ok"}
