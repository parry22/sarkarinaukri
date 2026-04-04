from __future__ import annotations
"""
Scraper for ALL major State Public Service Commissions (PSCs) and
State Staff Selection Boards (SSBs) in India.

Covers 28+ state PSCs and major subordinate service boards.
Each source is scraped independently with per-source error isolation.
"""

import re
from typing import Any, Optional

import requests
from bs4 import BeautifulSoup, Tag

from scraping.scrapers.base_scraper import BaseScraper

# ---------------------------------------------------------------------------
# Source definitions — every state PSC / SSB we track
# ---------------------------------------------------------------------------

STATE_SOURCES: list[dict[str, Any]] = [
    # Tier 1 - Highest aspirant volume
    {"name": "UPPSC", "base_url": "https://uppsc.up.nic.in", "paths": ["/", "/Notifications.aspx", "/AllNotifications.aspx"], "recruiting_body": "Uttar Pradesh Public Service Commission (UPPSC)", "state": "Uttar Pradesh"},
    {"name": "BPSC", "base_url": "https://www.bpsc.bih.nic.in", "paths": ["/", "/Advt.htm"], "recruiting_body": "Bihar Public Service Commission (BPSC)", "state": "Bihar"},
    {"name": "MPPSC", "base_url": "https://mppsc.mp.gov.in", "paths": ["/", "/Notifications"], "recruiting_body": "Madhya Pradesh Public Service Commission (MPPSC)", "state": "Madhya Pradesh"},
    {"name": "RPSC", "base_url": "https://rpsc.rajasthan.gov.in", "paths": ["/", "/latestnotification.aspx"], "recruiting_body": "Rajasthan Public Service Commission (RPSC)", "state": "Rajasthan"},
    {"name": "TNPSC", "base_url": "https://www.tnpsc.gov.in", "paths": ["/", "/Notifications.html"], "recruiting_body": "Tamil Nadu Public Service Commission (TNPSC)", "state": "Tamil Nadu"},
    {"name": "KPSC", "base_url": "https://kpsc.kar.nic.in", "paths": ["/", "/Abortkpsc.aspx"], "recruiting_body": "Karnataka Public Service Commission (KPSC)", "state": "Karnataka"},
    {"name": "MPSC", "base_url": "https://mpsc.gov.in", "paths": ["/", "/advt"], "recruiting_body": "Maharashtra Public Service Commission (MPSC)", "state": "Maharashtra"},
    {"name": "WBPSC", "base_url": "https://wbpsc.gov.in", "paths": ["/", "/advertisement"], "recruiting_body": "West Bengal Public Service Commission (WBPSC)", "state": "West Bengal"},
    # Tier 2 - High volume
    {"name": "HPSC", "base_url": "https://hpsc.gov.in", "paths": ["/", "/advertisement.html"], "recruiting_body": "Haryana Public Service Commission (HPSC)", "state": "Haryana"},
    {"name": "PPSC", "base_url": "https://ppsc.gov.in", "paths": ["/", "/notifications.aspx"], "recruiting_body": "Punjab Public Service Commission (PPSC)", "state": "Punjab"},
    {"name": "APPSC", "base_url": "https://psc.ap.gov.in", "paths": ["/", "/Notifications"], "recruiting_body": "Andhra Pradesh Public Service Commission (APPSC)", "state": "Andhra Pradesh"},
    {"name": "TSPSC", "base_url": "https://www.tspsc.gov.in", "paths": ["/", "/notifications"], "recruiting_body": "Telangana State Public Service Commission (TSPSC)", "state": "Telangana"},
    {"name": "GPSC", "base_url": "https://gpsc.gujarat.gov.in", "paths": ["/", "/advertisements"], "recruiting_body": "Gujarat Public Service Commission (GPSC)", "state": "Gujarat"},
    {"name": "CGPSC", "base_url": "https://psc.cg.gov.in", "paths": ["/", "/advertisement"], "recruiting_body": "Chhattisgarh Public Service Commission (CGPSC)", "state": "Chhattisgarh"},
    {"name": "JPSC", "base_url": "https://www.jpsc.gov.in", "paths": ["/", "/notifications"], "recruiting_body": "Jharkhand Public Service Commission (JPSC)", "state": "Jharkhand"},
    {"name": "OPSC", "base_url": "https://www.opsc.gov.in", "paths": ["/", "/Advertisement.aspx"], "recruiting_body": "Odisha Public Service Commission (OPSC)", "state": "Odisha"},
    {"name": "UKPSC", "base_url": "https://ukpsc.gov.in", "paths": ["/", "/advertisements.html"], "recruiting_body": "Uttarakhand Public Service Commission (UKPSC)", "state": "Uttarakhand"},
    {"name": "KeralaPSC", "base_url": "https://www.keralapsc.gov.in", "paths": ["/", "/notifications"], "recruiting_body": "Kerala Public Service Commission", "state": "Kerala"},
    # Tier 3 - Other states
    {"name": "HPPSC", "base_url": "https://www.hppsc.hp.gov.in", "paths": ["/", "/Advertisement.aspx"], "recruiting_body": "Himachal Pradesh Public Service Commission (HPPSC)", "state": "Himachal Pradesh"},
    {"name": "JKPSC", "base_url": "https://www.jkpsc.nic.in", "paths": ["/", "/notifications.aspx"], "recruiting_body": "Jammu & Kashmir Public Service Commission (JKPSC)", "state": "Jammu & Kashmir"},
    {"name": "APSC_Assam", "base_url": "https://apsc.nic.in", "paths": ["/", "/advertisement.php"], "recruiting_body": "Assam Public Service Commission (APSC)", "state": "Assam"},
    {"name": "GPSC_Goa", "base_url": "https://gpsc.goa.gov.in", "paths": ["/"], "recruiting_body": "Goa Public Service Commission (GPSC)", "state": "Goa"},
    {"name": "MPSC_Manipur", "base_url": "https://mpscmanipur.gov.in", "paths": ["/"], "recruiting_body": "Manipur Public Service Commission (MPSC)", "state": "Manipur"},
    {"name": "MPSC_Meghalaya", "base_url": "https://mpsc.nic.in", "paths": ["/"], "recruiting_body": "Meghalaya Public Service Commission (MePSC)", "state": "Meghalaya"},
    {"name": "NPSC_Nagaland", "base_url": "https://npsc.nagaland.gov.in", "paths": ["/"], "recruiting_body": "Nagaland Public Service Commission (NPSC)", "state": "Nagaland"},
    {"name": "SPSC_Sikkim", "base_url": "https://spsc.sikkim.gov.in", "paths": ["/"], "recruiting_body": "Sikkim Public Service Commission (SPSC)", "state": "Sikkim"},
    {"name": "TPSC_Tripura", "base_url": "https://tpsc.tripura.gov.in", "paths": ["/"], "recruiting_body": "Tripura Public Service Commission (TPSC)", "state": "Tripura"},
    {"name": "MPSC_Mizoram", "base_url": "https://mpsc.mizoram.gov.in", "paths": ["/"], "recruiting_body": "Mizoram Public Service Commission (MPSC)", "state": "Mizoram"},
    # Major State SSBs (Subordinate Services)
    {"name": "DSSSB", "base_url": "https://dsssb.delhi.gov.in", "paths": ["/", "/notification.php"], "recruiting_body": "Delhi Subordinate Services Selection Board (DSSSB)", "state": "Delhi"},
    {"name": "UPSSSC", "base_url": "https://upsssc.gov.in", "paths": ["/", "/AllNotifications.aspx"], "recruiting_body": "Uttar Pradesh Subordinate Services Selection Commission (UPSSSC)", "state": "Uttar Pradesh"},
    {"name": "HSSC", "base_url": "https://www.hssc.gov.in", "paths": ["/", "/advertisement-details.php"], "recruiting_body": "Haryana Staff Selection Commission (HSSC)", "state": "Haryana"},
    {"name": "RSMSSB", "base_url": "https://rsmssb.rajasthan.gov.in", "paths": ["/"], "recruiting_body": "Rajasthan Subordinate & Ministerial Services Selection Board (RSMSSB)", "state": "Rajasthan"},
    {"name": "OSSSC", "base_url": "https://www.osssc.gov.in", "paths": ["/", "/advertisement.html"], "recruiting_body": "Odisha Sub-ordinate Staff Selection Commission (OSSSC)", "state": "Odisha"},
    {"name": "BSSC", "base_url": "https://bssc.bihar.gov.in", "paths": ["/"], "recruiting_body": "Bihar Staff Selection Commission (BSSC)", "state": "Bihar"},
    {"name": "WBSSC", "base_url": "https://www.wbssc.gov.in", "paths": ["/"], "recruiting_body": "West Bengal Staff Selection Commission (WBSSC)", "state": "West Bengal"},
]

