from __future__ import annotations
"""
Government job notification matching engine.

Determines eligibility of users for notifications based on age, qualification,
state domicile, gender, and exam type preferences.
"""

from datetime import date
from typing import Optional

from database.models import (
    UserProfile,
    Notification,
    QUALIFICATION_HIERARCHY,
    CategoryType,
    ExamCategory,
)
from database.connection import get_supabase


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _qualification_rank(qualification: Optional[str]) -> int:
    """Return the numeric rank of a qualification in the hierarchy.

    Returns -1 if the qualification is not found or is None.
    """
    if qualification is None:
        return -1
    try:
        return QUALIFICATION_HIERARCHY.index(qualification)
    except ValueError:
        return -1


def _get_category_relaxation(user: UserProfile, notification: Notification) -> int:
    """Return the age relaxation (in years) based on the user's category."""
    category = (user.category or "").strip()

    if category == CategoryType.OBC.value:
        return notification.obc_relaxation
    elif category in (CategoryType.SC.value, CategoryType.ST.value):
        return notification.sc_st_relaxation
    elif category == CategoryType.EWS.value:
        return notification.ews_relaxation

    # General category gets no relaxation
    return 0


# ---------------------------------------------------------------------------
# Individual eligibility checks
# ---------------------------------------------------------------------------

def _check_age(user: UserProfile, notification: Notification) -> bool:
    """Check whether the user's age falls within the notification's limits.

    Age relaxation is applied additively:
        effective_max = max_age + category_relaxation + pwd_relaxation + ex_serviceman_relaxation
    """
    if notification.max_age is None and notification.min_age is None:
        return True

    if user.age_years is None:
        # Cannot determine eligibility without the user's age
        return False

    # --- upper-age check ---
    if notification.max_age is not None:
        effective_max = notification.max_age
        effective_max += _get_category_relaxation(user, notification)

        if user.pwd_status:
            effective_max += notification.pwd_relaxation

        if user.ex_serviceman:
            effective_max += notification.ex_serviceman_relaxation

        if user.age_years > effective_max:
            return False

    # --- lower-age check ---
    if notification.min_age is not None:
        if user.age_years < notification.min_age:
            return False

    return True


def _check_qualification(user: UserProfile, notification: Notification) -> bool:
    """User's qualification must be at or above the notification requirement."""
    if notification.min_qualification is None:
        return True

    user_rank = _qualification_rank(user.qualification)
    required_rank = _qualification_rank(notification.min_qualification)

    if user_rank == -1:
        # User qualification unknown — cannot confirm eligibility
        return False

    if required_rank == -1:
        # Notification specifies an unrecognised qualification — treat as no restriction
        return True

    return user_rank >= required_rank


def _check_state_domicile(user: UserProfile, notification: Notification) -> bool:
    """For notifications with a state restriction, verify the user's domicile.

    State PSC notifications also require the state to be in the user's
    state_psc_states preference list.
    """
    if notification.state_restriction is None:
        return True

    required_state = notification.state_restriction.strip()

    # Basic domicile match
    user_state = (user.state_domicile or "").strip()
    if user_state.lower() != required_state.lower():
        return False

    # For State PSC, additionally check preference list
    if notification.exam_category == ExamCategory.STATE_PSC.value:
        psc_states_lower = [s.strip().lower() for s in user.state_psc_states]
        if required_state.lower() not in psc_states_lower:
            return False

    return True


def _check_gender(user: UserProfile, notification: Notification) -> bool:
    """If the notification restricts gender, the user's gender must be in the list."""
    if notification.gender_restriction is None or len(notification.gender_restriction) == 0:
        return True

    if user.gender is None:
        return False

    allowed_lower = [g.strip().lower() for g in notification.gender_restriction]
    return user.gender.strip().lower() in allowed_lower


def _check_exam_preference(user: UserProfile, notification: Notification) -> bool:
    """The notification's exam category must be in the user's preference list."""
    if not user.exam_preferences:
        # User has not set any preferences — cannot match
        return False

    prefs_lower = [p.strip().lower() for p in user.exam_preferences]
    return notification.exam_category.strip().lower() in prefs_lower


# ---------------------------------------------------------------------------
# Public API — in-memory matching
# ---------------------------------------------------------------------------

def is_eligible(user: UserProfile, notification: Notification) -> bool:
    """Return True if the user is eligible for the given notification.

    Runs all checks in sequence; short-circuits on the first failure.
    """
    checks = [
        _check_exam_preference,
        _check_age,
        _check_qualification,
        _check_gender,
        _check_state_domicile,
    ]
    return all(check(user, notification) for check in checks)


def find_eligible_users(
    notification: Notification,
    all_users: list[UserProfile],
) -> list[UserProfile]:
    """Return the subset of *all_users* eligible for *notification*.

    This is an in-memory operation suitable for batch processing.
    """
    return [user for user in all_users if is_eligible(user, notification)]


def find_eligible_notifications(
    user: UserProfile,
    all_notifications: list[Notification],
) -> list[Notification]:
    """Return every notification in *all_notifications* that the user is eligible for.

    This is an in-memory operation suitable for batch processing.
    """
    return [n for n in all_notifications if is_eligible(user, n)]


def count_eligible_notifications(
    user: UserProfile,
    active_notifications: list[Notification],
) -> int:
    """Count how many active notifications the user qualifies for.

    Intended for the onboarding flow: "You're eligible for X notifications."
    """
    return sum(1 for n in active_notifications if is_eligible(user, n))


# ---------------------------------------------------------------------------
# DB-backed convenience methods (use Supabase)
# ---------------------------------------------------------------------------

def _rows_to_users(rows: list[dict]) -> list[UserProfile]:
    """Convert raw Supabase rows to UserProfile instances."""
    users = []
    for row in rows:
        users.append(UserProfile(**row))
    return users


def _rows_to_notifications(rows: list[dict]) -> list[Notification]:
    """Convert raw Supabase rows to Notification instances."""
    notifications = []
    for row in rows:
        notifications.append(Notification(**row))
    return notifications


def fetch_eligible_users_for_notification(notification: Notification) -> list[UserProfile]:
    """Fetch all active users from the database and return those eligible.

    Uses the Supabase client to pull users, then applies in-memory matching.
    """
    supabase = get_supabase()
    response = (
        supabase.table("user_profiles")
        .select("*")
        .eq("is_active", True)
        .eq("onboarding_step", "completed")
        .execute()
    )
    all_users = _rows_to_users(response.data or [])
    return find_eligible_users(notification, all_users)


def fetch_eligible_notifications_for_user(user: UserProfile) -> list[Notification]:
    """Fetch active notifications from the database and return those the user is eligible for.

    Only considers notifications whose application_end_date is today or later.
    """
    supabase = get_supabase()
    today = date.today().isoformat()
    response = (
        supabase.table("notifications")
        .select("*")
        .gte("application_end_date", today)
        .execute()
    )
    all_notifications = _rows_to_notifications(response.data or [])
    return find_eligible_notifications(user, all_notifications)


def fetch_eligible_notification_count(user: UserProfile) -> int:
    """Fetch active notifications from DB and count how many the user qualifies for.

    Convenience wrapper for the onboarding "You're eligible for X" message.
    """
    notifications = fetch_eligible_notifications_for_user(user)
    return len(notifications)
