from __future__ import annotations
"""
Scraper for Railway Recruitment Board (RRB) notifications.

Primary target: rrbcdg.gov.in (RRB Chandigarh / Delhi).
Designed for extension to other zonal RRB websites.
Covers: NTPC, Group D, ALP, JE, Paramedical.
"""

import re
from typing import Any, Optional

import requests
from bs4 import BeautifulSoup, Tag

from scraping.scrapers.base_scraper import BaseScraper

_EXAM_KEYWORDS: dict[str, str] = {
    "ntpc": "Non-Technical Popular Categories (NTPC)",
    "non technical": "Non-Technical Popular Categories (NTPC)",
    "group d": "Group D (Level 1)",
    "group-d": "Group D (Level 1)",
    "level 1": "Group D (Level 1)",
    "alp": "Assistant Loco Pilot (ALP)",
    "assistant loco pilot": "Assistant Loco Pilot (ALP)",
    "technician": "Assistant Loco Pilot (ALP)",
    "je": "Junior Engineer (JE)",
    "junior engineer": "Junior Engineer (JE)",
    "paramedical": "Paramedical Categories",
    "staff nurse": "Paramedical Categories",
    "health & malaria inspector": "Paramedical Categories",
}

# All 21 zonal RRB websites.
_ZONAL_URLS: dict[str, str] = {
    "rrbcdg": "https://rrbcdg.gov.in",
    "rrbmumbai": "https://rrbmumbai.gov.in",
    "rrbchennai": "https://rrbchennai.gov.in",
    "rrbkolkata": "https://rrbkolkata.gov.in",
    "rrbahmedabad": "https://rrbahmedabad.gov.in",
    "rrbbhopal": "https://rrbbhopal.gov.in",
    "rrbbilaspur": "https://rrbbilaspur.gov.in",
    "rrbchangarh": "https://rrbcdg.gov.in",  # alias — same as CDG
    "rrbguwahati": "https://rrbguwahati.gov.in",
    "rrbjammu": "https://rrbjammu.nic.in",
    "rrbmalda": "https://rrbmalda.gov.in",
    "rrbmuzaffarpur": "https://rrbmuzaffarpur.gov.in",
    "rrbpatna": "https://rrbpatna.gov.in",
    "rrbranchi": "https://rrbranchi.gov.in",
    "rrbsecunderabad": "https://rrbsecunderabad.gov.in",
    "rrbsiliguri": "https://rrbsiliguri.gov.in",
    "rrbtrivandrum": "https://rrbtrivandrum.gov.in",
    "rrbvaranasi": "https://rrbvaranasi.gov.in",
    "rrballahabad": "https://rrbald.gov.in",
    "rrbajmer": "https://rrbajmer.gov.in",
    "rrbbangalore": "https://rrbbnc.gov.in",
    "rrbnsr": "https://rrbnsr.gov.in",  # Gorakhpur zone (NSR = North-Eastern/Sambalpur)
}


class RRBScraper(BaseScraper):
    SCRAPER_NAME = "rrb"
    BASE_URL = "https://rrbcdg.gov.in"
    EXAM_CATEGORY = "Railway"
    MIN_REQUEST_INTERVAL = 3.0

    def __init__(
        self,
        zones: Optional[list[str]] = None,
        rate_limit: Optional[float] = None,
    ) -> None:
        super().__init__(rate_limit=rate_limit)
        # Default to ALL zones for comprehensive coverage.
        if zones:
            self._zone_urls = {z: _ZONAL_URLS[z] for z in zones if z in _ZONAL_URLS}
        else:
            self._zone_urls = dict(_ZONAL_URLS)

    def scrape(self) -> list[dict[str, Any]]:
        notifications: list[dict[str, Any]] = []

        for zone_key, base_url in self._zone_urls.items():
            self.logger.info("Scraping RRB zone: %s (%s)", zone_key, base_url)
            response = self.fetch(base_url)
            if response is None:
                continue
            notifications.extend(self.parse_page(response))

            # Also check a common /cen (centralised employment notice) path.
            cen_url = self.resolve_url(base_url, "/cen")
            cen_resp = self.fetch(cen_url)
            if cen_resp is not None:
                notifications.extend(self.parse_page(cen_resp))

        self.logger.info("RRB scraper extracted %d notifications", len(notifications))
        return notifications

    def parse_page(self, response: requests.Response) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        soup = BeautifulSoup(response.text, "html.parser")

        selectors = [
            "table tr",
            ".marquee a",
            ".scrolling a",
            "#ContentPlaceHolder1_gvNotice tr",
            ".content-area a",
            "#notice a",
        ]

        seen_hrefs: set[str] = set()
        for selector in selectors:
            for el in soup.select(selector):
                parsed = self._extract_notification(el, response.url, seen_hrefs)
                if parsed is not None:
                    results.append(parsed)

        return results

    def _extract_notification(
        self,
        element: Tag,
        page_url: str,
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
        # Determine which zone's base URL to resolve against.
        base = self._base_for_page(page_url)
        source_url = self.resolve_url(base, href)
        pdf_url = source_url if href.lower().endswith(".pdf") else None

        row_text = element.get_text(" ", strip=True) if element.name != "a" else ""
        notification_date = self._extract_date(row_text)

        # RRB CEN (Centralised Employment Notice) number if present.
        cen_number = self._extract_cen_number(text)
        extra: dict[str, Any] = {}
        if cen_number:
            extra["cen_number"] = cen_number

        return self.build_notification_dict(
            recruiting_body="Railway Recruitment Board (RRB)",
            post_name=exam_name,
            source_url=source_url,
            pdf_url=pdf_url,
            notification_date=notification_date,
            official_website=base,
            **extra,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _base_for_page(self, page_url: str) -> str:
        for base in self._zone_urls.values():
            if page_url.startswith(base):
                return base
        return self.BASE_URL

    @staticmethod
    def _match_exam(text: str) -> Optional[str]:
        text_lower = text.lower()

        recruitment_signals = (
            "recruitment",
            "notification",
            "cen",
            "vacancy",
            "advt",
            "employment notice",
        )
        if not any(sig in text_lower for sig in recruitment_signals):
            return None

        for keyword, canonical in _EXAM_KEYWORDS.items():
            if keyword in text_lower:
                return canonical

        return None

    @staticmethod
    def _extract_cen_number(text: str) -> Optional[str]:
        """Extract CEN number like 'CEN 01/2025' from text."""
        match = re.search(r"CEN[\s-]*(\d{1,2}/\d{4})", text, re.IGNORECASE)
        return match.group(0).strip() if match else None

    def _extract_date(self, text: str) -> Any:
        match = re.search(r"(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{4})", text)
        if match:
            return self.parse_date(match.group(1))
        return None
