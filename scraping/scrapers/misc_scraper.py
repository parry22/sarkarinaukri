from __future__ import annotations
"""
Scraper for miscellaneous important government recruitment bodies in India.

Covers a diverse set of organisations that don't fit neatly into other
category-specific scrapers, including:
- Employees' Provident Fund Organisation (EPFO)
- Employment News (Rozgar Samachar)
- UPRVUNL
- High Courts (Allahabad, Delhi, Bombay, Madras, Calcutta, Patna)
- Supreme Court of India
- Agricultural Scientists Recruitment Board (ASRB/ICAR)
- Central Teacher Eligibility Test (CTET)

Each source carries its own exam_category, overriding the class default.
"""

import re
from typing import Any, Optional

import requests
from bs4 import BeautifulSoup, Tag

from scraping.scrapers.base_scraper import BaseScraper

# ---------------------------------------------------------------------------
# Miscellaneous government sources
# ---------------------------------------------------------------------------

SOURCES: list[dict[str, Any]] = [
    {"name": "EPFO", "base_url": "https://www.epfindia.gov.in", "paths": ["/", "/site_en/Circulars.php"], "recruiting_body": "Employees' Provident Fund Organisation (EPFO)", "exam_category": "Banking"},
    {"name": "EmploymentNews", "base_url": "https://www.employmentnews.gov.in", "paths": ["/", "/NewEmp/LatestVacancies.aspx"], "recruiting_body": "Employment News (Rozgar Samachar)", "exam_category": "SSC"},
    {"name": "UPRVUNL", "base_url": "https://www.uprvunl.org", "paths": ["/"], "recruiting_body": "UPRVUNL", "exam_category": "PSU"},
    {"name": "HighCourt_Allahabad", "base_url": "https://www.allahabadhighcourt.in", "paths": ["/", "/recruitment.html"], "recruiting_body": "Allahabad High Court", "exam_category": "Judiciary"},
    {"name": "HighCourt_Delhi", "base_url": "https://delhihighcourt.nic.in", "paths": ["/", "/recruitment.asp"], "recruiting_body": "Delhi High Court", "exam_category": "Judiciary"},
    {"name": "HighCourt_Bombay", "base_url": "https://bombayhighcourt.nic.in", "paths": ["/", "/recruitment.php"], "recruiting_body": "Bombay High Court", "exam_category": "Judiciary"},
    {"name": "HighCourt_Madras", "base_url": "https://www.mhc.tn.gov.in", "paths": ["/"], "recruiting_body": "Madras High Court", "exam_category": "Judiciary"},
    {"name": "HighCourt_Calcutta", "base_url": "https://calcuttahighcourt.gov.in", "paths": ["/", "/recruitment"], "recruiting_body": "Calcutta High Court", "exam_category": "Judiciary"},
    {"name": "HighCourt_Patna", "base_url": "https://patnahighcourt.gov.in", "paths": ["/", "/recruitment.html"], "recruiting_body": "Patna High Court", "exam_category": "Judiciary"},
    {"name": "SupremeCourt", "base_url": "https://main.sci.gov.in", "paths": ["/", "/recruitment"], "recruiting_body": "Supreme Court of India", "exam_category": "Judiciary"},
    {"name": "ICAR_ASRB", "base_url": "https://asrb.org.in", "paths": ["/", "/advertisement"], "recruiting_body": "Agricultural Scientists Recruitment Board (ASRB/ICAR)", "exam_category": "PSU"},
    {"name": "CTET", "base_url": "https://ctet.nic.in", "paths": ["/"], "recruiting_body": "Central Teacher Eligibility Test (CTET)", "exam_category": "Teaching"},
]

# ---------------------------------------------------------------------------
# Broad keywords for miscellaneous government recruitment
# ---------------------------------------------------------------------------

_MISC_KEYWORDS: dict[str, str] = {
    "recruitment": "Recruitment",
    "vacancy": "Vacancy",
    "notification": "Notification",
    "advt": "Advertisement",
    "advertisement": "Advertisement",
    "bharti": "Bharti (Recruitment)",
    "examination": "Examination",
    "walk-in": "Walk-in Interview",
    "interview": "Interview",
    "contractual": "Contractual Appointment",
    "deputation": "Deputation",
    "transfer": "Transfer",
    "appointment": "Appointment",
    "post": "Post",
    "result": "Result",
}

# Broad CSS selectors to handle varied government site structures.
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
    ".career a",
    ".latest a",
    ".news a",
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
    "examination",
    "online form",
    "registration",
)


class MiscGovtScraper(BaseScraper):
    """
    Multi-source scraper for miscellaneous Indian government recruitment portals.

    Iterates over all configured government sites, fetches each page, and
    extracts recruitment notifications using keyword matching.  Each source
    can specify its own exam_category, which overrides the class default.
    """

    SCRAPER_NAME = "misc_govt"
    BASE_URL = ""  # Multi-source scraper; no single base URL.
    EXAM_CATEGORY = "SSC"  # Default fallback; overridden per source.
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
            "Misc govt scraper extracted %d notifications from %d sources",
            len(notifications),
            len(SOURCES),
        )
        return notifications

    # ------------------------------------------------------------------
    # Per-source scraping
    # ------------------------------------------------------------------

    def _scrape_source(self, source: dict[str, Any]) -> list[dict[str, Any]]:
        """Scrape all configured paths for a single miscellaneous source."""
        results: list[dict[str, Any]] = []
        base_url: str = source["base_url"]
        exam_category: str = source.get("exam_category", self.EXAM_CATEGORY)

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
                    exam_category=exam_category,
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
        return self._parse_source_page(
            response,
            recruiting_body="Government Recruitment",
            base_url=response.url.rstrip("/"),
            exam_category=self.EXAM_CATEGORY,
        )

    def _parse_source_page(
        self,
        response: requests.Response,
        recruiting_body: str,
        base_url: str,
        exam_category: str,
    ) -> list[dict[str, Any]]:
        """Parse a single page from a specific government source."""
        results: list[dict[str, Any]] = []
        soup = BeautifulSoup(response.text, "html.parser")

        seen_hrefs: set[str] = set()

        for selector in _CSS_SELECTORS:
            try:
                for element in soup.select(selector):
                    parsed = self._extract_from_element(
                        element, base_url, recruiting_body, exam_category, seen_hrefs
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
        exam_category: str,
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

        seen.add(href)
        source_url = self.resolve_url(base_url, href)
        pdf_url = source_url if href.lower().endswith(".pdf") else None

        # Use the full link text (capped) as post name for misc sources,
        # since the keyword set is intentionally broad.
        post_name = text[:120] if len(text) <= 200 else text[:120] + "..."

        # Try to extract a date from the surrounding element text.
        row_text = element.get_text(" ", strip=True) if element.name != "a" else ""
        notification_date = self._extract_date(row_text)

        # Try to extract vacancy count from surrounding text.
        total_vacancies = self._extract_vacancy_count(row_text or text)

        # Build the notification dict, overriding exam_category per source.
        notif = self.build_notification_dict(
            recruiting_body=recruiting_body,
            post_name=post_name,
            source_url=source_url,
            pdf_url=pdf_url,
            notification_date=notification_date,
            total_vacancies=total_vacancies,
            official_website=base_url,
        )
        # Override the class-level exam_category with the source-specific one.
        notif["exam_category"] = exam_category
        return notif

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_recruitment_text(text: str) -> bool:
        """Return True if the text contains recruitment-related signals."""
        text_lower = text.lower()
        return any(signal in text_lower for signal in _RECRUITMENT_SIGNALS)

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
