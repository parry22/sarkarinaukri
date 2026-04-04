from __future__ import annotations
"""
Reminder scheduling logic for the Sarkari Naukri Alert Bot.

Calculates and creates deadline reminder entries for government job
notifications, and processes due reminders by sending WhatsApp messages.
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
from bot.message_templates import format_deadline_reminder

logger = logging.getLogger(__name__)

ALERT_TABLE = "alert_queue"

# Reminder intervals in days before application_end_date
REMINDER_DAYS = [7, 3, 1]

# Subscription tiers required for each reminder interval
TIER_REQUIREMENTS = {
    7: {"basic", "pro", "premium"},
    3: {"pro", "premium"},
    1: {"pro", "premium"},
}


def _alert_type_for_days(days: int) -> str:
    """Return the alert_type string for a given reminder interval."""
    return f"reminder_{days}d"


# ---------------------------------------------------------------------------
# Schedule reminders
# ---------------------------------------------------------------------------

def schedule_reminders_for_notification(notification: Notification) -> int:
    """
    Calculate and create reminder entries for a notification.

    Creates alert_queue entries for 7-day, 3-day, and 1-day reminders
    before the application_end_date. Only schedules reminders for dates
    that are still in the future. Respects subscription tier requirements.

    Args:
        notification: The notification to schedule reminders for.

    Returns:
        Number of reminder entries created.
    """
    if not notification.application_end_date:
        logger.debug(
            "No application_end_date for notification %s, skipping reminders",
            notification.id,
        )
        return 0

    today = date.today()
    client = get_supabase()
    eligible_users = fetch_eligible_users_for_notification(notification)

    if not eligible_users:
        logger.info(
            "No eligible users for notification %s, skipping reminders",
            notification.id,
        )
        return 0

    total_scheduled = 0

    for days_before in REMINDER_DAYS:
        reminder_date = notification.application_end_date - timedelta(days=days_before)

        # Only schedule if the reminder date is in the future
        if reminder_date <= today:
            continue

        alert_type = _alert_type_for_days(days_before)
        allowed_tiers = TIER_REQUIREMENTS[days_before]

        # Schedule the reminder at 9:00 AM IST on the reminder date
        scheduled_dt = datetime(
            reminder_date.year,
            reminder_date.month,
            reminder_date.day,
            3, 30, 0,  # 9:00 AM IST = 3:30 AM UTC
            tzinfo=timezone.utc,
        )

        for user in eligible_users:
            if user.subscription_tier not in allowed_tiers:
                continue

            try:
                client.table(ALERT_TABLE).insert({
                    "user_id": user.id,
                    "notification_id": notification.id,
                    "alert_type": alert_type,
                    "status": "pending",
                    "scheduled_for": scheduled_dt.isoformat(),
                }).execute()
                total_scheduled += 1
            except Exception as exc:
                error_msg = str(exc).lower()
                if "duplicate" in error_msg or "unique" in error_msg or "23505" in error_msg:
                    logger.debug(
                        "Reminder %s already scheduled for user %s / notification %s",
                        alert_type,
                        user.id,
                        notification.id,
                    )
                else:
                    logger.error(
                        "Failed to schedule reminder %s for user %s: %s",
                        alert_type,
                        user.id,
                        exc,
                    )

    logger.info(
        "Scheduled %d reminders for notification %s (%s)",
        total_scheduled,
        notification.id,
        notification.post_name,
    )
    return total_scheduled


# ---------------------------------------------------------------------------
# Check and send due reminders
# ---------------------------------------------------------------------------

def check_and_send_reminders() -> dict[str, int]:
    """
    Process all due reminders and send WhatsApp messages.

    Called periodically to:
    1. Get all due reminders (scheduled_for <= now, status = pending).
    2. Check if user has already applied (based on user response tracking).
    3. Send reminder via WhatsApp.
    4. Update status to 'sent' or 'failed'.

    Returns:
        Dict with counts: {"sent": N, "failed": N, "skipped": N}.
    """
    client = get_supabase()
    now = datetime.now(timezone.utc).isoformat()

    # Fetch due reminders with user and notification data
    response = (
        client.table(ALERT_TABLE)
        .select("*, user_profiles!alert_queue_user_id_fkey(*), notifications!alert_queue_notification_id_fkey(*)")
        .eq("status", "pending")
        .lte("scheduled_for", now)
        .like("alert_type", "reminder_%")
        .order("scheduled_for", desc=False)
        .limit(100)
        .execute()
    )

    reminders = response.data or []
    if not reminders:
        logger.debug("No due reminders to process")
        return {"sent": 0, "failed": 0, "skipped": 0}

    results = {"sent": 0, "failed": 0, "skipped": 0}

    for reminder in reminders:
        reminder_id = reminder["id"]
        alert_type = reminder.get("alert_type", "")

        try:
            user_data = reminder.get("user_profiles")
            notif_data = reminder.get("notifications")

            if not user_data or not notif_data:
                _mark_reminder(client, reminder_id, "failed", "Missing user or notification data")
                results["failed"] += 1
                continue

            user = UserProfile(**user_data)
            notification = Notification(**notif_data)

            # Check if user has already acknowledged a previous reminder
            # by looking for a 'sent' alert of an earlier reminder type
            if _user_has_applied(client, user.id, notification.id):
                _mark_reminder(client, reminder_id, "skipped", "User already applied")
                results["skipped"] += 1
                continue

            # Calculate days left for the message
            days_str = alert_type.replace("reminder_", "").replace("d", "")
            try:
                days_left = int(days_str)
            except ValueError:
                days_left = 0

            # Format and send the reminder (async function called from sync context)
            message = format_deadline_reminder(notification, days_left)
            asyncio.run(send_text_message(user.phone, message))

            # Mark as sent
            _mark_reminder(client, reminder_id, "sent")
            results["sent"] += 1

            logger.info(
                "Sent %s to %s for %s",
                alert_type,
                user.phone,
                notification.post_name,
            )

        except Exception as exc:
            _mark_reminder(client, reminder_id, "failed", str(exc))
            results["failed"] += 1
            logger.error("Failed to send reminder %s: %s", reminder_id, exc)

        # Rate limit between sends
        time.sleep(0.5)

    logger.info(
        "Processed %d reminders: %d sent, %d failed, %d skipped",
        len(reminders),
        results["sent"],
        results["failed"],
        results["skipped"],
    )
    return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _user_has_applied(client: Any, user_id: str, notification_id: str) -> bool:
    """
    Check if the user has indicated they already applied.

    Looks for a 'skipped' status on any reminder for this user/notification
    combination, which is set when the user responds that they have applied.
    """
    response = (
        client.table(ALERT_TABLE)
        .select("id")
        .eq("user_id", user_id)
        .eq("notification_id", notification_id)
        .like("alert_type", "reminder_%")
        .eq("status", "skipped")
        .limit(1)
        .execute()
    )
    return bool(response.data)


def _mark_reminder(
    client: Any,
    reminder_id: str,
    status: str,
    error_message: str | None = None,
) -> None:
    """Update a reminder's status in the alert_queue."""
    update_data: dict[str, Any] = {"status": status}

    if status == "sent":
        update_data["sent_at"] = datetime.now(timezone.utc).isoformat()

    if error_message:
        update_data["error_message"] = error_message[:500]

    client.table(ALERT_TABLE).update(update_data).eq("id", reminder_id).execute()
