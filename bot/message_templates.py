from __future__ import annotations
"""
Hinglish message templates for the Sarkari Naukri Alert Bot.

All user-facing messages live here so they are easy to update and localise.
"""

from database.models import Notification, UserProfile


# ------------------------------------------------------------------
# Onboarding step messages
# ------------------------------------------------------------------

def welcome_message() -> str:
    return (
        "🙏 *Namaste! Sarkari Naukri Alert Bot mein aapka swagat hai!*\n\n"
        "Hum aapko government job notifications bhejenge jo aapke liye eligible hain.\n\n"
        "Pehle kuch basic details chahiye taaki hum aapke liye sahi jobs dhundh sakein.\n\n"
        "Chaliye shuru karte hain! 💪\n\n"
        "Sabse pehle, aapka *naam* bataiye:"
    )


def ask_name() -> str:
    return "Aapka *poora naam* bataiye (jaise: Rajesh Kumar):"


def ask_dob() -> str:
    return (
        "📅 Aapki *date of birth* bataiye\n"
        "Format: DD/MM/YYYY\n"
        "(jaise: 15/08/1995)"
    )


def ask_qualification() -> str:
    return (
        "🎓 Aapki *highest qualification* kya hai?\n\n"
        "Number bhejiye:\n"
        "1️⃣ 8th Pass\n"
        "2️⃣ 10th Pass\n"
        "3️⃣ 12th Pass\n"
        "4️⃣ ITI\n"
        "5️⃣ Diploma\n"
        "6️⃣ Graduate\n"
        "7️⃣ Postgraduate"
    )


def ask_stream() -> str:
    return (
        "📚 Aapka *stream/subject* kya hai?\n"
        "(jaise: Science, Commerce, Arts, Engineering, Medical, etc.)\n\n"
        "Agar applicable nahi hai toh *skip* bhejiye."
    )


def ask_state() -> str:
    return (
        "📍 Aapka *state/domicile* kya hai?\n"
        "(jaise: Uttar Pradesh, Bihar, Rajasthan, etc.)\n\n"
        "Ye isliye zaroori hai kyunki kuch jobs sirf "
        "specific state ke candidates ke liye hoti hain."
    )


def ask_category() -> str:
    return (
        "👤 Aapki *category* kya hai?\n\n"
        "Number bhejiye:\n"
        "1️⃣ General\n"
        "2️⃣ OBC\n"
        "3️⃣ SC\n"
        "4️⃣ ST\n"
        "5️⃣ EWS"
    )


def ask_gender() -> str:
    return (
        "Aapka *gender* kya hai?\n\n"
        "1️⃣ Male\n"
        "2️⃣ Female\n"
        "3️⃣ Other"
    )


def ask_pwd() -> str:
    return (
        "♿ Kya aap *PwD (Person with Disability)* category mein aate hain?\n\n"
        "1️⃣ Haan\n"
        "2️⃣ Nahi"
    )


def ask_ex_serviceman() -> str:
    return (
        "🎖️ Kya aap *Ex-Serviceman* hain?\n\n"
        "1️⃣ Haan\n"
        "2️⃣ Nahi"
    )


def ask_exam_prefs() -> str:
    return (
        "📋 Aap *kaun si exams* mein interested hain?\n\n"
        "Ek ya zyada number comma se bhejiye (jaise: 1,3,5):\n\n"
        "1️⃣ Railway (RRB)\n"
        "2️⃣ SSC\n"
        "3️⃣ Banking (IBPS/SBI)\n"
        "4️⃣ Defence\n"
        "5️⃣ Teaching\n"
        "6️⃣ State PSC\n"
        "7️⃣ UPSC\n"
        "8️⃣ Police"
    )


def ask_language() -> str:
    return (
        "🌐 Aapko alerts kis *language* mein chahiye?\n\n"
        "1️⃣ Hindi\n"
        "2️⃣ English\n"
        "3️⃣ Both (Hindi + English)"
    )


# ------------------------------------------------------------------
# Profile complete
# ------------------------------------------------------------------

def profile_complete(eligible_count: int) -> str:
    return (
        "✅ *Bahut badiya! Aapka profile complete ho gaya!*\n\n"
        f"🔍 Abhi aap *{eligible_count} active notifications* ke liye eligible hain.\n\n"
        "Ab se jab bhi koi nayi sarkari naukri aayegi jo aapke liye fit hogi, "
        "hum turant aapko alert bhejenge! 🔔\n\n"
        "Commands:\n"
        "• *status* - apna profile dekhein\n"
        "• *alerts* - recent eligible notifications\n"
        "• *help* - sabhi commands"
    )


# ------------------------------------------------------------------
# New alert
# ------------------------------------------------------------------

