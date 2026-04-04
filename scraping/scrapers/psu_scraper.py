from __future__ import annotations
"""
Scraper for Public Sector Undertakings (PSUs) and government research
organisations in India.

Covers 35+ organisations across defence/space research, heavy engineering,
oil & gas, power, steel/mining, transport, shipbuilding, research, and
telecom sectors.
"""

import re
from typing import Any, Optional

import requests
from bs4 import BeautifulSoup, Tag

from scraping.scrapers.base_scraper import BaseScraper

# ---------------------------------------------------------------------------
# PSU sources
# ---------------------------------------------------------------------------

SOURCES: list[dict[str, Any]] = [
    # Defence / Space Research
    {"name": "DRDO", "base_url": "https://www.drdo.gov.in", "paths": ["/", "/drdo/career"], "recruiting_body": "Defence Research & Development Organisation (DRDO)"},
    {"name": "ISRO", "base_url": "https://www.isro.gov.in", "paths": ["/", "/careers.html"], "recruiting_body": "Indian Space Research Organisation (ISRO)"},
    {"name": "BARC", "base_url": "https://www.barc.gov.in", "paths": ["/", "/careers"], "recruiting_body": "Bhabha Atomic Research Centre (BARC)"},
    # Heavy Engineering / Manufacturing
    {"name": "HAL", "base_url": "https://hal-india.co.in", "paths": ["/", "/careers.asp"], "recruiting_body": "Hindustan Aeronautics Limited (HAL)"},
    {"name": "BEL", "base_url": "https://www.bel-india.in", "paths": ["/", "/Ede/career.aspx"], "recruiting_body": "Bharat Electronics Limited (BEL)"},
    {"name": "BHEL", "base_url": "https://www.bhel.com", "paths": ["/", "/careers"], "recruiting_body": "Bharat Heavy Electricals Limited (BHEL)"},
    {"name": "ECIL", "base_url": "https://www.ecil.co.in", "paths": ["/", "/jobs.htm"], "recruiting_body": "Electronics Corporation of India Limited (ECIL)"},
    # Oil & Gas / Energy
    {"name": "ONGC", "base_url": "https://www.ongcindia.com", "paths": ["/", "/wps/wcm/connect/en/careers/"], "recruiting_body": "Oil and Natural Gas Corporation (ONGC)"},
    {"name": "GAIL", "base_url": "https://gailonline.com", "paths": ["/", "/careers"], "recruiting_body": "GAIL (India) Limited"},
    {"name": "IOCL", "base_url": "https://iocl.com", "paths": ["/", "/pages/PeopleCareers.aspx"], "recruiting_body": "Indian Oil Corporation Limited (IOCL)"},
    {"name": "BPCL", "base_url": "https://www.bharatpetroleum.in", "paths": ["/", "/careers"], "recruiting_body": "Bharat Petroleum Corporation Limited (BPCL)"},
    {"name": "HPCL", "base_url": "https://www.hindustanpetroleum.com", "paths": ["/", "/pages/careers"], "recruiting_body": "Hindustan Petroleum Corporation Limited (HPCL)"},
    # Power
    {"name": "NTPC", "base_url": "https://www.ntpc.co.in", "paths": ["/", "/en/careers"], "recruiting_body": "National Thermal Power Corporation (NTPC)"},
    {"name": "PowerGrid", "base_url": "https://www.powergrid.in", "paths": ["/", "/careers"], "recruiting_body": "Power Grid Corporation of India"},
    {"name": "NHPC", "base_url": "https://www.nhpcindia.com", "paths": ["/", "/career.htm"], "recruiting_body": "NHPC Limited"},
    {"name": "NPCIL", "base_url": "https://www.npcil.co.in", "paths": ["/", "/career_main.aspx"], "recruiting_body": "Nuclear Power Corporation of India Limited (NPCIL)"},
    # Steel / Mining / Metals
    {"name": "SAIL", "base_url": "https://www.sail.co.in", "paths": ["/", "/career.php"], "recruiting_body": "Steel Authority of India Limited (SAIL)"},
    {"name": "CoalIndia", "base_url": "https://www.coalindia.in", "paths": ["/", "/en-us/career"], "recruiting_body": "Coal India Limited"},
    {"name": "NALCO", "base_url": "https://nalcoindia.com", "paths": ["/", "/career.aspx"], "recruiting_body": "National Aluminium Company (NALCO)"},
    {"name": "NMDC", "base_url": "https://www.nmdc.co.in", "paths": ["/", "/careers"], "recruiting_body": "National Mineral Development Corporation (NMDC)"},
    # Transport / Infrastructure
    {"name": "AAI", "base_url": "https://www.aai.aero", "paths": ["/", "/en/content/job-openings"], "recruiting_body": "Airports Authority of India (AAI)"},
    {"name": "FCI", "base_url": "https://fci.gov.in", "paths": ["/", "/recruitments.php"], "recruiting_body": "Food Corporation of India (FCI)"},
    {"name": "CONCOR", "base_url": "https://www.concorindia.co.in", "paths": ["/", "/career.asp"], "recruiting_body": "Container Corporation of India (CONCOR)"},
    {"name": "DMRC", "base_url": "https://www.delhimetrorail.com", "paths": ["/", "/career"], "recruiting_body": "Delhi Metro Rail Corporation (DMRC)"},
    # Shipbuilding / Defence Production
    {"name": "MDL", "base_url": "https://mazagondock.in", "paths": ["/", "/career-default.aspx"], "recruiting_body": "Mazagon Dock Shipbuilders Limited (MDL)"},
    {"name": "GRSE", "base_url": "https://grse.in", "paths": ["/", "/career"], "recruiting_body": "Garden Reach Shipbuilders & Engineers (GRSE)"},
    {"name": "BDL", "base_url": "https://bdl-india.in", "paths": ["/", "/career.html"], "recruiting_body": "Bharat Dynamics Limited (BDL)"},
    {"name": "HSL", "base_url": "https://hsl.nic.in", "paths": ["/", "/careers.htm"], "recruiting_body": "Hindustan Shipyard Limited (HSL)"},
    # Research / Science
    {"name": "CSIR", "base_url": "https://www.csir.res.in", "paths": ["/", "/career"], "recruiting_body": "Council of Scientific & Industrial Research (CSIR)"},
    {"name": "ICAR", "base_url": "https://icar.org.in", "paths": ["/", "/content/recruitments"], "recruiting_body": "Indian Council of Agricultural Research (ICAR)"},
    # Telecom / IT
    {"name": "BSNL", "base_url": "https://www.bsnl.co.in", "paths": ["/", "/opencms/bsnl/BSNL/about_us/career/"], "recruiting_body": "Bharat Sanchar Nigam Limited (BSNL)"},
    {"name": "MTNL", "base_url": "https://www.mtnl.in", "paths": ["/"], "recruiting_body": "Mahanagar Telephone Nigam Limited (MTNL)"},
    # Other Important PSUs
    {"name": "RITES", "base_url": "https://www.rites.com", "paths": ["/", "/career"], "recruiting_body": "RITES Limited"},
    {"name": "IRCON", "base_url": "https://www.ircon.org", "paths": ["/", "/career.php"], "recruiting_body": "IRCON International Limited"},
    {"name": "NBCC", "base_url": "https://www.nbccindia.in", "paths": ["/", "/career"], "recruiting_body": "National Buildings Construction Corporation (NBCC)"},
    {"name": "WAPCOS", "base_url": "https://www.wapcos.gov.in", "paths": ["/", "/career.htm"], "recruiting_body": "WAPCOS Limited"},
]

