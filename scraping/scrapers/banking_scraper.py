from __future__ import annotations
"""
Combined scraper for major banking/financial recruitment bodies NOT covered
by the IBPS scraper.

Targets:
- SBI  (sbi.co.in)        — PO, Clerk, SO, Apprentice
- RBI  (rbi.org.in)       — Grade B, Assistant, Office Attendant
- LIC  (licindia.in)      — AAO, ADO, Assistant  (Insurance category)
- NABARD (nabard.org)      — Grade A, Grade B
- SEBI (sebi.gov.in)      — Officer Grade A, Grade B
"""

import re
from typing import Any, Optional

import requests
from bs4 import BeautifulSoup, Tag

from scraping.scrapers.base_scraper import BaseScraper

# Signals that a link/row is recruitment-related (case-insensitive).
_RECRUITMENT_SIGNALS = (
    "recruitment",
    "notification",
    "vacancy",
    "vacancies",
    "advt",
    "advertisement",
    "bharti",
    "online form",
    "apply online",
    "engagement",
    "appointment",
    "empanelment",
    "walk-in",
    "walk in",
)


class BankingScraper(BaseScraper):
    """
    Multi-source scraper for SBI, RBI, LIC, NABARD and SEBI career pages.
    """

    SCRAPER_NAME = "banking_extended"
    BASE_URL = ""  # Multi-source; each source has its own base URL.
    EXAM_CATEGORY = "Banking"  # Default; overridden per source.
    MIN_REQUEST_INTERVAL = 3.0

    # ------------------------------------------------------------------
    # Source definitions
    # ------------------------------------------------------------------

    SOURCES: list[dict[str, Any]] = [
        {
            "name": "SBI",
            "base_url": "https://sbi.co.in",
            "paths": [
                "/web/careers",
                "/web/careers/current-openings",
            ],
            "exam_category": "Banking",
            "recruiting_body": "State Bank of India (SBI)",
            "selectors": [
                "table tr",
                ".card a",
                ".accordion a",
                ".content-area a",
                "#main-content a",
                ".portlet-body a",
            ],
            "keywords": {
                "sbi po": "SBI Probationary Officer (PO)",
                "probationary officer": "SBI Probationary Officer (PO)",
                "sbi clerk": "SBI Clerk (Junior Associate)",
                "junior associate": "SBI Clerk (Junior Associate)",
                "clerk": "SBI Clerk (Junior Associate)",
                "sbi so": "SBI Specialist Officer (SO)",
                "specialist officer": "SBI Specialist Officer (SO)",
                "specialist cadre officer": "SBI Specialist Officer (SO)",
                "sbi apprentice": "SBI Apprentice",
                "apprentice": "SBI Apprentice",
                "sco": "SBI Specialist Cadre Officer (SCO)",
                "circle based officer": "SBI Circle Based Officer (CBO)",
                "cbo": "SBI Circle Based Officer (CBO)",
                "pharmacist": "SBI Pharmacist",
                "fire engineer": "SBI Fire Engineer",
            },
        },
        {
            "name": "RBI",
            "base_url": "https://rbi.org.in",
            "paths": [
                "/Scripts/Aborbi.aspx",
            ],
            "exam_category": "Banking",
            "recruiting_body": "Reserve Bank of India (RBI)",
            "selectors": [
                "table tr",
                "#divContent a",
                ".tablebg a",
                ".content-area a",
                "#ctl00_ContentPlaceHolder1_pnlMain a",
                ".zebra-table tr",
            ],
            "keywords": {
                "grade b": "RBI Grade B Officer",
                "grade-b": "RBI Grade B Officer",
                "rbi assistant": "RBI Assistant",
                "assistant": "RBI Assistant",
                "office attendant": "RBI Office Attendant",
                "attendant": "RBI Office Attendant",
                "grade a": "RBI Grade A Officer",
                "security guard": "RBI Security Guard",
                "pharmacist": "RBI Pharmacist",
                "manager": "RBI Manager",
                "legal officer": "RBI Legal Officer",
                "rajbhasha": "RBI Rajbhasha Officer",
            },
        },
        {
            "name": "LIC",
            "base_url": "https://licindia.in",
            "paths": [
                "/Bottom-Links/Recruitments",
            ],
            "exam_category": "Insurance",
            "recruiting_body": "Life Insurance Corporation of India (LIC)",
            "selectors": [
                "table tr",
                ".content-area a",
                "#mainContent a",
                ".entry-content a",
                "#content a",
                ".post-content a",
            ],
            "keywords": {
                "aao": "LIC Assistant Administrative Officer (AAO)",
                "assistant administrative officer": "LIC Assistant Administrative Officer (AAO)",
                "ado": "LIC Apprentice Development Officer (ADO)",
                "apprentice development officer": "LIC Apprentice Development Officer (ADO)",
                "lic assistant": "LIC Assistant",
                "assistant": "LIC Assistant",
                "lic hfl": "LIC HFL Assistant / Associate",
                "housing finance": "LIC HFL Assistant / Associate",
                "advisor": "LIC Insurance Advisor",
            },
        },
        {
            "name": "NABARD",
            "base_url": "https://www.nabard.org",
            "paths": [
                "/career",
                "/careers",
                "/recruitment",
            ],
            "exam_category": "Banking",
            "recruiting_body": "National Bank for Agriculture and Rural Development (NABARD)",
            "selectors": [
                "table tr",
                ".content-area a",
                "#main-content a",
                ".entry-content a",
                ".field-content a",
                ".views-row a",
            ],
            "keywords": {
                "grade a": "NABARD Grade A Officer",
                "grade-a": "NABARD Grade A Officer",
                "grade b": "NABARD Grade B Officer",
                "grade-b": "NABARD Grade B Officer",
                "assistant manager": "NABARD Assistant Manager (Grade A)",
                "manager grade": "NABARD Manager",
                "development assistant": "NABARD Development Assistant",
                "specialist officer": "NABARD Specialist Officer",
                "rajbhasha": "NABARD Rajbhasha Officer",
                "office attendant": "NABARD Office Attendant",
            },
        },
        {
            "name": "SEBI",
            "base_url": "https://www.sebi.gov.in",
            "paths": [
                "/sebiweb/home/HomeSectionLinks.jsp?link=CareerSection",
            ],
            "exam_category": "Banking",
            "recruiting_body": "Securities and Exchange Board of India (SEBI)",
            "selectors": [
                "table tr",
                ".content-area a",
                "#mainContent a",
                "#contentDiv a",
                ".table-bordered tr",
            ],
            "keywords": {
                "grade a": "SEBI Officer Grade A",
                "officer grade a": "SEBI Officer Grade A",
                "grade b": "SEBI Officer Grade B",
                "officer grade b": "SEBI Officer Grade B",
                "assistant manager": "SEBI Assistant Manager",
                "legal officer": "SEBI Legal Officer",
                "information technology": "SEBI IT Officer",
                "official": "SEBI Official",
            },
        },
    ]

    # ------------------------------------------------------------------
    # Scrape orchestration
    # ------------------------------------------------------------------

    def scrape(self) -> list[dict[str, Any]]:
        notifications: list[dict[str, Any]] = []

        for source in self.SOURCES:
            source_name = source["name"]
            base_url = source["base_url"]

            for path in source["paths"]:
                url = self.resolve_url(base_url, path)
                self.logger.info(
                    "[%s] Fetching %s", source_name, url,
                )

                response = self.fetch(url)
                if response is None:
                    self.logger.warning(
                        "[%s] Failed to fetch %s — skipping", source_name, url,
                    )
                    continue

                page_results = self._parse_source_page(response, source)
                self.logger.info(
                    "[%s] Extracted %d notifications from %s",
                    source_name,
                    len(page_results),
                    url,
                )
                notifications.extend(page_results)

        self.logger.info(
            "Banking extended scraper finished: %d total notifications",
            len(notifications),
        )
        return notifications

    def parse_page(self, response: requests.Response) -> list[dict[str, Any]]:
        """
        Default parse_page implementation required by BaseScraper.
        Delegates to _parse_source_page with a generic Banking source context.
        """
        generic_source: dict[str, Any] = {
            "name": "Generic",
            "base_url": response.url,
            "exam_category": self.EXAM_CATEGORY,
            "recruiting_body": "Banking Recruitment",
            "selectors": ["table tr", "a"],
            "keywords": {},
        }
        return self._parse_source_page(response, generic_source)

    # ------------------------------------------------------------------
    # Per-source page parser
    # ------------------------------------------------------------------

    def _parse_source_page(
        self,
        response: requests.Response,
        source: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """
        Parse a single page using the CSS selectors and keyword map defined
        in *source*. Returns a list of notification dicts.
        """
        results: list[dict[str, Any]] = []
        soup = BeautifulSoup(response.text, "html.parser")

        selectors: list[str] = source.get("selectors", ["table tr", "a"])
        keywords: dict[str, str] = source.get("keywords", {})
        base_url: str = source["base_url"]
        recruiting_body: str = source["recruiting_body"]
        exam_category: str = source.get("exam_category", self.EXAM_CATEGORY)

        seen_hrefs: set[str] = set()

        for selector in selectors:
            for element in soup.select(selector):
                parsed = self._extract_from_element(
                    element=element,
                    base_url=base_url,
                    keywords=keywords,
                    recruiting_body=recruiting_body,
                    exam_category=exam_category,
                    seen_hrefs=seen_hrefs,
                )
                if parsed is not None:
                    results.append(parsed)

        return results

    # ------------------------------------------------------------------
    # Element-level extraction
    # ------------------------------------------------------------------

    def _extract_from_element(
        self,
        *,
        element: Tag,
        base_url: str,
        keywords: dict[str, str],
        recruiting_body: str,
        exam_category: str,
        seen_hrefs: set[str],
    ) -> Optional[dict[str, Any]]:
        """
        Try to extract a recruitment notification from a single HTML element
        (table row, list item, card, or anchor tag).
        """
        # Find the first anchor with an href inside the element.
        link_tag: Optional[Tag] = (
            element if element.name == "a" else element.find("a", href=True)
        )
        if link_tag is None or not link_tag.get("href"):
            return None

        href: str = link_tag["href"].strip()
        if not href or href == "#":
            return None

        # De-duplicate within this page.
        if href in seen_hrefs:
            return None

        text: str = link_tag.get_text(strip=True)
        if not text:
            return None

        # Match against recruitment signals + exam keywords.
        post_name = self._match_exam(text, keywords)
        if post_name is None:
            return None

        seen_hrefs.add(href)

        source_url = self.resolve_url(base_url, href)
        pdf_url = source_url if href.lower().endswith(".pdf") else None

        # Try to pull a date from the surrounding row text.
        row_text = element.get_text(" ", strip=True) if element.name != "a" else ""
        notification_date = self._extract_date(row_text)

        # Override exam_category at the notification level.
        return self.build_notification_dict(
            recruiting_body=recruiting_body,
            post_name=post_name,
            source_url=source_url,
            pdf_url=pdf_url,
            notification_date=notification_date,
            official_website=base_url,
            exam_category=exam_category,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _match_exam(text: str, keywords: dict[str, str]) -> Optional[str]:
        """
        Return the canonical exam/post name if *text* contains a recruitment
        signal AND matches a known keyword.  Returns ``None`` otherwise.
        """
        text_lower = text.lower()

        # Must look like a recruitment-related notice.
        if not any(sig in text_lower for sig in _RECRUITMENT_SIGNALS):
            return None

        for keyword, canonical in keywords.items():
            if keyword in text_lower:
                return canonical

        return None

    def _extract_date(self, text: str) -> Any:
        """Best-effort date extraction from surrounding row text."""
        match = re.search(r"(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{4})", text)
        if match:
            return self.parse_date(match.group(1))
        return None
