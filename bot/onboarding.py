from __future__ import annotations
"""
Onboarding conversation flow manager.

Walks a new user through each profile field step-by-step over WhatsApp,
validates responses, persists to Supabase, and sends the next question.
"""

import logging
import re
from datetime import date, datetime
from typing import Optional

from database.connection import get_supabase
from database.models import (
    CategoryType,
    ExamCategory,
    GenderType,
    LanguagePref,
    OnboardingStep,
    QualificationLevel,
    UserProfile,
)
from matching.eligibility_matcher import fetch_eligible_notification_count
from bot.whatsapp_client import send_text_message
from bot import message_templates as tpl

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------

INDIAN_STATES = [
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar",
    "Chhattisgarh", "Goa", "Gujarat", "Haryana", "Himachal Pradesh",
    "Jharkhand", "Karnataka", "Kerala", "Madhya Pradesh", "Maharashtra",
    "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Punjab",
    "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura",
    "Uttar Pradesh", "Uttarakhand", "West Bengal",
    # UTs
    "Delhi", "Chandigarh", "J&K", "Ladakh", "Puducherry",
    "Andaman & Nicobar", "Dadra & Nagar Haveli", "Lakshadweep",
]

_STATES_LOWER = {s.lower(): s for s in INDIAN_STATES}

QUALIFICATION_MAP = {
    "1": QualificationLevel.EIGHTH.value,
    "2": QualificationLevel.TENTH.value,
    "3": QualificationLevel.TWELFTH.value,
    "4": QualificationLevel.ITI.value,
    "5": QualificationLevel.DIPLOMA.value,
    "6": QualificationLevel.GRADUATE.value,
    "7": QualificationLevel.POSTGRADUATE.value,
}

CATEGORY_MAP = {
    "1": CategoryType.GENERAL.value,
    "2": CategoryType.OBC.value,
    "3": CategoryType.SC.value,
    "4": CategoryType.ST.value,
    "5": CategoryType.EWS.value,
}

GENDER_MAP = {
    "1": GenderType.MALE.value,
    "2": GenderType.FEMALE.value,
    "3": GenderType.OTHER.value,
}

EXAM_PREF_MAP = {
    "1": ExamCategory.RAILWAY.value,
    "2": ExamCategory.SSC.value,
    "3": ExamCategory.BANKING.value,
    "4": ExamCategory.DEFENCE.value,
    "5": ExamCategory.TEACHING.value,
    "6": ExamCategory.STATE_PSC.value,
    "7": ExamCategory.UPSC.value,
    "8": ExamCategory.POLICE.value,
}

LANGUAGE_MAP = {
    "1": LanguagePref.HINDI.value,
    "2": LanguagePref.ENGLISH.value,
    "3": LanguagePref.BOTH.value,
}


# ------------------------------------------------------------------
# DB helpers
# ------------------------------------------------------------------

def _update_user(phone: str, updates: dict) -> None:
    """Persist partial updates for a user row in Supabase."""
    supabase = get_supabase()
    supabase.table("user_profiles").update(updates).eq("phone", phone).execute()


def _calculate_age(dob: date) -> int:
    today = date.today()
    age = today.year - dob.year
    if (today.month, today.day) < (dob.month, dob.day):
        age -= 1
    return age


def _parse_dob(text: str) -> Optional[date]:
    """Parse DD/MM/YYYY or DD-MM-YYYY into a date object."""
    text = text.strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _match_state(text: str) -> Optional[str]:
    """Fuzzy-ish match of user input to an Indian state name."""
    text_lower = text.strip().lower()
    if not text_lower:
        return None
    # Exact match
    if text_lower in _STATES_LOWER:
        return _STATES_LOWER[text_lower]
    # Partial / substring match
    for key, canonical in _STATES_LOWER.items():
        if text_lower in key or key in text_lower:
            return canonical
    return None


# ------------------------------------------------------------------
# Step handlers
# ------------------------------------------------------------------

async def _handle_name(phone: str, text: str) -> None:
    name = text.strip()
    if len(name) < 2 or len(name) > 100:
        await send_text_message(phone, "Kripya apna poora naam bhejiye (2-100 characters).")
        return
    _update_user(phone, {
        "name": name,
        "onboarding_step": OnboardingStep.DOB.value,
    })
    await send_text_message(phone, tpl.ask_dob())


async def _handle_dob(phone: str, text: str) -> None:
    dob = _parse_dob(text)
    if dob is None:
        await send_text_message(
            phone,
            "❌ Date samajh nahi aayi. Kripya DD/MM/YYYY format mein bhejiye (jaise: 15/08/1995)."
        )
        return
    age = _calculate_age(dob)
    if age < 14 or age > 65:
        await send_text_message(
            phone,
            "❌ Age 14-65 ke beech honi chahiye. Kripya sahi date bhejiye."
        )
        return
    _update_user(phone, {
        "date_of_birth": dob.isoformat(),
        "age_years": age,
        "onboarding_step": OnboardingStep.QUALIFICATION.value,
    })
    await send_text_message(phone, tpl.ask_qualification())


async def _handle_qualification(phone: str, text: str) -> None:
    choice = text.strip()
    qualification = QUALIFICATION_MAP.get(choice)
    if qualification is None:
        await send_text_message(phone, "❌ Kripya 1 se 7 ke beech number bhejiye.")
        return
    _update_user(phone, {
        "qualification": qualification,
        "onboarding_step": OnboardingStep.STREAM.value,
    })
    await send_text_message(phone, tpl.ask_stream())


async def _handle_stream(phone: str, text: str) -> None:
    stream = text.strip()
    if stream.lower() == "skip":
        stream = None
    _update_user(phone, {
        "qualification_stream": stream,
        "onboarding_step": OnboardingStep.STATE.value,
    })
    await send_text_message(phone, tpl.ask_state())


