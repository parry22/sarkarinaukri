from __future__ import annotations
"""
Notification detail enricher.

For notifications that were scraped from aggregator sites (SarkariResult,
FreeJobAlert, SarkariExam, etc.) and therefore only have post_name +
source_url, this module visits the source URL, extracts structured job
details from the page, and updates the Supabase record.

Also hands off any official PDF it finds to the existing PDF parser.

Supported sources (auto-detected by domain):
    - sarkariresult.com / sarkariresults.org.in
    - freejobalert.com
    - sarkariexam.com
    - rojgarresult.com
    - sarkarinaukriblog.com
    - govtjobsalert.com
    - Generic fallback: scans any page for common patterns

Pipeline:
    enrich_notification(notification_dict) -> dict   # enriched copy
    enrich_pending_notifications(limit=50)           # batch DB job
"""

import logging
import re
import time
from datetime import date
from typing import Any, Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from database.connection import get_supabase

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9,hi;q=0.8",
}

_SESSION = requests.Session()
_SESSION.headers.update(_HEADERS)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fetch(url: str) -> Optional[BeautifulSoup]:
    try:
        resp = _SESSION.get(url, timeout=20)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")
    except Exception as exc:
        logger.warning("Enricher fetch failed for %s: %s", url, exc)
        return None


def _parse_date_text(text: str) -> Optional[date]:
    """Try common Indian date formats in a string."""
    patterns = [
        r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})",       # 15/03/2026
        r"(\d{1,2})\s+(\w+)\s+(\d{4})",              # 15 March 2026
        r"(\w+)\s+(\d{4})",                           # March 2026 (month only)
    ]
    months = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        "january": 1, "february": 2, "march": 3, "april": 4, "june": 6,
        "july": 7, "august": 8, "september": 9, "october": 10,
        "november": 11, "december": 12,
    }

    m = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", text)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass

    m = re.search(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", text)
    if m:
        mo = months.get(m.group(2).lower())
        if mo:
            try:
                return date(int(m.group(3)), mo, int(m.group(1)))
            except ValueError:
                pass

    return None


def _extract_int(text: str) -> Optional[int]:
    """Extract the first integer from a string."""
    m = re.search(r"[\d,]+", text)
    if m:
        try:
            return int(m.group().replace(",", ""))
        except ValueError:
            pass
    return None


def _domain(url: str) -> str:
    return urlparse(url).netloc.lower().replace("www.", "")


# ---------------------------------------------------------------------------
# SarkariResult parser (primary aggregator — most structured)
# ---------------------------------------------------------------------------

def _parse_sarkariresult(soup: BeautifulSoup, url: str) -> dict[str, Any]:
    """
    SarkariResult detail pages have a consistent 3-column table layout:
      col1: label  |  col2: value  |  col3: (sometimes more)

    Key sections: Important Dates | Application Fee | Age Limit | Vacancy Details
    """
    data: dict[str, Any] = {}
    full_text = soup.get_text(" ", strip=True).lower()

    # Find the main data table (usually the last/largest table on page)
    tables = soup.find_all("table")
    if not tables:
        return data

    # Concatenate all table text for regex extraction
    table_text = " ".join(t.get_text(" ", strip=True) for t in tables)

    # --- Dates ---
    for label, key in [
        (r"application begin\s*[:\|]?\s*([\d/\- A-Za-z]+?)(?:last|pay|exam|\||$)", "application_start_date"),
        (r"last date(?:\s+for\s+apply\s+online)?\s*[:\|]?\s*([\d/\- A-Za-z]+?)(?:pay|exam|admit|\||$)", "application_end_date"),
        (r"exam date\s*[:\|]?\s*([\d/\- A-Za-z]+?)(?:admit|\||$)", "exam_date"),
        (r"admit card\s+(?:available\s*)?[:\|]?\s*([\d/\- A-Za-z]+?)(?:how|\||$)", "admit_card_date"),
    ]:
        m = re.search(label, table_text, re.IGNORECASE)
        if m:
            parsed = _parse_date_text(m.group(1).strip())
            if parsed:
                data[key] = parsed.isoformat()

    # --- Vacancies ---
    m = re.search(
        r"(?:total|vacancy|vacancies|post)\s*[:\|]?\s*([\d,]+)\s*(?:post|vacancy|vacancies)?",
        table_text, re.IGNORECASE
    )
    if m:
        v = _extract_int(m.group(1))
        if v and 1 <= v <= 500_000:
            data["total_vacancies"] = v

    # --- Age ---
    min_age = re.search(r"minimum age\s*[:\|]?\s*(\d+)", table_text, re.IGNORECASE)
    max_age = re.search(r"maximum age\s*[:\|]?\s*(\d+)", table_text, re.IGNORECASE)
    if min_age:
        data["min_age"] = int(min_age.group(1))
    if max_age:
        data["max_age"] = int(max_age.group(1))

    # --- Fee ---
    fee: dict[str, str] = {}
    for cat, pattern in [
        ("General", r"general\s*/?\s*(?:obc\s*/?\s*ews\s*[:\|]?\s*([\d,]+)|[:\|]?\s*([\d,]+))"),
        ("OBC",     r"obc\s*[:\|]?\s*([\d,]+)"),
        ("SC",      r"sc\s*/?\s*(?:st)?\s*[:\|]?\s*([\d,]+)"),
        ("ST",      r"st\s*[:\|]?\s*([\d,]+)"),
        ("EWS",     r"ews\s*[:\|]?\s*([\d,]+)"),
    ]:
        m = re.search(pattern, table_text, re.IGNORECASE)
        if m:
            val = next((g for g in m.groups() if g), None)
            if val:
                fee[cat] = val.replace(",", "")
    if fee:
        data["application_fee"] = fee

    # --- Qualification ---
    qual_map = {
        "10th": "10th", "matriculation": "10th",
        "12th": "12th", "intermediate": "12th", "higher secondary": "12th",
        "iti": "ITI",
        "diploma": "Diploma",
        "bachelor": "Graduate", "graduation": "Graduate", "degree": "Graduate",
        "graduate": "Graduate",
        "post graduate": "Postgraduate", "postgraduate": "Postgraduate",
        "master": "Postgraduate", "mba": "Postgraduate",
    }
    for kw, qual in qual_map.items():
        if kw in full_text:
            data["min_qualification"] = qual
            break

    # --- Official website & PDF ---
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True).lower()
        if ".pdf" in href.lower() and "official" not in data:
            data["pdf_url"] = href
        if any(kw in text for kw in ["official website", "apply online", "apply here", "official notification"]):
            data["official_website"] = href

    return data


