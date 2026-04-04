from __future__ import annotations
"""
LLM-assisted eligibility parser for government job notifications.
Uses Groq (Llama) for fast, free structured data extraction,
with a regex-based fallback when the API is unavailable.
"""

import json
import re
import logging
from datetime import date
from typing import Any, Optional

from groq import Groq

from config import get_settings
from scraping.parsers.date_parser import extract_dates

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """\
You are an expert at parsing Indian government job notifications.
Extract the following structured data from the notification text provided.

Return ONLY valid JSON with these exact keys (use null for missing values):

{
  "recruiting_body": "string — organization issuing the notification",
  "post_name": "string — name of the post/position",
  "exam_category": "one of: Railway, SSC, Banking, Defence, Teaching, State_PSC, UPSC, Police",
  "min_qualification": "one of: 8th, 10th, 12th, ITI, Diploma, Graduate, Postgraduate",
  "qualification_stream": "string or null — specific stream/subject if mentioned",
  "min_age": integer or null,
  "max_age": integer or null,
  "obc_relaxation": integer (default 3),
  "sc_st_relaxation": integer (default 5),
  "ews_relaxation": integer (default 0),
  "pwd_relaxation": integer (default 10),
  "ex_serviceman_relaxation": integer (default 5),
  "gender_restriction": ["Male"] or ["Female"] or null,
  "state_restriction": "state name or null",
  "application_start_date": "YYYY-MM-DD or null",
  "application_end_date": "YYYY-MM-DD or null",
  "exam_date": "YYYY-MM-DD or null",
  "total_vacancies": integer or null,
  "vacancy_breakdown": {"General": int, "OBC": int, "SC": int, "ST": int, "EWS": int} or null,
  "application_fee": {"General": int, "OBC": int, "SC_ST": int, "Female": int} or null,
  "documents_needed": ["list of document names"] or null,
  "summary_hindi": "2-3 sentence summary in Hindi",
  "summary_english": "2-3 sentence summary in English"
}

Important:
- For age relaxation, extract the YEARS of relaxation (e.g., "3 years for OBC" → obc_relaxation: 3)
- For qualification, map to the closest standard level
- Dates must be in YYYY-MM-DD format
- If exam_category is unclear, make your best guess from the recruiting body name

Notification text:
"""


def parse_with_llm(text: str) -> Optional[dict[str, Any]]:
    """
    Use Groq (Llama) to extract structured notification data from raw text.

    Args:
        text: Raw notification text from PDF or HTML.

    Returns:
        Dict of extracted fields matching the Notification model, or None on failure.
    """
    settings = get_settings()
    if not settings.groq_api_key:
        logger.warning("Groq API key not configured, skipping LLM parsing")
        return None

    # Truncate very long texts to stay within token limits
    max_chars = 12000
    truncated = text[:max_chars] if len(text) > max_chars else text

    try:
        client = Groq(api_key=settings.groq_api_key)
        completion = client.chat.completions.create(
            model=settings.groq_model,
            max_tokens=2000,
            temperature=0.1,  # low temp for factual extraction
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert at parsing Indian government job notifications. Always respond with valid JSON only, no markdown formatting.",
                },
                {
                    "role": "user",
                    "content": EXTRACTION_PROMPT + truncated,
                },
            ],
        )

        response_text = completion.choices[0].message.content.strip()

        # Strip markdown code blocks if model adds them anyway
        json_match = re.search(r"```(?:json)?\s*(.*?)```", response_text, re.DOTALL)
        if json_match:
            response_text = json_match.group(1).strip()

        parsed = json.loads(response_text)
        logger.info(
            "LLM parsing successful (model=%s) for: %s",
            settings.groq_model,
            parsed.get("post_name", "unknown"),
        )
        return _normalize_llm_output(parsed)

    except json.JSONDecodeError as e:
        logger.error("Failed to parse LLM JSON response: %s", e)
        return None
    except Exception as e:
        logger.error("Groq API error: %s", e)
        return None