# ---------------------------------------------------------------------------
# Keywords for matching State PSC / SSB recruitment notices
# ---------------------------------------------------------------------------

_STATE_PSC_KEYWORDS: dict[str, str] = {
    "pcs": "Provincial Civil Service (PCS)",
    "civil service": "State Civil Service",
    "combined": "Combined Competitive Exam",
    "pre": "Preliminary Examination",
    "mains": "Main Examination",
    "ras": "Rajasthan Administrative Service (RAS)",
    "ras/rts": "RAS/RTS Combined Competitive Exam",
    "uppcs": "UP PCS",
    "bpsc": "BPSC Combined Competitive Exam",
    "judicial service": "Judicial Service Exam",
    "lecturer": "Lecturer",
    "assistant professor": "Assistant Professor",
    "medical officer": "Medical Officer",
    "dental surgeon": "Dental Surgeon",
    "veterinary officer": "Veterinary Officer",
    "forest ranger": "Forest Ranger/Service",
    "forest service": "Forest Service",
    "statistical officer": "Statistical Officer",
    "excise inspector": "Excise Inspector",
    "supply inspector": "Supply Inspector",
    "junior engineer": "Junior Engineer",
    "assistant engineer": "Assistant Engineer",
    "sub inspector": "Sub Inspector",
    "naib tehsildar": "Naib Tehsildar",
    "tehsildar": "Tehsildar",
    "block development officer": "Block Development Officer (BDO)",
    "deputy collector": "Deputy Collector",
    "group a": "Group A Service",
    "group b": "Group B Service",
    "group c": "Group C Post",
    "group d": "Group D Post",
    "recruitment": "General Recruitment",
    "vacancy": "Vacancy Notification",
    "examination": "Examination Notification",
    "advt": "Advertisement",
    "patwari": "Patwari",
    "lekhpal": "Lekhpal",
    "panchayat secretary": "Panchayat Secretary",
    "gram sevak": "Gram Sevak",
    "village development officer": "Village Development Officer (VDO)",
    "ldc": "Lower Division Clerk (LDC)",
    "udc": "Upper Division Clerk (UDC)",
    "steno": "Stenographer",
    "computer operator": "Computer Operator",
    "deo": "Data Entry Operator",
}