# ---------------------------------------------------------------------------
# Generic parser (fallback for all other aggregators)
# ---------------------------------------------------------------------------

def _parse_generic(soup: BeautifulSoup, url: str) -> dict[str, Any]:
    """
    Generic extraction using regex on full page text.
    Works reasonably well on FreeJobAlert, SarkariExam, RojgarResult etc.
    which have similar but less structured layouts.
    """
    data: dict[str, Any] = {}
    text = soup.get_text(" ", strip=True)

    # Dates — look for common label patterns
    date_patterns = [
        (r"(?:last date|closing date|end date)\s*[:\-–]?\s*([\d/\-\. A-Za-z]+?)(?:\n|\.|\|)", "application_end_date"),
        (r"(?:start date|opening date|apply from|begin)\s*[:\-–]?\s*([\d/\-\. A-Za-z]+?)(?:\n|\.|\|)", "application_start_date"),
        (r"(?:exam date|written test)\s*[:\-–]?\s*([\d/\-\. A-Za-z]+?)(?:\n|\.|\|)", "exam_date"),
    ]
    for pattern, key in date_patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            parsed = _parse_date_text(m.group(1).strip())
            if parsed:
                data[key] = parsed.isoformat()

    # Vacancies
    m = re.search(
        r"(?:total\s+)?(?:vacancy|vacancies|posts?|seats?)\s*[:\-–]?\s*([\d,]+)",
        text, re.IGNORECASE
    )
    if m:
        v = _extract_int(m.group(1))
        if v and 1 <= v <= 500_000:
            data["total_vacancies"] = v

    # Age
    m = re.search(r"age\s+limit\s*[:\-–]?\s*(\d+)\s*(?:to|-)\s*(\d+)", text, re.IGNORECASE)
    if m:
        data["min_age"] = int(m.group(1))
        data["max_age"] = int(m.group(2))

    # Qualification
    qual_map = {
        "10th": "10th", "matriculation": "10th",
        "12th": "12th", "intermediate": "12th",
        "iti": "ITI", "diploma": "Diploma",
        "bachelor": "Graduate", "graduate": "Graduate", "graduation": "Graduate",
        "postgraduate": "Postgraduate", "post graduate": "Postgraduate",
        "master": "Postgraduate",
    }
    text_lower = text.lower()
    for kw, qual in qual_map.items():
        if kw in text_lower:
            data["min_qualification"] = qual
            break

    # PDF and official links
    for a in soup.find_all("a", href=True):
        href = a["href"]
        link_text = a.get_text(strip=True).lower()
        if ".pdf" in href.lower() and "pdf_url" not in data:
            data["pdf_url"] = href
        if any(kw in link_text for kw in ["official website", "apply online", "official notification", "apply here"]):
            data["official_website"] = href

    return data


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def enrich_notification(source_url: str) -> dict[str, Any]:
    """
    Fetch a notification's source URL and extract all available details.
    Returns a dict of enriched fields (only non-None values).
    """
    if not source_url:
        return {}

    soup = _fetch(source_url)
    if soup is None:
        return {}

    domain = _domain(source_url)

    if "sarkariresult" in domain:
        enriched = _parse_sarkariresult(soup, source_url)
    else:
        # Generic fallback for all other aggregators
        enriched = _parse_generic(soup, source_url)

    # If we found a PDF, also run the LLM parser on it for deeper extraction
    pdf_url = enriched.get("pdf_url")
    if pdf_url:
        try:
            from scraping.parsers.pdf_parser import extract_text_from_pdf
            from scraping.parsers.eligibility_parser import parse_notification as llm_parse
            pdf_text = extract_text_from_pdf(pdf_url)
            if pdf_text:
                llm_data = llm_parse(pdf_text)
                # LLM data fills any gaps the page scraper missed
                for k, v in llm_data.items():
                    if v is not None and k not in enriched:
                        enriched[k] = v
        except Exception as exc:
            logger.warning("PDF enrichment failed for %s: %s", pdf_url, exc)

    logger.info(
        "Enriched %s → fields added: %s",
        source_url[:80],
        [k for k, v in enriched.items() if v is not None],
    )
    return enriched