def _normalize_llm_output(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize and validate LLM output to match Notification model fields."""
    valid_qualifications = {"8th", "10th", "12th", "ITI", "Diploma", "Graduate", "Postgraduate"}
    valid_categories = {
        "Railway", "SSC", "Banking", "Defence", "Teaching",
        "State_PSC", "UPSC", "Police",
    }

    # Validate qualification
    qual = data.get("min_qualification")
    if qual and qual not in valid_qualifications:
        # Try fuzzy matching
        qual_lower = qual.lower()
        for v in valid_qualifications:
            if v.lower() in qual_lower or qual_lower in v.lower():
                data["min_qualification"] = v
                break
        else:
            data["min_qualification"] = None

    # Validate exam category
    cat = data.get("exam_category")
    if cat and cat not in valid_categories:
        data["exam_category"] = None

    # Ensure integer fields
    for field in [
        "min_age", "max_age", "total_vacancies",
        "obc_relaxation", "sc_st_relaxation", "ews_relaxation",
        "pwd_relaxation", "ex_serviceman_relaxation",
    ]:
        val = data.get(field)
        if val is not None:
            try:
                data[field] = int(val)
            except (ValueError, TypeError):
                data[field] = None

    # Validate date strings
    for field in ["application_start_date", "application_end_date", "exam_date"]:
        val = data.get(field)
        if val:
            try:
                date.fromisoformat(val)
            except (ValueError, TypeError):
                data[field] = None

    return data


# ---------------------------------------------------------------------------
# Regex-based fallback parser
# ---------------------------------------------------------------------------

def _extract_age_range(text: str) -> tuple[Optional[int], Optional[int]]:
    """Extract min/max age from text using regex."""
    # Patterns like "18-25 years", "Age: 18 to 30", "18 से 25 वर्ष"
    patterns = [
        r"(?:age|आयु)[^\d]*(\d{2})\s*(?:to|से|-|–)\s*(\d{2})\s*(?:years|वर्ष|yrs)?",
        r"(\d{2})\s*(?:to|से|-|–)\s*(\d{2})\s*(?:years|वर्ष|yrs)",
        r"min(?:imum)?\s*age[^\d]*(\d{2})",
        r"max(?:imum)?\s*age[^\d]*(\d{2})",
    ]
    text_lower = text.lower()

    for pattern in patterns[:2]:
        match = re.search(pattern, text_lower)
        if match:
            return int(match.group(1)), int(match.group(2))

    min_age = None
    max_age = None
    min_match = re.search(patterns[2], text_lower)
    max_match = re.search(patterns[3], text_lower)
    if min_match:
        min_age = int(min_match.group(1))
    if max_match:
        max_age = int(max_match.group(1))
    return min_age, max_age


def _extract_vacancies(text: str) -> Optional[int]:
    """Extract total vacancy count."""
    patterns = [
        r"total\s*(?:vacancies|posts|vacancy)[^\d]*(\d+)",
        r"(\d+)\s*(?:vacancies|posts|पद)",
        r"कुल\s*पद[^\d]*(\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text.lower())
        if match:
            num = int(match.group(1))
            if 1 <= num <= 500000:  # sanity check
                return num
    return None


def _extract_qualification(text: str) -> Optional[str]:
    """Extract qualification level from text."""
    text_lower = text.lower()
    # Check from highest to lowest to get minimum required
    qual_keywords = {
        "Postgraduate": ["post graduate", "postgraduate", "pg ", "m.a.", "m.sc", "m.tech", "mba", "m.com", "स्नातकोत्तर"],
        "Graduate": ["graduate", "graduation", "b.a.", "b.sc", "b.tech", "b.com", "b.e.", "degree", "स्नातक"],
        "Diploma": ["diploma", "डिप्लोमा"],
        "ITI": ["iti", "industrial training", "आईटीआई"],
        "12th": ["12th", "12 th", "intermediate", "higher secondary", "+2", "इंटरमीडिएट", "12वीं"],
        "10th": ["10th", "10 th", "matric", "matriculation", "ssc", "high school", "हाई स्कूल", "10वीं"],
        "8th": ["8th", "8 th", "eighth", "middle", "8वीं"],
    }

    for qual, keywords in qual_keywords.items():
        for kw in keywords:
            if kw in text_lower:
                return qual
    return None


def _extract_fee(text: str) -> Optional[dict[str, int]]:
    """Extract application fee details."""
    fees: dict[str, int] = {}
    text_lower = text.lower()

    patterns = [
        (r"(?:general|ur|gen)[^\d]*(?:rs\.?|₹)\s*(\d+)", "General"),
        (r"(?:obc)[^\d]*(?:rs\.?|₹)\s*(\d+)", "OBC"),
        (r"(?:sc|st|sc/st)[^\d]*(?:rs\.?|₹)\s*(\d+)", "SC_ST"),
        (r"(?:female|महिला)[^\d]*(?:rs\.?|₹)\s*(\d+)", "Female"),
    ]

    for pattern, category in patterns:
        match = re.search(pattern, text_lower)
        if match:
            fees[category] = int(match.group(1))

    return fees if fees else None


def parse_with_regex(text: str) -> dict[str, Any]:
    """
    Regex-based fallback parser for when the LLM API is unavailable.

    Extracts what it can from the raw text using pattern matching.
    Less accurate than LLM but works offline.

    Args:
        text: Raw notification text.

    Returns:
        Dict of extracted fields (may have many None values).
    """
    min_age, max_age = _extract_age_range(text)
    dates = extract_dates(text)

    result: dict[str, Any] = {
        "min_qualification": _extract_qualification(text),
        "min_age": min_age,
        "max_age": max_age,
        "total_vacancies": _extract_vacancies(text),
        "application_fee": _extract_fee(text),
        "application_start_date": dates.get("application_start_date"),
        "application_end_date": dates.get("application_end_date"),
        "exam_date": dates.get("exam_date"),
    }

    return result


def parse_notification(text: str) -> dict[str, Any]:
    """
    Parse notification text into structured data.

    Tries the LLM parser first, falls back to regex if that fails.

    Args:
        text: Raw notification text from PDF or HTML.

    Returns:
        Dict of extracted fields matching Notification model fields.
    """
    if not text or not text.strip():
        logger.warning("Empty text passed to parse_notification")
        return {}

    # Try LLM first
    result = parse_with_llm(text)
    if result:
        return result

    # Fallback to regex
    logger.info("Falling back to regex parser")
    return parse_with_regex(text)
