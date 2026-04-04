from __future__ import annotations
"""
Scraper for teaching and education recruitment bodies in India.

Targets:
- Kendriya Vidyalaya Sangathan (KVS)
- Navodaya Vidyalaya Samiti (NVS)
- Army Public School (APS-CSB)
- Central Board of Secondary Education (CBSE)
- National Council of Educational Research & Training (NCERT)
- University Grants Commission (UGC)
"""

import re
from typing import Any, Optional

import requests
from bs4 import BeautifulSoup, Tag

from scraping.scrapers.base_scraper import BaseScraper

# ---------------------------------------------------------------------------
# Education sources
# ---------------------------------------------------------------------------

SOURCES: list[dict[str, Any]] = [
    {"name": "KVS", "base_url": "https://kvsangathan.nic.in", "paths": ["/", "/recruitment-section.html"], "recruiting_body": "Kendriya Vidyalaya Sangathan (KVS)"},
    {"name": "NVS", "base_url": "https://navodaya.gov.in", "paths": ["/", "/nvs-recruitment.htm"], "recruiting_body": "Navodaya Vidyalaya Samiti (NVS)"},
    {"name": "ArmyPublicSchool", "base_url": "https://aps-csb.in", "paths": ["/"], "recruiting_body": "Army Public School (APS-CSB)"},
    {"name": "CBSE", "base_url": "https://www.cbse.gov.in", "paths": ["/", "/newsite/attach/recruitment.html"], "recruiting_body": "Central Board of Secondary Education (CBSE)"},
    {"name": "NCERT", "base_url": "https://ncert.nic.in", "paths": ["/", "/vacancy.html"], "recruiting_body": "National Council of Educational Research & Training (NCERT)"},
    {"name": "UGC", "base_url": "https://www.ugc.gov.in", "paths": ["/", "/subpage/vacancies.aspx"], "recruiting_body": "University Grants Commission (UGC)"},
]

# ---------------------------------------------------------------------------
# Education-specific keywords that indicate a recruitment notification
# ---------------------------------------------------------------------------

_EDUCATION_KEYWORDS: dict[str, str] = {
    "teacher": "Teacher",
    "pgt": "Post Graduate Teacher (PGT)",
    "tgt": "Trained Graduate Teacher (TGT)",
    "prt": "Primary Teacher (PRT)",
    "principal": "Principal",
    "librarian": "Librarian",
    "counselor": "Counselor",
    "physical education": "Physical Education Teacher",
    "music teacher": "Music Teacher",
    "art teacher": "Art Teacher",
    "computer teacher": "Computer Teacher",
    "lab assistant": "Lab Assistant",
    "trainer": "Trainer",
    "coordinator": "Coordinator",
    "vice principal": "Vice Principal",
    "kvs": "KVS Recruitment",
    "nvs": "NVS Recruitment",
    "lecturer": "Lecturer",
}

# Broad CSS selectors to handle varying education site structures.
_CSS_SELECTORS: list[str] = [
    "table tr",
    ".content a",
    "article a",
    ".notification a",
    ".card a",
    "ul li a",
    ".list-group-item a",
    "#content a",
    "main a",
    ".container a",
    "marquee a",
    ".page-content a",
    "#ContentPlaceHolder1 a",
    ".recruitment a",
    ".vacancy a",
]

# Signals that a link text is about recruitment rather than general news.
_RECRUITMENT_SIGNALS: tuple[str, ...] = (
    "recruitment",
    "notification",
    "vacancy",
    "vacancies",
    "advt",
    "advertisement",
    "walk-in",
    "walk in",
    "hiring",
    "career",
    "apply",
    "application",
    "appointment",
    "contractual",
    "positions",
    "empanelment",
    "engagement",
    "bharti",
    "openings",
    "interview",
    "deputation",
)


