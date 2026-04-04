from __future__ import annotations
"""
Combined scraper for Indian Armed Forces recruitment portals.

Targets:
- Indian Army       — joinindianarmy.nic.in
- Indian Navy       — joinindiannavy.gov.in
- Indian Air Force  — agnipathvayu.cdac.in, careerindianairforce.cdac.in
- Indian Coast Guard — joinindiancoastguard.cdac.in

Covers: Agniveer, NDA, CDS, AFCAT, SSC Tech, TGC, TES, Soldier entries,
        Navik, Yantrik, Assistant Commandant, and more.
"""

import re
from typing import Any, Optional

import requests
from bs4 import BeautifulSoup, Tag

from scraping.scrapers.base_scraper import BaseScraper

# Canonical exam name lookup keyed by keyword found in link text.
_DEFENCE_KEYWORDS: dict[str, str] = {
    "agniveer": "Agniveer",
    "agnipath": "Agniveer (Agnipath Scheme)",
    "nda": "National Defence Academy (NDA)",
    "cds": "Combined Defence Services (CDS)",
    "afcat": "Air Force Common Admission Test (AFCAT)",
    "ssc tech": "Short Service Commission (Technical)",
    "tgc": "Technical Graduate Course (TGC)",
    "tes": "Technical Entry Scheme (TES)",
    "soldier gd": "Soldier General Duty",
    "soldier technical": "Soldier Technical",
    "tradesman": "Tradesman",
    "clerk": "Soldier Clerk/SKT",
    "navik": "Navik",
    "yantrik": "Yantrik",
    "assistant commandant": "Assistant Commandant",
    "ssr": "Senior Secondary Recruit (SSR)",
    "mr": "Matric Recruit (MR)",
    "group x": "Group X (Technical)",
    "group y": "Group Y (Non-Technical)",
    "airmen": "Airmen",
    "sailor": "Sailor",
    "officer": "Officer Entry",
    "recruitment rally": "Recruitment Rally",
    "bharti rally": "Bharti Rally",
    "apprentice": "Apprentice",
    "dockyard": "Naval Dockyard Apprentice",
    "havildar": "Havildar",
    "short service": "Short Service Commission",
}

# Signals that indicate a link is recruitment-related.
_RECRUITMENT_SIGNALS: tuple[str, ...] = (
    "recruitment",
    "notification",
    "vacancy",
    "rally",
    "bharti",
    "online form",
    "apply",
    "entry scheme",
    "intake",
    "advertisement",
    "advt",
    "registration",
    "enrollment",
    "enrolment",
    "admit card",
    "result",
    "examination",
)

# Each source is a dict describing one recruitment portal.
_SOURCES: list[dict[str, Any]] = [
    {
        "name": "Indian Army",
        "base_url": "https://joinindianarmy.nic.in",
        "paths": ["/", "/officer-entry.htm", "/soldier-entry.htm"],
        "recruiting_body": "Indian Army",
    },
    {
        "name": "Indian Navy",
        "base_url": "https://joinindiannavy.gov.in",
        "paths": ["/", "/en/page/officer-entry", "/en/page/sailor-entry"],
        "recruiting_body": "Indian Navy",
    },
    {
        "name": "Indian Air Force (Agniveer Vayu)",
        "base_url": "https://agnipathvayu.cdac.in",
        "paths": ["/"],
        "recruiting_body": "Indian Air Force",
    },
    {
        "name": "Indian Air Force (Careers)",
        "base_url": "https://careerindianairforce.cdac.in",
        "paths": ["/"],
        "recruiting_body": "Indian Air Force",
    },
    {
        "name": "Indian Coast Guard",
        "base_url": "https://joinindiancoastguard.cdac.in",
        "paths": ["/"],
        "recruiting_body": "Indian Coast Guard",
    },
]