# Recruitment-signal words — at least one must appear for a link to qualify.
_RECRUITMENT_SIGNALS = (
    "recruitment",
    "notification",
    "examination",
    "vacancy",
    "advt",
    "advertisement",
    "apply",
    "bharti",
    "niyukti",
    "result",  # results often contain post names useful for awareness
)

# CSS selectors that cover NIC-style sites and modern government portals.
_CSS_SELECTORS = [
    "table tr",
    "#ContentPlaceHolder1 a",
    ".content-area a",
    ".notification a",
    "marquee a",
    ".scrolling a",
    "ul li a",
    "article a",
    ".entry a",
    "main a",
    ".container a",
    "#notice a",
    ".list-group-item a",
    ".card a",
    ".page-content a",
    ".view-content a",
]


class StatePSCScraper(BaseScraper):
    """
    Scraper for all major Indian State Public Service Commissions and
    State Staff Selection Boards.

    Iterates over every source in STATE_SOURCES, fetches each path,
    extracts recruitment links, and maps them to Notification-compatible
    dicts.  Per-source errors are caught and logged so that one flaky
    website does not break the entire run.
    """

    SCRAPER_NAME = "state_psc"
    BASE_URL = ""  # multi-source scraper; no single base URL
    EXAM_CATEGORY = "State_PSC"
    MIN_REQUEST_INTERVAL = 3.0

    # ------------------------------------------------------------------
    # Main scrape loop
    # ------------------------------------------------------------------

    def scrape(self) -> list[dict[str, Any]]:
        all_notifications: list[dict[str, Any]] = []
        seen_hashes: set[str] = set()

        for source in STATE_SOURCES:
            try:
                source_results = self._scrape_source(source)
            except Exception:
                self.logger.exception(
                    "Unhandled error scraping %s (%s); skipping",
                    source["name"],
                    source["base_url"],
                )
                continue

            # Deduplicate across sources within a single run.
            for notif in source_results:
                h = notif.get("dedup_hash", "")
                if h and h not in seen_hashes:
                    seen_hashes.add(h)
                    all_notifications.append(notif)

        self.logger.info(
            "State PSC scraper extracted %d unique notifications from %d sources",
            len(all_notifications),
            len(STATE_SOURCES),
        )
        return all_notifications

    def _scrape_source(self, source: dict[str, Any]) -> list[dict[str, Any]]:
        """Scrape all paths for a single State PSC / SSB source."""
        results: list[dict[str, Any]] = []
        base_url: str = source["base_url"]
        name: str = source["name"]

        for path in source["paths"]:
            url = self.resolve_url(base_url, path)
            try:
                response = self.fetch(url)
            except Exception:
                self.logger.exception(
                    "Error fetching %s path %s", name, url,
                )
                continue

            if response is None:
                self.logger.debug("No response from %s (%s)", name, url)
                continue

            try:
                page_results = self._parse_source_page(response, source)
                results.extend(page_results)
            except Exception:
                self.logger.exception(
                    "Error parsing page for %s (%s)", name, url,
                )

        self.logger.debug(
            "%s: found %d notifications across %d paths",
            name,
            len(results),
            len(source["paths"]),
        )
        return results

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def parse_page(self, response: requests.Response) -> list[dict[str, Any]]:
        """
        Generic parse_page required by BaseScraper.  For this multi-source
        scraper the real work happens in _parse_source_page which receives
        the source metadata.  This fallback treats the response as an
        unknown source.
        """
        return self._parse_source_page(response, source=None)

    def _parse_source_page(
        self,
        response: requests.Response,
        source: Optional[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Parse a single fetched page using broad CSS selectors."""
        results: list[dict[str, Any]] = []
        soup = BeautifulSoup(response.text, "html.parser")

        # Collect candidate elements using all selectors.
        elements: list[Tag] = []
        seen_ids: set[int] = set()  # avoid processing same element twice
        for selector in _CSS_SELECTORS:
            for el in soup.select(selector):
                eid = id(el)
                if eid not in seen_ids:
                    seen_ids.add(eid)
                    elements.append(el)

        for element in elements:
            parsed = self._extract_from_element(element, response.url, source)
            if parsed is not None:
                results.append(parsed)

        return results

    def _extract_from_element(
        self,
        element: Tag,
        page_url: str,
        source: Optional[dict[str, Any]],
    ) -> Optional[dict[str, Any]]:
        """
        Try to extract a recruitment notification from a single HTML element
        (table row, list item, or anchor tag).
        """
        # Locate the first anchor with an href.
        link_tag: Optional[Tag] = (
            element if element.name == "a" else element.find("a", href=True)
        )
        if link_tag is None or not link_tag.get("href"):
            return None

        href: str = link_tag["href"].strip()
        text: str = link_tag.get_text(strip=True)

        if not text or len(text) < 5:
            return None

        # Must look like a recruitment-related notice.
        post_name = self._match_exam(text)
        if post_name is None:
            return None

        # Resolve URLs.
        base = source["base_url"] if source else page_url
        source_url = self.resolve_url(base, href)
        pdf_url = source_url if href.lower().endswith(".pdf") else None

        # Best-effort date extraction from surrounding text.
        row_text = element.get_text(" ", strip=True) if element.name != "a" else ""
        notification_date = self._extract_date(row_text)

        # Source metadata.
        recruiting_body = (
            source["recruiting_body"] if source else "State Public Service Commission"
        )
        official_website = source["base_url"] if source else None
        state = source["state"] if source else None

        # Build the notification dict.  state_restriction is passed as an
        # extra kwarg so it gets merged into the dict by build_notification_dict.
        extra_kwargs: dict[str, Any] = {}
        if state:
            extra_kwargs["state_restriction"] = state

        return self.build_notification_dict(
            recruiting_body=recruiting_body,
            post_name=post_name,
            source_url=source_url,
            pdf_url=pdf_url,
            notification_date=notification_date,
            official_website=official_website,
            **extra_kwargs,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _match_exam(text: str) -> Optional[str]:
        """
        Return a canonical post/exam name if *text* matches known State PSC
        keywords.  A recruitment-signal word must also be present.
        """
        text_lower = text.lower()

        # Quick filter: must contain at least one recruitment-signal word.
        if not any(sig in text_lower for sig in _RECRUITMENT_SIGNALS):
            return None

        # Check for specific exam/post keywords.
        for keyword, canonical in _STATE_PSC_KEYWORDS.items():
            if keyword in text_lower:
                return canonical

        # If none of the specific keywords matched but the text has a signal,
        # treat it as a generic recruitment notification (only if it has
        # meaningful length to avoid false positives).
        if len(text) >= 20:
            return text.strip()[:120]

        return None

    def _extract_date(self, text: str) -> Any:
        """Best-effort date extraction from surrounding row text."""
        match = re.search(r"(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{4})", text)
        if match:
            return self.parse_date(match.group(1))
        return None