# ---------------------------------------------------------------------------
# PSU-specific keywords that indicate a recruitment notification
# ---------------------------------------------------------------------------

_PSU_KEYWORDS: dict[str, str] = {
    "engineer": "Engineer",
    "management trainee": "Management Trainee (MT)",
    "executive trainee": "Executive Trainee (ET)",
    "graduate trainee": "Graduate Trainee",
    "apprentice": "Apprentice",
    "trade apprentice": "Trade Apprentice",
    "technician": "Technician",
    "scientist": "Scientist",
    "junior engineer": "Junior Engineer",
    "diploma trainee": "Diploma Trainee",
    "artisan": "Artisan",
    "operator": "Operator",
    "assistant": "Assistant",
    "officer": "Officer",
    "manager": "Manager",
    "superintendent": "Superintendent",
    "trainee": "Trainee",
    "gate": "GATE-based recruitment",
    "through gate": "GATE-based recruitment",
    "junior assistant": "Junior Assistant",
    "accounts officer": "Accounts Officer",
    "finance": "Finance Officer",
    "hr": "HR Officer",
    "legal": "Legal Officer",
    "medical officer": "Medical Officer",
    "security": "Security Officer",
    "fireman": "Fireman",
    "fitter": "Fitter",
    "electrician": "Electrician",
    "welder": "Welder",
    "machinist": "Machinist",
    "turner": "Turner",
}