# ---------------------------------------------------------------------------
# Batch enricher — runs as a scheduled job
# ---------------------------------------------------------------------------

def enrich_pending_notifications(limit: int = 30) -> int:
    """
    Find notifications missing key fields, enrich them, and update DB.
    Returns count of successfully enriched records.
    """
    client = get_supabase()

    # Fetch notifications that have a source_url but are missing key details
    response = (
        client.table("notifications")
        .select("id, source_url, recruiting_body, post_name, total_vacancies, "
                "min_qualification, min_age, max_age, application_end_date")
        .is_("total_vacancies", "null")
        .not_.is_("source_url", "null")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )

    rows = response.data or []
    if not rows:
        logger.info("No notifications to enrich")
        return 0

    enriched_count = 0

    for row in rows:
        notif_id = row["id"]
        source_url = row.get("source_url", "")

        if not source_url:
            continue

        # Skip official govt site URLs — they need the PDF parser, not this enricher
        domain = _domain(source_url)
        if any(official in domain for official in [
            "ssc.gov.in", "upsc.gov.in", "rrbcdg.gov.in", "ibps.in",
            "nta.ac.in", "sbi.co.in", "rbi.org.in", ".nic.in", ".gov.in",
        ]):
            continue

        try:
            enriched = enrich_notification(source_url)
            if not enriched:
                continue

            # Only update fields that are currently NULL — don't overwrite existing data
            update_data = {k: v for k, v in enriched.items() if v is not None}
            if not update_data:
                continue

            client.table("notifications").update(update_data).eq("id", notif_id).execute()
            enriched_count += 1
            logger.info(
                "Updated notification %s (%s): %s",
                notif_id[:8],
                row.get("post_name", "")[:40],
                list(update_data.keys()),
            )

            # Be polite — 1 second between requests
            time.sleep(1)

        except Exception as exc:
            logger.error("Failed to enrich notification %s: %s", notif_id, exc)

    logger.info("Enrichment run complete: %d/%d enriched", enriched_count, len(rows))
    return enriched_count