class EducationScraper(BaseScraper):
    """
    Multi-source scraper for Indian education and teaching recruitment portals.

    Iterates over all configured education recruitment sites, fetches each
    page, and extracts recruitment notifications using keyword matching.
    """

    SCRAPER_NAME = "education"
    BASE_URL = ""  # Multi-source scraper; no single base URL.
    EXAM_CATEGORY = "Teaching"
    MIN_REQUEST_INTERVAL = 3.0

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def scrape(self) -> list[dict[str, Any]]:
        notifications: list[dict[str, Any]] = []
        seen_hashes: set[str] = set()

        for source in SOURCES:
            try:
                source_results = self._scrape_source(source)
                for notif in source_results:
                    dedup = notif.get("dedup_hash", "")
                    if dedup and dedup not in seen_hashes:
                        seen_hashes.add(dedup)
                        notifications.append(notif)
            except Exception:
                self.logger.exception(
                    "Error scraping source %s (%s) — skipping",
                    source["name"],
                    source["base_url"],
                )
                continue

        self.logger.info(
            "Education scraper extracted %d notifications from %d sources",
            len(notifications),
            len(SOURCES),
        )
        return notifications

    # ------------------------------------------------------------------
    # Per-source scraping
    # ------------------------------------------------------------------

    def _scrape_source(self, source: dict[str, Any]) -> list[dict[str, Any]]:
        """Scrape all configured paths for a single education source."""
        results: list[dict[str, Any]] = []
        base_url: str = source["base_url"]

        for path in source["paths"]:
            url = self.resolve_url(base_url, path)
            try:
                response = self.fetch(url)
                if response is None:
                    continue
                parsed = self._parse_source_page(
                    response,
                    recruiting_body=source["recruiting_body"],
                    base_url=base_url,
                )
                results.extend(parsed)
            except Exception:
                self.logger.exception(
                    "Error parsing %s for source %s — skipping path",
                    url,
                    source["name"],
                )
                continue

        return results

    # ------------------------------------------------------------------
    # Page parsing
    # ------------------------------------------------------------------

    def parse_page(self, response: requests.Response) -> list[dict[str, Any]]:
        """
        Generic parse_page implementation (required by BaseScraper).
        Uses a synthetic source with defaults.
        """
        synthetic_source: dict[str, Any] = {
            "name": "unknown",
            "base_url": response.url.rstrip("/"),
            "paths": ["/"],
            "recruiting_body": "Education Recruitment",
        }
        return self._parse_source_page(
            response,
            recruiting_body=synthetic_source["recruiting_body"],
            base_url=synthetic_source["base_url"],
        )

    def _parse_source_page(
        self,
        response: requests.Response,
        recruiting_body: str,
        base_url: str,
    ) -> list[dict[str, Any]]:
        """Parse a single page from a specific education source."""
        results: list[dict[str, Any]] = []
        soup = BeautifulSoup(response.text, "html.parser")

        seen_hrefs: set[str] = set()

        for selector in _CSS_SELECTORS:
            try:
                for element in soup.select(selector):
                    parsed = self._extract_from_element(
                        element, base_url, recruiting_body, seen_hrefs
                    )
                    if parsed is not None:
                        results.append(parsed)
            except Exception:
                continue

        return results

    # ------------------------------------------------------------------
    # Element-level extraction
    # ------------------------------------------------------------------

    def _extract_from_element(
        self,
        element: Tag,
        base_url: str,
        recruiting_body: str,
        seen: set[str],
    ) -> Optional[dict[str, Any]]:
        """
        Try to extract a recruitment notification from a single HTML element
        (table row, list item, or anchor tag).
        """
        link_tag: Optional[Tag] = (
            element if element.name == "a" else element.find("a", href=True)
        )
        if link_tag is None or not link_tag.get("href"):
            return None

        href: str = link_tag["href"].strip()
        if not href or href == "#" or href in seen:
            return None

        text: str = link_tag.get_text(strip=True)
        if not text or len(text) < 8:
            return None

        # Must contain a recruitment signal word.
        if not self._is_recruitment_text(text):
            return None

        # Must match a known education keyword.
        post_name = self._match_post(text)
        if post_name is None:
            return None

        seen.add(href)
        source_url = self.resolve_url(base_url, href)
        pdf_url = source_url if href.lower().endswith(".pdf") else None

        # Try to extract a date from the surrounding element text.
        row_text = element.get_text(" ", strip=True) if element.name != "a" else ""
        notification_date = self._extract_date(row_text)

        # Try to extract vacancy count from surrounding text.
        total_vacancies = self._extract_vacancy_count(row_text or text)

        return self.build_notification_dict(
            recruiting_body=recruiting_body,
            post_name=post_name,
            source_url=source_url,
            pdf_url=pdf_url,
            notification_date=notification_date,
            total_vacancies=total_vacancies,
            official_website=base_url,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_recruitment_text(text: str) -> bool:
        """Return True if the text contains recruitment-related signals."""
        text_lower = text.lower()
        return any(signal in text_lower for signal in _RECRUITMENT_SIGNALS)

    @staticmethod
    def _match_post(text: str) -> Optional[str]:
        """
        Return a canonical post/role name if *text* matches a known
        education recruitment keyword.
        """
        text_lower = text.lower()

        # Check longer keywords first for more specific matches
        # (e.g. "vice principal" before "principal").
        for keyword in sorted(_EDUCATION_KEYWORDS, key=len, reverse=True):
            if keyword in text_lower:
                return _EDUCATION_KEYWORDS[keyword]

        # If recruitment signal present but no specific role keyword matched,
        # return the trimmed text itself as the post name (capped length).
        return text[:120] if len(text) <= 200 else text[:120] + "..."

    @staticmethod
    def _extract_date(text: str) -> Any:
        """Best-effort date extraction from surrounding row text."""
        if not text:
            return None
        match = re.search(r"(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{4})", text)
        if match:
            return BaseScraper.parse_date(match.group(1))
        return None

    @staticmethod
    def _extract_vacancy_count(text: str) -> Optional[int]:
        """Try to pull a vacancy count from text like '150 posts' or '23 vacancies'."""
        if not text:
            return None
        match = re.search(
            r"(\d+)\s*(?:posts?|vacancies|vacancy|positions?|openings?)",
            text,
            re.IGNORECASE,
        )
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return None
        return None
