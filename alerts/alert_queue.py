from __future__ import annotations
"""
Alert queue manager for the Sarkari Naukri Alert Bot.

Handles queuing, processing, and tracking of user alerts for government
job notifications. Integrates with the eligibility matcher, WhatsApp
client, and Supabase for persistent storage.
"""

import asyncio
import logging
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any

from database.connection import get_supabase
from database.models import Notification, UserProfile
from matching.eligibility_matcher import fetch_eligible_users_for_notification
from bot.whatsapp_client import send_text_message
from bot.message_templates import format_new_alert, format_deadline_reminder
from scraping.storage.notification_store import get_active_notifications

logger = logging.getLogger(__name__)

TABLE = "alert_queue"

# Subscription tiers that qualify for each reminder type
REMINDER_TIERS = {
    "reminder_7d": {"basic", "pro", "premium"},
    "reminder_3d": {"pro", "premium"},
    "reminder_1d": {"pro", "premium"},
}


# ---------------------------------------------------------------------------
# Queue new alerts
# ---------------------------------------------------------------------------

def queue_alerts_for_notification(notification: Notification) -> int:
    """
    Queue alerts for all users eligible for the given notification.

    Finds eligible users via the matching engine and creates alert_queue
    entries with status='pending'. Skips entries that already exist
    (UNIQUE constraint on user_id + notification_id + alert_type).

    Args:
        notification: The notification to alert users about.

    Returns:
        Number of alerts successfully queued.
    """
    eligible_users = fetch_eligible_users_for_notification(notification)
    if not eligible_users:
        logger.info(
            "No eligible users for notification %s (%s)",
            notification.id,
            notification.post_name,
        )
        return 0

    client = get_supabase()
    queued = 0

    for user in eligible_users:
        try:
            client.table(TABLE).insert({
                "user_id": user.id,
                "notification_id": notification.id,
                "alert_type": "new_alert",
                "status": "pending",
                "scheduled_for": datetime.now(timezone.utc).isoformat(),
            }).execute()
            queued += 1
        except Exception as exc:
            # UNIQUE constraint violation means the alert already exists
            error_msg = str(exc).lower()
            if "duplicate" in error_msg or "unique" in error_msg or "23505" in error_msg:
                logger.debug(
                    "Alert already exists for user %s / notification %s",
                    user.id,
                    notification.id,
                )
            else:
                logger.error(
                    "Failed to queue alert for user %s: %s", user.id, exc,
                )

    logger.info(
        "Queued %d alerts for notification %s (%s)",
        queued,
        notification.id,
        notification.post_name,
    )
    return queued


# ---------------------------------------------------------------------------
# Deadline reminders
# ---------------------------------------------------------------------------

def queue_deadline_reminders() -> int:
    """
    Check all active notifications and create deadline reminder alerts.

    Reminder schedule:
    - 7-day reminder: basic, pro, premium subscribers
    - 3-day reminder: pro, premium subscribers
    - 1-day reminder: pro, premium subscribers

    Only queues reminders for dates in the future and skips if already queued.

    Returns:
        Total number of reminders queued.
    """
    active_notifications = get_active_notifications()
    if not active_notifications:
        logger.info("No active notifications for deadline reminders")
        return 0

    client = get_supabase()
    today = date.today()
    total_queued = 0

    for notif_data in active_notifications:
        end_date_str = notif_data.get("application_end_date")
        if not end_date_str:
            continue

        try:
            end_date = date.fromisoformat(str(end_date_str))
        except (ValueError, TypeError):
            continue

        notification = Notification(**notif_data)
        days_left = (end_date - today).days

        # Determine which reminders are due
        reminders_to_queue: list[tuple[str, int]] = []
        if days_left == 7:
            reminders_to_queue.append(("reminder_7d", 7))
        if days_left == 3:
            reminders_to_queue.append(("reminder_3d", 3))
        if days_left == 1:
            reminders_to_queue.append(("reminder_1d", 1))

        if not reminders_to_queue:
            continue

        # Get eligible users for this notification
        eligible_users = fetch_eligible_users_for_notification(notification)

        for alert_type, _days in reminders_to_queue:
            allowed_tiers = REMINDER_TIERS[alert_type]

            for user in eligible_users:
                if user.subscription_tier not in allowed_tiers:
                    continue

                try:
                    client.table(TABLE).insert({
                        "user_id": user.id,
                        "notification_id": notification.id,
                        "alert_type": alert_type,
                        "status": "pending",
                        "scheduled_for": datetime.now(timezone.utc).isoformat(),
                    }).execute()
                    total_queued += 1
                except Exception as exc:
                    error_msg = str(exc).lower()
                    if "duplicate" in error_msg or "unique" in error_msg or "23505" in error_msg:
                        logger.debug(
                            "Reminder %s already exists for user %s / notification %s",
                            alert_type,
                            user.id,
                            notification.id,
                        )
                    else:
                        logger.error(
                            "Failed to queue reminder %s for user %s: %s",
                            alert_type,
                            user.id,
                            exc,
                        )

    logger.info("Queued %d deadline reminders", total_queued)
    return total_queued