# Broad CSS selectors to handle varying military site structures.
_CSS_SELECTORS: list[str] = [
    "table tr",
    ".content a",
    "article a",
    ".entry a",
    ".notification a",
    ".card a",
    "ul li a",
    ".list-group-item a",
    "#content a",
    "main a",
    ".container a",
]


class DefenceScraper(BaseScraper):
    """
    Multi-source scraper for Indian Armed Forces recruitment portals.

    Iterates over all configured defence recruitment sites, fetches each
    page, and extracts recruitment notifications using keyword matching.
    """

    SCRAPER_NAME = "defence"
    BASE_URL = ""  # Multi-source; no single base URL.
    EXAM_CATEGORY = "Defence"
    MIN_REQUEST_INTERVAL = 3.0

    def scrape(self) -> list[dict[str, Any]]:
        notifications: list[dict[str, Any]] = []

        for source in _SOURCES:
            self.logger.info("Scraping defence source: %s", source["name"])
            for path in source["paths"]:
                url = self.resolve_url(source["base_url"], path)
                response = self.fetch(url)
                if response is None:
                    continue
                notifications.extend(
                    self._parse_source_page(response, source)
                )

        self.logger.info(
            "Defence scraper extracted %d notifications", len(notifications)
        )
        return notifications

    def parse_page(self, response: requests.Response) -> list[dict[str, Any]]:
        """
        Generic parse_page implementation (required by BaseScraper).
        Uses a synthetic source with defaults.
        """
        synthetic_source: dict[str, Any] = {
            "name": "unknown",
            "base_url": response.url.rstrip("/"),
            "paths": ["/"],
            "recruiting_body": "Indian Armed Forces",
        }
        return self._parse_source_page(response, synthetic_source)

    # ------------------------------------------------------------------
    # Internal parsing
    # ------------------------------------------------------------------

    def _parse_source_page(
        self,
        response: requests.Response,
        source: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Parse a single page from a specific defence source."""
        results: list[dict[str, Any]] = []
        soup = BeautifulSoup(response.text, "html.parser")
        base_url = source["base_url"]
        recruiting_body = source["recruiting_body"]

        seen_hrefs: set[str] = set()

        for selector in _CSS_SELECTORS:
            for element in soup.select(selector):
                parsed = self._extract_from_element(
                    element, base_url, recruiting_body, seen_hrefs
                )
                if parsed is not None:
                    results.append(parsed)

        return results

    def _extract_from_element(
        self,
        element: Tag,
        base_url: str,
        recruiting_body: str,
        seen: set[str],
    ) -> Optional[dict[str, Any]]:
        """
        Try to extract a recruitment notification from a single HTML element.
        Handles both anchor tags and container elements (table rows, list items).
        """
        # Get the anchor tag.
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

        # Must be recruitment-related text.
        if not self._is_recruitment_text(text):
            return None

        # Must match a known defence exam / entry keyword.
        exam_name = self._match_exam(text)
        if exam_name is None:
            return None

        seen.add(href)
        source_url = self.resolve_url(base_url, href)
        pdf_url = source_url if href.lower().endswith(".pdf") else None

        # Try to extract a date from the surrounding element text.
        row_text = element.get_text(" ", strip=True) if element.name != "a" else ""
        notification_date = self._extract_date(row_text)

        return self.build_notification_dict(
            recruiting_body=recruiting_body,
            post_name=exam_name,
            source_url=source_url,
            pdf_url=pdf_url,
            notification_date=notification_date,
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
    def _match_exam(text: str) -> Optional[str]:
        """
        Return the canonical exam / entry name if *text* matches a known
        defence recruitment keyword.
        """
        text_lower = text.lower()
        for keyword, canonical in _DEFENCE_KEYWORDS.items():
            if keyword in text_lower:
                return canonical
        return None

    def _extract_date(self, text: str) -> Any:
        """Best-effort date extraction from surrounding row text."""
        match = re.search(r"(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{4})", text)
        if match:
            return self.parse_date(match.group(1))
        return None
