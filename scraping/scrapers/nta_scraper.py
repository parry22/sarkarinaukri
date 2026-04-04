from __future__ import annotations
"""
Scraper for National Testing Agency (NTA) notifications.

Targets: nta.ac.in and exams.nta.ac.in
Covers: JEE Main/Advanced, NEET UG, CUET UG/PG, CTET, UGC NET.
"""

import re
from typing import Any, Optional

import requests
from bs4 import BeautifulSoup, Tag

from scraping.scrapers.base_scraper import BaseScraper

_EXAM_KEYWORDS: dict[str, str] = {
    "jee main": "Joint Entrance Examination Main (JEE Main)",
    "jee advanced": "Joint Entrance Examination Advanced (JEE Advanced)",
    "jee (main)": "Joint Entrance Examination Main (JEE Main)",
    "jee (advanced)": "Joint Entrance Examination Advanced (JEE Advanced)",
    "neet": "National Eligibility cum Entrance Test (NEET UG)",
    "neet ug": "National Eligibility cum Entrance Test (NEET UG)",
    "cuet ug": "Common University Entrance Test UG (CUET UG)",
    "cuet pg": "Common University Entrance Test PG (CUET PG)",
    "cuet": "Common University Entrance Test (CUET)",
    "ctet": "Central Teacher Eligibility Test (CTET)",
    "ugc net": "UGC National Eligibility Test (UGC NET)",
    "ugc-net": "UGC National Eligibility Test (UGC NET)",
    "csir net": "CSIR UGC NET",
}

# Map exam keywords to an appropriate exam_category override.
_CATEGORY_OVERRIDES: dict[str, str] = {
    "ctet": "Teaching",
    "ugc net": "Teaching",
    "ugc-net": "Teaching",
    "csir net": "Teaching",
}


class NTAScraper(BaseScraper):
    SCRAPER_NAME = "nta"
    BASE_URL = "https://nta.ac.in"
    EXAM_CATEGORY = "Teaching"  # default; overridden per-exam where needed
    MIN_REQUEST_INTERVAL = 2.5

    TARGETS: list[dict[str, str]] = [
        {"base": "https://nta.ac.in", "path": "/"},
        {"base": "https://exams.nta.ac.in", "path": "/"},
        {"base": "https://nta.ac.in", "path": "/notice"},
    ]

    def scrape(self) -> list[dict[str, Any]]:
        notifications: list[dict[str, Any]] = []

        for target in self.TARGETS:
            url = self.resolve_url(target["base"], target["path"])
            response = self.fetch(url)
            if response is None:
                continue
            notifications.extend(
                self._parse_with_base(response, target["base"])
            )

        self.logger.info("NTA scraper extracted %d notifications", len(notifications))
        return notifications

    def parse_page(self, response: requests.Response) -> list[dict[str, Any]]:
        return self._parse_with_base(response, self.BASE_URL)

    def _parse_with_base(
        self, response: requests.Response, base_url: str
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        soup = BeautifulSoup(response.text, "html.parser")

        selectors = [
            "table tr",
            ".notification-list a",
            ".latest-notification a",
            ".news-ticker a",
            ".marquee a",
            "#notice a",
            ".content-area a",
            "ul.list-group a",
        ]

        seen_hrefs: set[str] = set()
        for selector in selectors:
            for el in soup.select(selector):
                parsed = self._extract_notification(el, base_url, seen_hrefs)
                if parsed is not None:
                    results.append(parsed)

        return results

    def _extract_notification(
        self,
        element: Tag,
        base_url: str,
        seen: set[str],
    ) -> Optional[dict[str, Any]]:
        link_tag = element if element.name == "a" else element.find("a", href=True)
        if link_tag is None or not link_tag.get("href"):
            return None

        href: str = link_tag["href"].strip()
        if href in seen:
            return None

        text: str = link_tag.get_text(strip=True)
        if not text:
            return None

        exam_name = self._match_exam(text)
        if exam_name is None:
            return None

        seen.add(href)
        source_url = self.resolve_url(base_url, href)
        pdf_url = source_url if href.lower().endswith(".pdf") else None

        # Determine the best exam_category for this specific exam.
        exam_category = self._resolve_category(text)

        row_text = element.get_text(" ", strip=True) if element.name != "a" else ""
        notification_date = self._extract_date(row_text)

        return self.build_notification_dict(
            recruiting_body="National Testing Agency (NTA)",
            post_name=exam_name,
            source_url=source_url,
            pdf_url=pdf_url,
            notification_date=notification_date,
            official_website=base_url,
            exam_category=exam_category,  # override the default
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _match_exam(text: str) -> Optional[str]:
        text_lower = text.lower()

        recruitment_signals = (
            "notification",
            "bulletin",
            "registration",
            "application",
            "advt",
            "admit card",
            "examination",
        )
        if not any(sig in text_lower for sig in recruitment_signals):
            return None

        for keyword, canonical in _EXAM_KEYWORDS.items():
            if keyword in text_lower:
                return canonical

        return None

    @staticmethod
    def _resolve_category(text: str) -> str:
        """Return the most specific exam_category for the matched text."""
        text_lower = text.lower()
        for keyword, category in _CATEGORY_OVERRIDES.items():
            if keyword in text_lower:
                return category
        # JEE / NEET / CUET don't map to a single government-job category;
        # we default to Teaching which is closest for NTA's mandate.
        return "Teaching"

    def _extract_date(self, text: str) -> Any:
        match = re.search(r"(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{4})", text)
        if match:
            return self.parse_date(match.group(1))
        return None