# Broad CSS selectors that cover the varied HTML structures of PSU sites.
_CSS_SELECTORS: list[str] = [
    "table tr",
    ".career a",
    ".recruitment a",
    ".content a",
    "article a",
    ".notification a",
    "ul li a",
    ".card a",
    ".list-group-item a",
    "#content a",
    "main a",
    ".container a",
    ".job-listing a",
    ".vacancy a",
    "marquee a",
    ".page-content a",
    "#ContentPlaceHolder1 a",
]

# Signals that a link text is about recruitment rather than general news.
_RECRUITMENT_SIGNALS = (
    "recruitment",
    "notification",
    "vacancy",
    "vacancies",
    "advt",
    "advertisement",
    "walk-in",
    "walk in",
    "engagement",
    "hiring",
    "career",
    "openings",
    "apply",
    "application",
    "appointment",
    "empanelment",
    "contractual",
    "positions",
    "indent",
)


class PSUScraper(BaseScraper):
    SCRAPER_NAME = "psu"
    BASE_URL = ""  # Multi-source scraper; no single base URL.
    EXAM_CATEGORY = "PSU"
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
            "PSU scraper extracted %d notifications from %d sources",
            len(notifications),
            len(SOURCES),
        )
        return notifications

    # ------------------------------------------------------------------
    # Per-source scraping
    # ------------------------------------------------------------------

    def _scrape_source(self, source: dict[str, Any]) -> list[dict[str, Any]]:
        """Scrape all configured paths for a single PSU source."""
        results: list[dict[str, Any]] = []
        base_url: str = source["base_url"]

        for path in source["paths"]:
            url = self.resolve_url(base_url, path)
            try:
                response = self.fetch(url)
                if response is None:
                    continue
                parsed = self.parse_page(
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

    def parse_page(  # type: ignore[override]
        self,
        response: requests.Response,
        recruiting_body: str = "",
        base_url: str = "",
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        soup = BeautifulSoup(response.text, "html.parser")

        # Collect candidate elements using all CSS selectors.
        elements: list[Tag] = []
        for selector in _CSS_SELECTORS:
            try:
                elements.extend(soup.select(selector))
            except Exception:
                # Some selectors may fail on malformed HTML; ignore.
                continue

        # Deduplicate elements by id to avoid processing the same tag twice.
        seen_ids: set[int] = set()
        unique_elements: list[Tag] = []
        for el in elements:
            el_id = id(el)
            if el_id not in seen_ids:
                seen_ids.add(el_id)
                unique_elements.append(el)

        for element in unique_elements:
            parsed = self._extract_from_element(
                element,
                page_url=response.url,
                recruiting_body=recruiting_body,
                base_url=base_url,
            )
            if parsed is not None:
                results.append(parsed)

        return results

    # ------------------------------------------------------------------
    # Element-level extraction
    # ------------------------------------------------------------------

    def _extract_from_element(
        self,
        element: Tag,
        page_url: str,
        recruiting_body: str,
        base_url: str,
    ) -> Optional[dict[str, Any]]:
        """
        Try to extract a recruitment notification from a single HTML element
        (table row, list item, or anchor tag).
        """
        # Locate the anchor tag.
        link_tag: Optional[Tag] = (
            element if element.name == "a" else element.find("a", href=True)
        )
        if link_tag is None or not link_tag.get("href"):
            return None

        href: str = link_tag["href"].strip()
        text: str = link_tag.get_text(strip=True)

        if not text or len(text) < 5:
            return None

        # Must look like a recruitment notification.
        post_name = self._match_post(text)
        if post_name is None:
            return None

        source_url = self.resolve_url(base_url or page_url, href)
        pdf_url = source_url if href.lower().endswith(".pdf") else None

        # Try to extract a date from surrounding row text.
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
    def _match_post(text: str) -> Optional[str]:
        """
        Return a canonical post/role name if *text* looks like a PSU
        recruitment notification.
        """
        text_lower = text.lower()

        # First gate: must contain a recruitment signal word.
        if not any(sig in text_lower for sig in _RECRUITMENT_SIGNALS):
            return None

        # Check longer keywords first to prefer specific matches
        # (e.g. "management trainee" before "trainee").
        for keyword in sorted(_PSU_KEYWORDS, key=len, reverse=True):
            if keyword in text_lower:
                return _PSU_KEYWORDS[keyword]

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
            r"(\d+)\s*(?:posts?|vacancies|vacancy|positions?|openings?)", text, re.IGNORECASE
        )
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return None
        return None
