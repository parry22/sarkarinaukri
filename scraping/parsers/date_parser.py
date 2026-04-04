from __future__ import annotations
"""
Date parser for extracting dates from Indian government notification text.
Handles multiple formats commonly found in sarkari job notifications.
"""

import re
import logging
from datetime import date
from typing import Optional

from dateutil import parser as dateutil_parser

logger = logging.getLogger(__name__)

# Hindi month names to English mapping
HINDI_MONTH_MAP: dict[str, str] = {
    "जनवरी": "January",
    "फरवरी": "February",
    "मार्च": "March",
    "अप्रैल": "April",
    "मई": "May",
    "जून": "June",
    "जुलाई": "July",
    "अगस्त": "August",
    "सितंबर": "September",
    "सितम्बर": "September",
    "अक्टूबर": "October",
    "अक्तूबर": "October",
    "नवंबर": "November",
    "नवम्बर": "November",
    "दिसंबर": "December",
    "दिसम्बर": "December",
}

# Keywords that indicate what type of date it is
DATE_TYPE_KEYWORDS: dict[str, list[str]] = {
    "application_start_date": [
        "application start",
        "apply from",
        "starting date",
        "start date",
        "online apply start",
        "registration start",
        "आवेदन शुरू",
        "आवेदन प्रारंभ",
    ],
    "application_end_date": [
        "last date",
        "application end",
        "last date to apply",
        "closing date",
        "end date",
        "last date of application",
        "अंतिम तिथि",
        "आवेदन की अंतिम",
        "last date for online application",
    ],
    "exam_date": [
        "exam date",
        "examination date",
        "date of exam",
        "written test",
        "cbt date",
        "computer based test",
        "परीक्षा तिथि",
        "परीक्षा की तारीख",
    ],
    "admit_card_date": [
        "admit card",
        "hall ticket",
        "call letter",
        "admit card date",
        "प्रवेश पत्र",
        "एडमिट कार्ड",
    ],
}

# Date patterns in order of specificity
DATE_PATTERNS: list[re.Pattern] = [
    # 15 May 2026 / 15 January 2026
    re.compile(
        r"(\d{1,2})\s+"
        r"(January|February|March|April|May|June|July|August|September|October|November|December)"
        r"\s+(\d{4})",
        re.IGNORECASE,
    ),
    # 15-05-2026 or 15/05/2026 or 15.05.2026
    re.compile(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})"),
    # 2026-05-15 (ISO format)
    re.compile(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})"),
    # 15 May, 2026 (with comma)
    re.compile(
        r"(\d{1,2})\s+"
        r"(January|February|March|April|May|June|July|August|September|October|November|December)"
        r",?\s+(\d{4})",
        re.IGNORECASE,
    ),
]

# Hindi date pattern: "15 मई 2026"
HINDI_DATE_PATTERN = re.compile(
    r"(\d{1,2})\s+("
    + "|".join(re.escape(m) for m in HINDI_MONTH_MAP.keys())
    + r")\s+(\d{4})"
)


def _replace_hindi_months(text: str) -> str:
    """Replace Hindi month names with English equivalents."""
    result = text
    for hindi, english in HINDI_MONTH_MAP.items():
        result = result.replace(hindi, english)
    return result


def _parse_single_date(date_str: str) -> Optional[date]:
    """Try to parse a single date string into a date object."""
    try:
        parsed = dateutil_parser.parse(date_str, dayfirst=True)
        return parsed.date()
    except (ValueError, TypeError):
        return None


def extract_all_dates(text: str) -> list[tuple[date, str, int]]:
    """
    Extract all dates found in the text.

    Returns:
        List of (date, matched_string, position_in_text) tuples.
    """
    results: list[tuple[date, str, int]] = []
    seen_positions: set[int] = set()

    # Replace Hindi months first for uniform processing
    normalized = _replace_hindi_months(text)

    # Also try original text for Hindi date pattern
    for match in HINDI_DATE_PATTERN.finditer(text):
        day, hindi_month, year = match.groups()
        eng_month = HINDI_MONTH_MAP.get(hindi_month)
        if eng_month:
            date_str = f"{day} {eng_month} {year}"
            parsed = _parse_single_date(date_str)
            if parsed:
                pos = match.start()
                if pos not in seen_positions:
                    results.append((parsed, match.group(), pos))
                    seen_positions.add(pos)

    # Try each pattern on normalized text
    for pattern in DATE_PATTERNS:
        for match in pattern.finditer(normalized):
            parsed = _parse_single_date(match.group())
            if parsed:
                pos = match.start()
                if pos not in seen_positions:
                    results.append((parsed, match.group(), pos))
                    seen_positions.add(pos)

    # Sort by position in text
    results.sort(key=lambda x: x[2])
    return results


def _find_date_type(text: str, position: int, window: int = 80) -> Optional[str]:
    """
    Look at surrounding text to determine what type of date this is.

    Uses a smaller window and picks the *closest* keyword match so that
    when multiple dates appear close together, each is classified by its
    own nearest context keyword rather than a distant earlier one.

    Args:
        text: Full notification text (lowercased).
        position: Character position of the date in the text.
        window: Number of characters before the date to search for context.
    """
    start = max(0, position - window)
    context = text[start:position].lower()

    best_type = None
    best_pos = -1

    for date_type, keywords in DATE_TYPE_KEYWORDS.items():
        for keyword in keywords:
            kw_lower = keyword.lower()
            idx = context.rfind(kw_lower)
            if idx != -1 and idx > best_pos:
                best_pos = idx
                best_type = date_type

    return best_type


def extract_dates(text: str) -> dict[str, date]:
    """
    Extract and classify dates from notification text.

    Scans the text for dates in various Indian formats, then uses surrounding
    context to classify each date as application_start_date, application_end_date,
    exam_date, or admit_card_date.

    Args:
        text: Raw notification text (from PDF or HTML).

    Returns:
        Dict mapping date type keys to date objects, e.g.:
        {
            "application_start_date": date(2026, 5, 1),
            "application_end_date": date(2026, 5, 31),
            "exam_date": date(2026, 7, 15),
        }
    """
    if not text or not text.strip():
        return {}

    all_dates = extract_all_dates(text)
    if not all_dates:
        return {}

    classified: dict[str, date] = {}
    text_lower = text.lower()

    for parsed_date, _matched_str, position in all_dates:
        date_type = _find_date_type(text_lower, position)
        if date_type and date_type not in classified:
            classified[date_type] = parsed_date

    return classified
