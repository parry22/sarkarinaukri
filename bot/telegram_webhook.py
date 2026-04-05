from __future__ import annotations
"""
FastAPI router for the Telegram Bot webhook.

Telegram sends POST updates to /telegram/webhook.
Users are stored in Supabase with phone = "tg_{chat_id}" so they are
completely isolated from WhatsApp users but share the same onboarding
flow, notification matching, and alert queue.

The send_text_message in bot/whatsapp_client.py auto-detects the "tg_"
prefix and routes to bot/telegram_client — so handle_onboarding and
all command handlers work unchanged.
"""

import logging
from typing import Any

from fastapi import APIRouter, Request

from config import get_settings
from database.connection import get_supabase
from database.models import OnboardingStep, UserProfile
from matching.eligibility_matcher import fetch_eligible_notifications_for_user
from bot.telegram_client import answer_callback_query, send_text_message
from bot.onboarding import handle_onboarding
from bot import message_templates as tpl

logger = logging.getLogger(__name__)

router = APIRouter()


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _extract_update(body: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    """
    Parse a Telegram Update object.

    Returns:
        (tg_phone, text, callback_query_id)
        tg_phone  — "tg_{chat_id}" or None if unrecognised update type
        text      — message text or callback data
        callback_query_id — non-None only for inline button presses
    """
    # Inline keyboard button press
    if "callback_query" in body:
        cq = body["callback_query"]
        chat_id = str(cq.get("message", {}).get("chat", {}).get("id", ""))
        if not chat_id:
            return None, None, None
        return f"tg_{chat_id}", cq.get("data", "").strip(), cq.get("id")

    # Regular text message (or edited message)
    message = body.get("message") or body.get("edited_message")
    if not message:
        return None, None, None

    chat_id = str(message.get("chat", {}).get("id", ""))
    if not chat_id:
        return None, None, None

    text = message.get("text", "").strip()
    return f"tg_{chat_id}", text, None


def _get_or_create_user(tg_phone: str) -> tuple[UserProfile, bool]:
    """Look up or create a user keyed by their tg_<chat_id> identifier."""
    supabase = get_supabase()
    response = (
        supabase.table("user_profiles")
        .select("*")
        .eq("phone", tg_phone)
        .limit(1)
        .execute()
    )

    if response.data:
        return UserProfile(**response.data[0]), False

    new_user = UserProfile(phone=tg_phone)
    insert_data = new_user.model_dump(exclude_none=True)
    for key in ("date_of_birth", "subscription_expires_at"):
        if key in insert_data and insert_data[key] is not None:
            insert_data[key] = str(insert_data[key])
    supabase.table("user_profiles").insert(insert_data).execute()
    return new_user, True


# ------------------------------------------------------------------
# Command handlers (for fully onboarded Telegram users)
# ------------------------------------------------------------------

async def _handle_alerts(tg_phone: str, user: UserProfile) -> None:
    try:
        notifications = fetch_eligible_notifications_for_user(user)
    except Exception:
        logger.exception("Failed to fetch notifications for %s", tg_phone)
        await send_text_message(
            tg_phone,
            "Notifications fetch karne mein error aaya. Kripya baad mein try karein."
        )
        return

    if not notifications:
        await send_text_message(
            tg_phone,
            "Abhi aapke liye koi nayi eligible notification nahi hai. "
            "Jaise hi aayegi, hum alert bhejenge! 🔔",
        )
        return

    await send_text_message(tg_phone, tpl.format_weekly_digest(notifications, user))


# ------------------------------------------------------------------
# Webhook endpoint
# ------------------------------------------------------------------

@router.post("/telegram/webhook")
async def telegram_webhook(request: Request) -> dict[str, str]:
    """Receive and process a Telegram Update."""
    try:
        body = await request.json()
    except Exception:
        logger.exception("Could not parse Telegram webhook JSON")
        # Always return 200 to Telegram — otherwise it retries indefinitely
        return {"status": "error"}

    tg_phone, text, callback_query_id = _extract_update(body)

    # Acknowledge callback_query immediately (removes Telegram loading spinner)
    if callback_query_id:
        try:
            await answer_callback_query(callback_query_id)
        except Exception:
            pass

    if not tg_phone or not text:
        return {"status": "ok"}

    logger.info("Telegram update from %s: %s", tg_phone, text[:100])

    try:
        user, is_new = _get_or_create_user(tg_phone)
    except Exception:
        logger.exception("DB error for Telegram user %s", tg_phone)
        return {"status": "error"}

    # New user — send welcome and kick off onboarding
    if is_new:
        await send_text_message(tg_phone, tpl.welcome_message())
        return {"status": "ok"}

    # Onboarding in progress — delegate to shared state machine
    # send_text_message in whatsapp_client routes "tg_*" calls to telegram_client
    if user.onboarding_step != OnboardingStep.COMPLETED.value:
        await handle_onboarding(tg_phone, text, user)
        return {"status": "ok"}

    # Fully onboarded — handle commands
    command = text.lower()
    if command in ("status", "profile", "/status", "/profile", "/start"):
        await send_text_message(tg_phone, tpl.profile_summary(user))
    elif command in ("alerts", "/alerts"):
        await _handle_alerts(tg_phone, user)
    elif command in ("help", "/help"):
        await send_text_message(tg_phone, tpl.help_message())
    else:
        await send_text_message(tg_phone, tpl.generic_response())

    return {"status": "ok"}
