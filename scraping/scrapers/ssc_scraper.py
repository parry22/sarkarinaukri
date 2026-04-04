from __future__ import annotations
"""
Scraper for Staff Selection Commission (SSC) notifications.

Targets: ssc.gov.in — the official SSC notice/advertisement page.
Covers: CGL, CHSL, MTS, GD Constable, JE, CPO, Stenographer.
"""

import re
from typing import Any, Optional

import requests
from bs4 import BeautifulSoup, Tag

from scraping.scrapers.base_scraper import BaseScraper

# Keywords that indicate a recruitment notification (case-insensitive).
_EXAM_KEYWORDS: dict[str, str] = {
    "cgl": "Combined Graduate Level (CGL)",
    "chsl": "Combined Higher Secondary Level (CHSL)",
    "mts": "Multi Tasking Staff (MTS)",
    "gd constable": "GD Constable",
    "gd": "GD Constable",
    "je": "Junior Engineer (JE)",
    "junior engineer": "Junior Engineer (JE)",
    "cpo": "Central Police Organisation (CPO)",
    "sub-inspector": "Central Police Organisation (CPO)",
    "steno": "Stenographer",
    "stenographer": "Stenographer",
}


class SSCScraper(BaseScraper):
    SCRAPER_NAME = "ssc"
    BASE_URL = "https://ssc.gov.in"
    EXAM_CATEGORY = "SSC"
    MIN_REQUEST_INTERVAL = 3.0  # SSC site can be slow; be polite

    # Pages to check for new notices.
    NOTICE_PATHS = [
        "/notice/notice",
        "/notice/advertisement",
    ]

    def scrape(self) -> list[dict[str, Any]]:
        notifications: list[dict[str, Any]] = []

        for path in self.NOTICE_PATHS:
            url = self.resolve_url(self.BASE_URL, path)
            response = self.fetch(url)
            if response is None:
                continue
            notifications.extend(self.parse_page(response))

        self.logger.info("SSC scraper extracted %d notifications", len(notifications))
        return notifications

    def parse_page(self, response: requests.Response) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        soup = BeautifulSoup(response.text, "html.parser")

        # SSC notice pages typically contain tables or divs with links to PDFs.
        rows = soup.select("table tr, .view-content .views-row, .item-list li")
        if not rows:
            # Fallback: grab all links in the main content area.
            rows = soup.select("#block-system-main a, .region-content a")

        for row in rows:
            parsed = self._extract_from_element(row, response.url)
            if parsed is not None:
                results.append(parsed)

        return results

    def _extract_from_element(
        self, element: Tag, page_url: str
    ) -> Optional[dict[str, Any]]:
        """
        Try to extract a recruitment notification from a single HTML element
        (table row, list item, or anchor tag).
        """
        # Find the first anchor that points to a PDF or notice page.
        link_tag = element if element.name == "a" else element.find("a", href=True)
        if link_tag is None or not link_tag.get("href"):
            return None

        href: str = link_tag["href"].strip()
        text: str = link_tag.get_text(strip=True)

        if not text:
            return None

        # Only interested in recruitment-related notices.
        exam_name = self._match_exam(text)
        if exam_name is None:
            return None

        source_url = self.resolve_url(self.BASE_URL, href)
        pdf_url = source_url if href.lower().endswith(".pdf") else None

        # Try to pull a date from the surrounding row text.
        row_text = element.get_text(" ", strip=True) if element.name != "a" else ""
        notification_date = self._extract_date(row_text)

        return self.build_notification_dict(
            recruiting_body="Staff Selection Commission (SSC)",
            post_name=exam_name,
            source_url=source_url,
            pdf_url=pdf_url,
            notification_date=notification_date,
            official_website=self.BASE_URL,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _match_exam(text: str) -> Optional[str]:
        """Return the canonical exam name if *text* matches a known SSC exam."""
        text_lower = text.lower()

        # Quick filter: must look like a recruitment / notification / vacancy.
        recruitment_signals = (
            "recruitment",
            "notification",
            "examination",
            "vacancy",
            "advt",
            "advertisement",
        )
        if not any(sig in text_lower for sig in recruitment_signals):
            return None

        for keyword, canonical in _EXAM_KEYWORDS.items():
            if keyword in text_lower:
                return canonical

        return None

    def _extract_date(self, text: str) -> Any:
        """Best-effort date extraction from surrounding row text."""
        # Look for dd/mm/yyyy or dd-mm-yyyy patterns.
        match = re.search(r"(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{4})", text)
        if match:
            return self.parse_date(match.group(1))
        return None
