from __future__ import annotations
"""
Notification storage layer using Supabase.
Handles CRUD, deduplication, and query operations for notifications.
"""

import hashlib
import logging
from datetime import date, datetime
from typing import Any, Optional

from database.connection import get_supabase

logger = logging.getLogger(__name__)

TABLE = "notifications"


def _to_serializable(data: dict[str, Any]) -> dict[str, Any]:
    """Convert date/datetime objects to ISO strings for Supabase."""
    result = {}
    for key, value in data.items():
        if isinstance(value, (date, datetime)):
            result[key] = value.isoformat()
        elif value is not None:
            result[key] = value
    return result


def compute_dedup_hash(notification: dict[str, Any]) -> str:
    """
    Compute a deduplication hash from the notification's key fields.
    Uses recruiting_body + post_name + application_end_date to identify duplicates.
    """
    body = (notification.get("recruiting_body") or "").strip().lower()
    post = (notification.get("post_name") or "").strip().lower()
    end_date = str(notification.get("application_end_date") or "")
    raw = f"{body}|{post}|{end_date}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def store_notification(notification: dict[str, Any]) -> dict[str, Any]:
    """
    Upsert a notification with deduplication.

    If a notification with the same dedup_hash already exists, it is updated.
    Otherwise a new row is inserted.

    Args:
        notification: Dict of notification fields matching the Notification model.

    Returns:
        The stored/updated notification record from Supabase.
    """
    client = get_supabase()

    # Ensure dedup_hash is present
    if "dedup_hash" not in notification or not notification["dedup_hash"]:
        notification["dedup_hash"] = compute_dedup_hash(notification)

    dedup_hash = notification["dedup_hash"]
    data = _to_serializable(notification)

    # Check for existing record
    existing = (
        client.table(TABLE)
        .select("id")
        .eq("dedup_hash", dedup_hash)
        .execute()
    )

    if existing.data:
        # Update existing record
        record_id = existing.data[0]["id"]
        # Don't overwrite the id
        data.pop("id", None)
        result = (
            client.table(TABLE)
            .update(data)
            .eq("id", record_id)
            .execute()
        )
        logger.info("Updated notification %s (dedup_hash=%s)", record_id, dedup_hash)
    else:
        # Insert new record
        data.pop("id", None)  # Let Supabase generate the ID
        result = (
            client.table(TABLE)
            .insert(data)
            .execute()
        )
        logger.info("Inserted new notification (dedup_hash=%s)", dedup_hash)

    return result.data[0] if result.data else {}


def get_notification(notification_id: str) -> Optional[dict[str, Any]]:
    """
    Fetch a single notification by its ID.

    Args:
        notification_id: UUID of the notification.

    Returns:
        Notification dict or None if not found.
    """
    client = get_supabase()
    result = (
        client.table(TABLE)
        .select("*")
        .eq("id", notification_id)
        .execute()
    )
    return result.data[0] if result.data else None


def get_active_notifications() -> list[dict[str, Any]]:
    """
    Fetch all notifications whose application deadline has not passed.

    Returns:
        List of notification dicts with application_end_date >= today.
    """
    client = get_supabase()
    today = date.today().isoformat()
    result = (
        client.table(TABLE)
        .select("*")
        .gte("application_end_date", today)
        .order("application_end_date", desc=False)
        .execute()
    )
    return result.data or []


def get_notifications_since(since: datetime) -> list[dict[str, Any]]:
    """
    Fetch notifications created after the given timestamp.
    Useful for generating alerts about newly added notifications.

    Args:
        since: Datetime threshold — only return notifications created after this.

    Returns:
        List of notification dicts ordered by creation time.
    """
    client = get_supabase()
    result = (
        client.table(TABLE)
        .select("*")
        .gte("created_at", since.isoformat())
        .order("created_at", desc=False)
        .execute()
    )
    return result.data or []


def mark_verified(notification_id: str) -> Optional[dict[str, Any]]:
    """
    Mark a notification as verified against the official source.

    Args:
        notification_id: UUID of the notification.

    Returns:
        Updated notification dict or None if not found.
    """
    client = get_supabase()
    result = (
        client.table(TABLE)
        .update({"is_verified": True})
        .eq("id", notification_id)
        .execute()
    )
    if result.data:
        logger.info("Marked notification %s as verified", notification_id)
        return result.data[0]

    logger.warning("Notification %s not found for verification", notification_id)
    return None
