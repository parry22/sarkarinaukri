from __future__ import annotations
"""
Scraper for Institute of Banking Personnel Selection (IBPS) notifications.

Targets: ibps.in — the official IBPS website.
Covers: PO, Clerk, SO, RRB (PO / Clerk / Office Assistant).
Also attempts to consume RSS feeds when available.
"""

import re
from typing import Any, Optional
from xml.etree import ElementTree

import requests
from bs4 import BeautifulSoup, Tag

from scraping.scrapers.base_scraper import BaseScraper

_EXAM_KEYWORDS: dict[str, str] = {
    "po/mt": "Probationary Officer / Management Trainee (PO/MT)",
    "probationary officer": "Probationary Officer / Management Trainee (PO/MT)",
    "clerk": "Clerk",
    "clerical cadre": "Clerk",
    "so": "Specialist Officer (SO)",
    "specialist officer": "Specialist Officer (SO)",
    "rrb po": "RRB Probationary Officer (RRB PO)",
    "rrb clerk": "RRB Clerk / Office Assistant",
    "rrb office assistant": "RRB Clerk / Office Assistant",
}


class IBPSScraper(BaseScraper):
    SCRAPER_NAME = "ibps"
    BASE_URL = "https://www.ibps.in"
    EXAM_CATEGORY = "Banking"
    MIN_REQUEST_INTERVAL = 2.5

    # Pages to scrape.
    NOTIFICATION_PATHS = [
        "/",  # Homepage often has a scrolling ticker with latest notifications.
    ]

    RSS_FEEDS: list[str] = [
        # IBPS does not always expose a stable RSS; keep as placeholder.
        # "https://www.ibps.in/rss.xml",
    ]

    def scrape(self) -> list[dict[str, Any]]:
        notifications: list[dict[str, Any]] = []

        # 1. HTML scrape.
        for path in self.NOTIFICATION_PATHS:
            url = self.resolve_url(self.BASE_URL, path)
            response = self.fetch(url)
            if response is None:
                continue
            notifications.extend(self.parse_page(response))

        # 2. RSS feeds (if any are configured).
        for feed_url in self.RSS_FEEDS:
            rss_items = self._parse_rss(feed_url)
            notifications.extend(rss_items)

        self.logger.info("IBPS scraper extracted %d notifications", len(notifications))
        return notifications

    def parse_page(self, response: requests.Response) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        soup = BeautifulSoup(response.text, "html.parser")

        # IBPS site uses marquee / scrolling divs and plain anchor lists.
        selectors = [
            "marquee a",
            ".scrolling-text a",
            ".ticker a",
            "#exams a",
            ".content-area a",
            "table.table a",
            "#block-system-main a",
        ]

        seen_hrefs: set[str] = set()
        for selector in selectors:
            for tag in soup.select(selector):
                parsed = self._extract_notification(tag, response.url, seen_hrefs)
                if parsed is not None:
                    results.append(parsed)

        return results

    def _extract_notification(
        self,
        link_tag: Tag,
        page_url: str,
        seen: set[str],
    ) -> Optional[dict[str, Any]]:
        href = (link_tag.get("href") or "").strip()
        if not href or href in seen:
            return None

        text = link_tag.get_text(strip=True)
        if not text:
            return None

        exam_name = self._match_exam(text)
        if exam_name is None:
            return None

        seen.add(href)
        source_url = self.resolve_url(self.BASE_URL, href)
        pdf_url = source_url if href.lower().endswith(".pdf") else None

        return self.build_notification_dict(
            recruiting_body="Institute of Banking Personnel Selection (IBPS)",
            post_name=exam_name,
            source_url=source_url,
            pdf_url=pdf_url,
            official_website=self.BASE_URL,
        )

    # ------------------------------------------------------------------
    # RSS
    # ------------------------------------------------------------------

    def _parse_rss(self, feed_url: str) -> list[dict[str, Any]]:
        """Fetch and parse an RSS/Atom feed for notification items."""
        response = self.fetch(feed_url)
        if response is None:
            return []

        results: list[dict[str, Any]] = []
        try:
            root = ElementTree.fromstring(response.content)
        except ElementTree.ParseError:
            self.logger.warning("Failed to parse RSS XML from %s", feed_url)
            return []

        # Handle both RSS 2.0 (<item>) and Atom (<entry>) elements.
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        items = root.findall(".//item") or root.findall(".//atom:entry", ns)

        for item in items:
            title_el = item.find("title") or item.find("atom:title", ns)
            link_el = item.find("link") or item.find("atom:link", ns)
            if title_el is None or link_el is None:
                continue

            title = (title_el.text or "").strip()
            link = (
                link_el.text or link_el.get("href", "")
            ).strip()

            exam_name = self._match_exam(title)
            if exam_name is None:
                continue

            source_url = self.resolve_url(self.BASE_URL, link)
            pdf_url = source_url if link.lower().endswith(".pdf") else None

            pub_date_el = item.find("pubDate") or item.find("atom:published", ns)
            notification_date = None
            if pub_date_el is not None and pub_date_el.text:
                notification_date = self.parse_date(pub_date_el.text.strip())

            results.append(
                self.build_notification_dict(
                    recruiting_body="Institute of Banking Personnel Selection (IBPS)",
                    post_name=exam_name,
                    source_url=source_url,
                    pdf_url=pdf_url,
                    notification_date=notification_date,
                    official_website=self.BASE_URL,
                )
            )

        return results

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _match_exam(text: str) -> Optional[str]:
        text_lower = text.lower()

        recruitment_signals = (
            "recruitment",
            "notification",
            "crp",
            "vacancy",
            "advt",
            "advertisement",
            "online",
        )
        if not any(sig in text_lower for sig in recruitment_signals):
            return None

        for keyword, canonical in _EXAM_KEYWORDS.items():
            if keyword in text_lower:
                return canonical

        return None