# ---------------------------------------------------------------------------
# Process pending alerts
# ---------------------------------------------------------------------------

def process_pending_alerts(batch_size: int = 50) -> dict[str, int]:
    """
    Process a batch of pending alerts from the queue.

    1. Fetches pending alerts where scheduled_for <= now.
    2. Formats the appropriate message for each alert type.
    3. Sends via WhatsApp.
    4. Updates status to 'sent' or 'failed'.
    5. Rate-limits between sends to avoid WhatsApp throttling.

    Args:
        batch_size: Maximum number of alerts to process in this batch.

    Returns:
        Dict with counts: {"sent": N, "failed": N}.
    """
    client = get_supabase()
    now = datetime.now(timezone.utc).isoformat()

    # Fetch pending alerts that are due
    response = (
        client.table(TABLE)
        .select("*, user_profiles!alert_queue_user_id_fkey(*), notifications!alert_queue_notification_id_fkey(*)")
        .eq("status", "pending")
        .lte("scheduled_for", now)
        .limit(batch_size)
        .order("scheduled_for", desc=False)
        .execute()
    )

    alerts = response.data or []
    if not alerts:
        logger.debug("No pending alerts to process")
        return {"sent": 0, "failed": 0}

    results = {"sent": 0, "failed": 0}

    for alert in alerts:
        alert_id = alert["id"]
        alert_type = alert.get("alert_type", "new_alert")

        try:
            user_data = alert.get("user_profiles")
            notif_data = alert.get("notifications")

            if not user_data or not notif_data:
                _mark_alert_failed(client, alert_id, "Missing user or notification data")
                results["failed"] += 1
                continue

            user = UserProfile(**user_data)
            notification = Notification(**notif_data)

            # Format message based on alert type
            if alert_type == "new_alert":
                message = format_new_alert(notification, user)
            elif alert_type.startswith("reminder_"):
                days_str = alert_type.replace("reminder_", "").replace("d", "")
                days_left = int(days_str)
                message = format_deadline_reminder(notification, days_left)
            else:
                message = format_new_alert(notification, user)

            # Send via WhatsApp (async function called from sync context)
            asyncio.run(send_text_message(user.phone, message))

            # Mark as sent
            client.table(TABLE).update({
                "status": "sent",
                "sent_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", alert_id).execute()

            results["sent"] += 1
            logger.info(
                "Sent %s alert to %s for %s",
                alert_type,
                user.phone,
                notification.post_name,
            )

        except Exception as exc:
            _mark_alert_failed(client, alert_id, str(exc))
            results["failed"] += 1
            logger.error("Failed to process alert %s: %s", alert_id, exc)

        # Rate limit between sends to avoid WhatsApp throttling
        time.sleep(0.5)

    logger.info(
        "Processed %d alerts: %d sent, %d failed",
        len(alerts),
        results["sent"],
        results["failed"],
    )
    return results


def _mark_alert_failed(client: Any, alert_id: str, error_message: str) -> None:
    """Mark an alert as failed with the given error message."""
    client.table(TABLE).update({
        "status": "failed",
        "error_message": error_message[:500],
    }).eq("id", alert_id).execute()


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def get_alert_stats() -> dict[str, int]:
    """
    Return counts of alerts by status.

    Returns:
        Dict with keys: pending, sent, failed, total.
    """
    client = get_supabase()

    stats = {"pending": 0, "sent": 0, "failed": 0, "total": 0}

    for status in ("pending", "sent", "failed"):
        response = (
            client.table(TABLE)
            .select("id", count="exact")
            .eq("status", status)
            .execute()
        )
        stats[status] = response.count or 0

    stats["total"] = stats["pending"] + stats["sent"] + stats["failed"]
    return stats
