from __future__ import annotations
"""
Telegram Bot API client.

Sends messages to Telegram users identified by their chat_id.
Phone-style IDs in this project are stored as "tg_{chat_id}" in the DB —
this module strips that prefix before calling the API.
"""

import logging
from typing import Any

import httpx

from config import get_settings

logger = logging.getLogger(__name__)

_TG_BASE = "https://api.telegram.org/bot{token}/{method}"


def _tg_url(method: str) -> str:
    token = get_settings().telegram_bot_token
    return _TG_BASE.format(token=token, method=method)


def _real_chat_id(phone: str) -> str:
    """Strip the 'tg_' prefix to get the raw Telegram chat_id."""
    return phone[3:] if phone.startswith("tg_") else phone


async def send_text_message(phone: str, text: str) -> None:
    """
    Send a plain text message to a Telegram chat.

    Tries Markdown parse mode first; falls back to plain text if Telegram
    rejects it (e.g. due to unescaped special chars in message templates).
    """
    chat_id = _real_chat_id(phone)
    url = _tg_url("sendMessage")

    # First attempt: Markdown (supports *bold* which our templates use)
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
    }

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(url, json=payload)
        if resp.status_code == 200:
            return

        # Markdown parse failed — retry as plain text
        logger.warning(
            "Telegram Markdown send failed (%s), retrying as plain text",
            resp.status_code,
        )
        payload.pop("parse_mode")
        resp2 = await client.post(url, json=payload)
        if resp2.status_code != 200:
            logger.error(
                "Telegram send failed for chat_id %s: %s — %s",
                chat_id,
                resp2.status_code,
                resp2.text[:200],
            )


async def send_buttons_message(phone: str, text: str, buttons: list[str]) -> None:
    """
    Send a message with inline keyboard buttons.

    Falls back to a numbered-option text message if the button list is empty.
    """
    chat_id = _real_chat_id(phone)

    if not buttons:
        await send_text_message(phone, text)
        return

    inline_keyboard = [[{"text": btn, "callback_data": btn}] for btn in buttons]
    url = _tg_url("sendMessage")
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "reply_markup": {"inline_keyboard": inline_keyboard},
    }

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(url, json=payload)
        if resp.status_code != 200:
            logger.warning(
                "Telegram button message failed (%s) — falling back to text",
                resp.status_code,
            )
            await send_text_message(phone, text)


async def answer_callback_query(callback_query_id: str) -> None:
    """Acknowledge a callback_query so Telegram removes the loading spinner."""
    url = _tg_url("answerCallbackQuery")
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(url, json={"callback_query_id": callback_query_id})


async def set_webhook(webhook_url: str) -> dict[str, Any]:
    """Register our HTTPS endpoint with Telegram."""
    url = _tg_url("setWebhook")
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(url, json={"url": webhook_url})
        result = resp.json()
        if result.get("ok"):
            logger.info("Telegram webhook set to: %s", webhook_url)
        else:
            logger.error("Telegram setWebhook failed: %s", result)
        return result


async def delete_webhook() -> dict[str, Any]:
    """Remove the Telegram webhook (switch to polling or clear old URL)."""
    url = _tg_url("deleteWebhook")
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(url)
        return resp.json()


async def get_me() -> dict[str, Any]:
    """Return bot info — useful for verifying the token is correct."""
    url = _tg_url("getMe")
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url)
        return resp.json()