def format_new_alert(notification: Notification, user: UserProfile) -> str:
    """Format a rich individual job alert — only shows fields that are actually available."""

    # --- Category badge ---
    cat_emoji = {
        "Railway": "🚂", "SSC": "📋", "Banking": "🏦", "Defence": "🪖",
        "Teaching": "📚", "State_PSC": "🏛️", "UPSC": "🎯", "Police": "👮",
        "PSU": "🏭", "Healthcare": "🏥", "Insurance": "📄",
        "Postal": "📬", "Judiciary": "⚖️",
    }.get(notification.exam_category, "📢")

    # --- Build detail lines — only include what is actually known ---
    # --- Header (always shown) ---
    header = [
        f"{cat_emoji} *{notification.post_name}*",
        f"🏢 {notification.recruiting_body}",
    ]

    # --- Detail fields (only shown when available) ---
    details = []

    if notification.total_vacancies:
        details.append(f"📌 *Posts:* {notification.total_vacancies:,}")

    if notification.min_qualification:
        qual = notification.min_qualification
        if notification.qualification_stream:
            qual += f" ({notification.qualification_stream})"
        details.append(f"🎓 *Qualification:* {qual}")

    if notification.min_age or notification.max_age:
        if notification.min_age and notification.max_age:
            age_str = f"{notification.min_age}–{notification.max_age} years"
        elif notification.max_age:
            age_str = f"Up to {notification.max_age} years"
        else:
            age_str = f"Min {notification.min_age} years"
        details.append(f"👤 *Age Limit:* {age_str}")

    if notification.application_fee:
        parts = []
        for key in ("General", "OBC", "SC", "ST", "EWS"):
            val = notification.application_fee.get(key)
            if val is not None:
                parts.append(f"{key}: ₹{val}" if val else f"{key}: Free")
        if parts:
            details.append(f"💰 *Fee:* {' | '.join(parts)}")

    if notification.application_start_date:
        details.append(f"📅 *Apply From:* {notification.application_start_date.strftime('%d %b %Y')}")
    if notification.application_end_date:
        details.append(f"⏳ *Last Date:* {notification.application_end_date.strftime('%d %b %Y')}")
    if notification.exam_date:
        details.append(f"🗓️ *Exam Date:* {notification.exam_date.strftime('%d %b %Y')}")
    if notification.admit_card_date:
        details.append(f"🪪 *Admit Card:* {notification.admit_card_date.strftime('%d %b %Y')}")

    # --- Apply link (always shown) ---
    apply_link = notification.source_url or notification.official_website or ""
    footer = [
        f"🔗 *Apply / Full Details:*",
        apply_link if apply_link else "Check official website",
    ]

    # --- Assemble with separator only when there are details ---
    lines = header
    if details:
        lines.append("━━━━━━━━━━━━━━━━━━━")
        lines.extend(details)
    lines.append("━━━━━━━━━━━━━━━━━━━")
    lines.extend(footer)

    return "\n".join(lines)


# ------------------------------------------------------------------
# Deadline reminder
# ------------------------------------------------------------------

def format_deadline_reminder(notification: Notification, days_left: int) -> str:
    end_date = (
        notification.application_end_date.strftime("%d %b %Y")
        if notification.application_end_date
        else "N/A"
    )
    return (
        f"⏰ *DEADLINE ALERT - {days_left} DAYS LEFT*\n\n"
        f"*{notification.post_name}* - Last date: {end_date}\n\n"
        "Kya aapne apply kar diya?\n\n"
        "1️⃣ Haan, apply ho gaya ✅\n"
        "2️⃣ Nahi, abhi karna hai\n"
        "3️⃣ Mujhe help chahiye form bharne mein"
    )


# ------------------------------------------------------------------
# Weekly digest
# ------------------------------------------------------------------

def format_weekly_digest(
    notifications: list[Notification], user: UserProfile
) -> str:
    if not notifications:
        return (
            "📊 *Weekly Digest*\n\n"
            "Is hafte koi nayi eligible notification nahi aayi.\n"
            "Chinta mat kijiye, hum nazar rakh rahe hain! 👀"
        )

    header = (
        f"📊 *Weekly Digest - {len(notifications)} Nayi Eligible Jobs!*\n\n"
        f"Namaste {user.name or 'User'}! Ye rahi is hafte ki nayi "
        f"sarkari naukri notifications:\n\n"
    )

    items = []
    for i, n in enumerate(notifications, 1):
        end = (
            n.application_end_date.strftime("%d %b")
            if n.application_end_date
            else "N/A"
        )
        items.append(
            f"{i}. *{n.post_name}*\n"
            f"   📋 {n.total_vacancies or 'N/A'} posts | "
            f"📅 Last date: {end}"
        )

    footer = (
        "\n\nKisi bhi notification ka detail dekhne ke liye uska number bhejiye.\n"
        "Ya *alerts* bhejiye sabhi dekhne ke liye."
    )

    return header + "\n".join(items) + footer


# ------------------------------------------------------------------
# Command responses
# ------------------------------------------------------------------

def profile_summary(user: UserProfile) -> str:
    return (
        "👤 *Aapka Profile:*\n\n"
        f"📛 Name: {user.name or 'N/A'}\n"
        f"🎂 DOB: {user.date_of_birth or 'N/A'}\n"
        f"🎓 Qualification: {user.qualification or 'N/A'}\n"
        f"📚 Stream: {user.qualification_stream or 'N/A'}\n"
        f"📍 State: {user.state_domicile or 'N/A'}\n"
        f"👤 Category: {user.category or 'N/A'}\n"
        f"⚧ Gender: {user.gender or 'N/A'}\n"
        f"♿ PwD: {'Haan' if user.pwd_status else 'Nahi'}\n"
        f"🎖️ Ex-Serviceman: {'Haan' if user.ex_serviceman else 'Nahi'}\n"
        f"📋 Exam Prefs: {', '.join(user.exam_preferences) if user.exam_preferences else 'N/A'}\n"
        f"🌐 Language: {user.language_preference}\n"
        f"📦 Subscription: {user.subscription_tier}"
    )


def help_message() -> str:
    return (
        "ℹ️ *Available Commands:*\n\n"
        "• *status* / *profile* - Apna profile dekhein\n"
        "• *alerts* - Recent eligible notifications dekhein\n"
        "• *help* - Ye help message\n\n"
        "Koi bhi sawal ho toh yahan likh dijiye!"
    )


def generic_response() -> str:
    return (
        "🤔 Samajh nahi aaya. Kripya niche diye gaye commands use karein:\n\n"
        "• *status* - Apna profile dekhein\n"
        "• *alerts* - Recent notifications\n"
        "• *help* - Sabhi commands"
    )
