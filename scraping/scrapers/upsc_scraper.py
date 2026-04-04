from __future__ import annotations
"""
Scraper for Union Public Service Commission (UPSC) notifications.

Targets: upsc.gov.in — examination notifications page.
Covers: CSE, CDS, NDA, CAPF, CMS, IES/ISS.
"""

import re
from typing import Any, Optional

import requests
from bs4 import BeautifulSoup, Tag

from scraping.scrapers.base_scraper import BaseScraper

_EXAM_KEYWORDS: dict[str, str] = {
    "civil services": "Civil Services Examination (CSE)",
    "cse": "Civil Services Examination (CSE)",
    "ias": "Civil Services Examination (CSE)",
    "cds": "Combined Defence Services (CDS)",
    "combined defence": "Combined Defence Services (CDS)",
    "nda": "National Defence Academy (NDA)",
    "national defence": "National Defence Academy (NDA)",
    "capf": "Central Armed Police Forces (CAPF)",
    "central armed police": "Central Armed Police Forces (CAPF)",
    "cms": "Combined Medical Services (CMS)",
    "combined medical": "Combined Medical Services (CMS)",
    "ies": "Indian Engineering Services (IES/ISS)",
    "iss": "Indian Engineering Services (IES/ISS)",
    "engineering services": "Indian Engineering Services (IES/ISS)",
    "indian statistical": "Indian Engineering Services (IES/ISS)",
}


class UPSCScraper(BaseScraper):
    SCRAPER_NAME = "upsc"
    BASE_URL = "https://upsc.gov.in"
    EXAM_CATEGORY = "UPSC"
    MIN_REQUEST_INTERVAL = 3.0

    NOTIFICATION_PATHS = [
        "/examinations/active-examinations",
        "/content/notifications",
    ]

    def scrape(self) -> list[dict[str, Any]]:
        notifications: list[dict[str, Any]] = []

        for path in self.NOTIFICATION_PATHS:
            url = self.resolve_url(self.BASE_URL, path)
            response = self.fetch(url)
            if response is None:
                continue
            notifications.extend(self.parse_page(response))

        self.logger.info("UPSC scraper extracted %d notifications", len(notifications))
        return notifications

    def parse_page(self, response: requests.Response) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        soup = BeautifulSoup(response.text, "html.parser")

        # UPSC site uses a table or view-rows for listing notifications.
        rows = soup.select(
            "table.views-table tbody tr, "
            ".view-content .views-row, "
            ".field-content a, "
            "#block-system-main table tr"
        )

        for row in rows:
            parsed = self._extract_notification(row, response.url)
            if parsed is not None:
                results.append(parsed)

        return results

    def _extract_notification(
        self, element: Tag, page_url: str
    ) -> Optional[dict[str, Any]]:
        link_tag = element if element.name == "a" else element.find("a", href=True)
        if link_tag is None or not link_tag.get("href"):
            return None

        href: str = link_tag["href"].strip()
        text: str = link_tag.get_text(strip=True)
        if not text:
            return None

        exam_name = self._match_exam(text)
        if exam_name is None:
            return None

        source_url = self.resolve_url(self.BASE_URL, href)
        pdf_url = source_url if href.lower().endswith(".pdf") else None

        row_text = element.get_text(" ", strip=True) if element.name != "a" else ""
        notification_date = self._extract_date(row_text)

        return self.build_notification_dict(
            recruiting_body="Union Public Service Commission (UPSC)",
            post_name=exam_name,
            source_url=source_url,
            pdf_url=pdf_url,
            notification_date=notification_date,
            official_website=self.BASE_URL,
        )

    @staticmethod
    def _match_exam(text: str) -> Optional[str]:
        text_lower = text.lower()

        recruitment_signals = (
            "notification",
            "examination",
            "recruitment",
            "vacancy",
            "advt",
        )
        if not any(sig in text_lower for sig in recruitment_signals):
            return None

        for keyword, canonical in _EXAM_KEYWORDS.items():
            if keyword in text_lower:
                return canonical

        return None

    def _extract_date(self, text: str) -> Any:
        match = re.search(r"(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{4})", text)
        if match:
            return self.parse_date(match.group(1))
        return None