async def _handle_state(phone: str, text: str) -> None:
    matched = _match_state(text)
    if matched is None:
        await send_text_message(
            phone,
            "❌ State nahi mila. Kripya Indian state ka naam bhejiye (jaise: Uttar Pradesh, Bihar, Delhi)."
        )
        return
    _update_user(phone, {
        "state_domicile": matched,
        "onboarding_step": OnboardingStep.CATEGORY.value,
    })
    await send_text_message(phone, tpl.ask_category())


async def _handle_category(phone: str, text: str) -> None:
    choice = text.strip()
    category = CATEGORY_MAP.get(choice)
    if category is None:
        await send_text_message(phone, "❌ Kripya 1 se 5 ke beech number bhejiye.")
        return
    _update_user(phone, {
        "category": category,
        "onboarding_step": OnboardingStep.GENDER.value,
    })
    await send_text_message(phone, tpl.ask_gender())


async def _handle_gender(phone: str, text: str) -> None:
    choice = text.strip()
    gender = GENDER_MAP.get(choice)
    if gender is None:
        await send_text_message(phone, "❌ Kripya 1, 2 ya 3 bhejiye.")
        return
    _update_user(phone, {
        "gender": gender,
        "onboarding_step": OnboardingStep.PWD.value,
    })
    await send_text_message(phone, tpl.ask_pwd())


async def _handle_pwd(phone: str, text: str) -> None:
    choice = text.strip()
    if choice not in ("1", "2"):
        await send_text_message(phone, "❌ Kripya 1 (Haan) ya 2 (Nahi) bhejiye.")
        return
    _update_user(phone, {
        "pwd_status": choice == "1",
        "onboarding_step": OnboardingStep.EX_SERVICEMAN.value,
    })
    await send_text_message(phone, tpl.ask_ex_serviceman())


async def _handle_ex_serviceman(phone: str, text: str) -> None:
    choice = text.strip()
    if choice not in ("1", "2"):
        await send_text_message(phone, "❌ Kripya 1 (Haan) ya 2 (Nahi) bhejiye.")
        return
    _update_user(phone, {
        "ex_serviceman": choice == "1",
        "onboarding_step": OnboardingStep.EXAM_PREFS.value,
    })
    await send_text_message(phone, tpl.ask_exam_prefs())


async def _handle_exam_prefs(phone: str, text: str) -> None:
    """Parse comma-separated numbers like '1,3,5' into exam categories."""
    raw = text.strip().replace(" ", "")
    tokens = [t.strip() for t in raw.split(",") if t.strip()]

    selected: list[str] = []
    for token in tokens:
        exam = EXAM_PREF_MAP.get(token)
        if exam is None:
            await send_text_message(
                phone,
                f"❌ '{token}' galat hai. Kripya 1-8 ke beech number comma se bhejiye (jaise: 1,3,5)."
            )
            return
        if exam not in selected:
            selected.append(exam)

    if not selected:
        await send_text_message(phone, "❌ Kam se kam ek exam select kijiye.")
        return

    _update_user(phone, {
        "exam_preferences": selected,
        "onboarding_step": OnboardingStep.LANGUAGE.value,
    })
    await send_text_message(phone, tpl.ask_language())


async def _handle_language(phone: str, text: str, user: UserProfile) -> None:
    choice = text.strip()
    language = LANGUAGE_MAP.get(choice)
    if language is None:
        await send_text_message(phone, "❌ Kripya 1, 2 ya 3 bhejiye.")
        return

    _update_user(phone, {
        "language_preference": language,
        "onboarding_step": OnboardingStep.COMPLETED.value,
    })

    # Build an updated user model for eligibility counting
    user.language_preference = language
    user.onboarding_step = OnboardingStep.COMPLETED.value

    try:
        eligible_count = fetch_eligible_notification_count(user)
    except Exception:
        logger.exception("Failed to fetch eligible count for %s", phone)
        eligible_count = 0

    await send_text_message(phone, tpl.profile_complete(eligible_count))


# ------------------------------------------------------------------
# Main router
# ------------------------------------------------------------------

# Maps each onboarding step to the handler that processes the user's
# response for that step.
_STEP_HANDLERS = {
    OnboardingStep.STARTED.value: _handle_name,
    OnboardingStep.NAME.value: _handle_name,
    OnboardingStep.DOB.value: _handle_dob,
    OnboardingStep.QUALIFICATION.value: _handle_qualification,
    OnboardingStep.STREAM.value: _handle_stream,
    OnboardingStep.STATE.value: _handle_state,
    OnboardingStep.CATEGORY.value: _handle_category,
    OnboardingStep.GENDER.value: _handle_gender,
    OnboardingStep.PWD.value: _handle_pwd,
    OnboardingStep.EX_SERVICEMAN.value: _handle_ex_serviceman,
    OnboardingStep.EXAM_PREFS.value: _handle_exam_prefs,
}


async def handle_onboarding(
    phone: str, message_text: str, user: UserProfile
) -> None:
    """Route incoming message to the correct onboarding step handler.

    Args:
        phone: User's phone number.
        message_text: The raw text the user sent.
        user: Current UserProfile from the database.
    """
    step = user.onboarding_step

    if step == OnboardingStep.LANGUAGE.value:
        await _handle_language(phone, message_text, user)
        return

    handler = _STEP_HANDLERS.get(step)
    if handler is None:
        logger.warning("Unknown onboarding step '%s' for phone %s", step, phone)
        await send_text_message(
            phone,
            "Kuch gadbad ho gayi. Kripya *help* bhejiye ya dubara try karein."
        )
        return

    await handler(phone, message_text)
