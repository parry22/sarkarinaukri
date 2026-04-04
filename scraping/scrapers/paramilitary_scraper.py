from __future__ import annotations
"""
Combined scraper for all Central Armed Police Forces (CAPF) / paramilitary
recruitment in India.

Covers: CRPF, BSF, CISF, ITBP, SSB, Assam Rifles, RPF.
"""

import re
from typing import Any, Optional

import requests
from bs4 import BeautifulSoup, Tag

from scraping.scrapers.base_scraper import BaseScraper

# Keyword -> canonical post name mapping for paramilitary roles.
_PARAMILITARY_KEYWORDS: dict[str, str] = {
    "constable gd": "Constable (General Duty)",
    "constable (gd)": "Constable (General Duty)",
    "constable tradesman": "Constable (Tradesman)",
    "constable technical": "Constable (Technical)",
    "constable": "Constable",
    "head constable": "Head Constable",
    "hc": "Head Constable",
    "sub inspector": "Sub Inspector (SI)",
    "si": "Sub Inspector (SI)",
    "asi": "Assistant Sub Inspector (ASI)",
    "inspector": "Inspector",
    "commandant": "Commandant",
    "rifleman": "Rifleman (General Duty)",
    "havildar": "Havildar",
    "driver": "Constable (Driver)",
    "fire": "Constable/Fire",
    "telecom": "Constable (Telecom)",
    "motor mechanic": "Constable (Motor Mechanic)",
    "ministerial": "Head Constable (Ministerial)",
    "steno": "Stenographer",
    "veterinary": "Veterinary Staff",
    "recruitment": "General Recruitment",
}

# Each source represents one paramilitary force website.
_SOURCES: list[dict[str, Any]] = [
    {
        "name": "CRPF",
        "base_url": "https://crpf.gov.in",
        "paths": ["/", "/recruitment.htm"],
        "recruiting_body": "Central Reserve Police Force (CRPF)",
    },
    {
        "name": "BSF",
        "base_url": "https://bsf.gov.in",
        "paths": ["/", "/recruitment.html"],
        "recruiting_body": "Border Security Force (BSF)",
    },
    {
        "name": "CISF",
        "base_url": "https://cisf.gov.in",
        "paths": ["/", "/recruitment"],
        "recruiting_body": "Central Industrial Security Force (CISF)",
    },
    {
        "name": "ITBP",
        "base_url": "https://itbp.gov.in",
        "paths": ["/", "/recruitment.html"],
        "recruiting_body": "Indo-Tibetan Border Police (ITBP)",
    },
    {
        "name": "SSB",
        "base_url": "https://ssbrectt.gov.in",
        "paths": ["/"],
        "recruiting_body": "Sashastra Seema Bal (SSB)",
    },
    {
        "name": "Assam Rifles",
        "base_url": "https://assamrifles.gov.in",
        "paths": ["/", "/recruitment"],
        "recruiting_body": "Assam Rifles",
    },
    {
        "name": "RPF",
        "base_url": "https://rpf.indianrailways.gov.in",
        "paths": ["/"],
        "recruiting_body": "Railway Protection Force (RPF)",
    },
]

# CSS selectors covering typical NIC / govt site layouts.
_CSS_SELECTORS: list[str] = [
    "table tr",
    "marquee a",
    ".scrolling a",
    "#ContentPlaceHolder1 a",
    ".content-area a",
    "ul li a",
    ".notification a",
    "#notice a",
    "main a",
    ".container a",
    "article a",
]


class ParamilitaryScraper(BaseScraper):
    SCRAPER_NAME = "paramilitary"
    BASE_URL = ""  # multi-source; no single base URL
    EXAM_CATEGORY = "Police"
    MIN_REQUEST_INTERVAL = 3.0

    def __init__(
        self,
        sources: Optional[list[dict[str, Any]]] = None,
        rate_limit: Optional[float] = None,
    ) -> None:
        super().__init__(rate_limit=rate_limit)
        self._sources = sources if sources is not None else list(_SOURCES)
        # Track the current source context for use in parse_page.
        self._current_source: dict[str, Any] = {}

    def scrape(self) -> list[dict[str, Any]]:
        notifications: list[dict[str, Any]] = []

        for source in self._sources:
            name = source["name"]
            base_url = source["base_url"]
            paths = source["paths"]

            self.logger.info("Scraping %s (%s)", name, base_url)
            self._current_source = source

            for path in paths:
                url = self.resolve_url(base_url, path)
                response = self.fetch(url)
                if response is None:
                    continue
                notifications.extend(self.parse_page(response))

        self.logger.info(
            "Paramilitary scraper extracted %d notifications", len(notifications)
        )
        return notifications

    def parse_page(self, response: requests.Response) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        soup = BeautifulSoup(response.text, "html.parser")

        seen_hrefs: set[str] = set()
        for selector in _CSS_SELECTORS:
            for element in soup.select(selector):
                parsed = self._extract_notification(
                    element, response.url, seen_hrefs
                )
                if parsed is not None:
                    results.append(parsed)

        return results

    def _extract_notification(
        self,
        element: Tag,
        page_url: str,
        seen: set[str],
    ) -> Optional[dict[str, Any]]:
        """
        Try to extract a recruitment notification from a single HTML element.
        """
        link_tag = element if element.name == "a" else element.find("a", href=True)
        if link_tag is None or not link_tag.get("href"):
            return None

        href: str = link_tag["href"].strip()
        if href in seen:
            return None

        text: str = link_tag.get_text(strip=True)
        if not text:
            return None

        post_name = self._match_post(text)
        if post_name is None:
            return None

        seen.add(href)

        base_url = self._current_source.get("base_url", "")
        source_url = self.resolve_url(base_url, href)
        pdf_url = source_url if href.lower().endswith(".pdf") else None

        row_text = element.get_text(" ", strip=True) if element.name != "a" else ""
        notification_date = self._extract_date(row_text)

        recruiting_body = self._current_source.get("recruiting_body", "")
        force_name = self._current_source.get("name", "")

        # Prefix the post name with the force abbreviation for clarity.
        full_post_name = f"{force_name} - {post_name}"

        return self.build_notification_dict(
            recruiting_body=recruiting_body,
            post_name=full_post_name,
            source_url=source_url,
            pdf_url=pdf_url,
            notification_date=notification_date,
            official_website=base_url,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _match_post(text: str) -> Optional[str]:
        """
        Return the canonical post name if *text* matches a known paramilitary
        recruitment keyword.
        """
        text_lower = text.lower()

        recruitment_signals = (
            "recruitment",
            "notification",
            "vacancy",
            "advt",
            "advertisement",
            "rally",
            "bharti",
            "application",
            "online form",
        )
        if not any(sig in text_lower for sig in recruitment_signals):
            return None

        # Iterate from most specific to least specific: _PARAMILITARY_KEYWORDS
        # is ordered with specific multi-word keys first, so a match on
        # "constable gd" will take priority over bare "constable".
        for keyword, canonical in _PARAMILITARY_KEYWORDS.items():
            if keyword in text_lower:
                return canonical

        return None

    def _extract_date(self, text: str) -> Any:
        """Best-effort date extraction from surrounding row text."""
        match = re.search(r"(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{4})", text)
        if match:
            return self.parse_date(match.group(1))
        return None
