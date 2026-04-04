from __future__ import annotations
"""
Aggregator cross-check scraper for early notification detection.

Targets: SarkariResult.com and FreeJobAlert.com
Purpose: catch notifications early as an "early-warning" layer and cross-verify
against official sources. All results are marked as **unverified**.
"""

import re
from typing import Any, Optional

import requests
from bs4 import BeautifulSoup, Tag

from scraping.scrapers.base_scraper import BaseScraper

# Map common recruiting body keywords to (recruiting_body, exam_category).
_BODY_MAP: dict[str, tuple[str, str]] = {
    # Existing
    "ssc": ("Staff Selection Commission (SSC)", "SSC"),
    "upsc": ("Union Public Service Commission (UPSC)", "UPSC"),
    "ibps": ("Institute of Banking Personnel Selection (IBPS)", "Banking"),
    "rrb": ("Railway Recruitment Board (RRB)", "Railway"),
    "railway": ("Railway Recruitment Board (RRB)", "Railway"),
    "nta": ("National Testing Agency (NTA)", "Teaching"),
    "bank": ("Banking Sector", "Banking"),
    "sbi": ("State Bank of India (SBI)", "Banking"),
    "rbi": ("Reserve Bank of India (RBI)", "Banking"),
    "nda": ("Union Public Service Commission (UPSC)", "Defence"),
    "cds": ("Union Public Service Commission (UPSC)", "Defence"),
    "capf": ("Union Public Service Commission (UPSC)", "Defence"),
    "police": ("Police Department", "Police"),
    "constable": ("Police Department", "Police"),
    "psc": ("State Public Service Commission", "State_PSC"),
    "state psc": ("State Public Service Commission", "State_PSC"),
    "teacher": ("Teaching Recruitment", "Teaching"),
    "ctet": ("National Testing Agency (NTA)", "Teaching"),
    "ugc net": ("National Testing Agency (NTA)", "Teaching"),
    # Banking / Insurance / Finance
    "nabard": ("NABARD", "Banking"),
    "sebi": ("Securities and Exchange Board of India (SEBI)", "Banking"),
    "lic": ("Life Insurance Corporation (LIC)", "Insurance"),
    "gic": ("General Insurance Corporation (GIC)", "Insurance"),
    "epfo": ("Employees' Provident Fund Organisation (EPFO)", "Banking"),
    "pfrda": ("Pension Fund Regulatory Authority (PFRDA)", "Banking"),
    "irdai": ("Insurance Regulatory Authority (IRDAI)", "Insurance"),
    # Defence / Paramilitary
    "indian army": ("Indian Army", "Defence"),
    "army": ("Indian Army", "Defence"),
    "indian navy": ("Indian Navy", "Defence"),
    "navy": ("Indian Navy", "Defence"),
    "air force": ("Indian Air Force", "Defence"),
    "iaf": ("Indian Air Force", "Defence"),
    "coast guard": ("Indian Coast Guard", "Defence"),
    "agniveer": ("Indian Armed Forces (Agniveer)", "Defence"),
    "agnipath": ("Indian Armed Forces (Agniveer)", "Defence"),
    "crpf": ("Central Reserve Police Force (CRPF)", "Police"),
    "bsf": ("Border Security Force (BSF)", "Police"),
    "cisf": ("Central Industrial Security Force (CISF)", "Police"),
    "itbp": ("Indo-Tibetan Border Police (ITBP)", "Police"),
    "ssb": ("Sashastra Seema Bal (SSB)", "Police"),
    "assam rifles": ("Assam Rifles", "Police"),
    "rpf": ("Railway Protection Force (RPF)", "Police"),
    # PSU / Engineering
    "drdo": ("Defence Research & Development Organisation (DRDO)", "PSU"),
    "isro": ("Indian Space Research Organisation (ISRO)", "PSU"),
    "hal": ("Hindustan Aeronautics Limited (HAL)", "PSU"),
    "bhel": ("Bharat Heavy Electricals Limited (BHEL)", "PSU"),
    "ongc": ("Oil and Natural Gas Corporation (ONGC)", "PSU"),
    "ntpc": ("National Thermal Power Corporation (NTPC)", "PSU"),
    "coal india": ("Coal India Limited", "PSU"),
    "sail": ("Steel Authority of India Limited (SAIL)", "PSU"),
    "power grid": ("Power Grid Corporation of India", "PSU"),
    "gail": ("GAIL (India) Limited", "PSU"),
    "iocl": ("Indian Oil Corporation Limited (IOCL)", "PSU"),
    "indian oil": ("Indian Oil Corporation Limited (IOCL)", "PSU"),
    "bpcl": ("Bharat Petroleum Corporation Limited (BPCL)", "PSU"),
    "hpcl": ("Hindustan Petroleum Corporation Limited (HPCL)", "PSU"),
    "fci": ("Food Corporation of India (FCI)", "PSU"),
    "aai": ("Airports Authority of India (AAI)", "PSU"),
    "bel": ("Bharat Electronics Limited (BEL)", "PSU"),
    "ecil": ("Electronics Corporation of India Limited (ECIL)", "PSU"),
    "nhpc": ("NHPC Limited", "PSU"),
    "npcil": ("Nuclear Power Corporation of India (NPCIL)", "PSU"),
    "barc": ("Bhabha Atomic Research Centre (BARC)", "PSU"),
    "dmrc": ("Delhi Metro Rail Corporation (DMRC)", "PSU"),
    "metro": ("Metro Rail Corporation", "PSU"),
    "nalco": ("National Aluminium Company (NALCO)", "PSU"),
    "nmdc": ("National Mineral Development Corporation (NMDC)", "PSU"),
    "concor": ("Container Corporation of India (CONCOR)", "PSU"),
    "mdl": ("Mazagon Dock Shipbuilders Limited (MDL)", "PSU"),
    "grse": ("Garden Reach Shipbuilders (GRSE)", "PSU"),
    "hsl": ("Hindustan Shipyard Limited (HSL)", "PSU"),
    # State PSC keywords
    "uppsc": ("UP Public Service Commission (UPPSC)", "State_PSC"),
    "bpsc": ("Bihar Public Service Commission (BPSC)", "State_PSC"),
    "mppsc": ("MP Public Service Commission (MPPSC)", "State_PSC"),
    "rpsc": ("Rajasthan Public Service Commission (RPSC)", "State_PSC"),
    "tnpsc": ("Tamil Nadu Public Service Commission (TNPSC)", "State_PSC"),
    "kpsc": ("Karnataka Public Service Commission (KPSC)", "State_PSC"),
    "mpsc": ("Maharashtra Public Service Commission (MPSC)", "State_PSC"),
    "wbpsc": ("West Bengal Public Service Commission (WBPSC)", "State_PSC"),
    "hpsc": ("Haryana Public Service Commission (HPSC)", "State_PSC"),
    "ppsc": ("Punjab Public Service Commission (PPSC)", "State_PSC"),
    "appsc": ("Andhra Pradesh Public Service Commission (APPSC)", "State_PSC"),
    "tspsc": ("Telangana State Public Service Commission (TSPSC)", "State_PSC"),
    "gpsc": ("Gujarat Public Service Commission (GPSC)", "State_PSC"),
    "jpsc": ("Jharkhand Public Service Commission (JPSC)", "State_PSC"),
    "opsc": ("Odisha Public Service Commission (OPSC)", "State_PSC"),
    "ukpsc": ("Uttarakhand Public Service Commission (UKPSC)", "State_PSC"),
    "cgpsc": ("Chhattisgarh Public Service Commission (CGPSC)", "State_PSC"),
    "dsssb": ("Delhi Subordinate Services Selection Board (DSSSB)", "State_PSC"),
    # Healthcare
    "aiims": ("All India Institute of Medical Sciences (AIIMS)", "Healthcare"),
    "esic": ("Employees' State Insurance Corporation (ESIC)", "Healthcare"),
    "pgimer": ("PGIMER Chandigarh", "Healthcare"),
    "jipmer": ("JIPMER Puducherry", "Healthcare"),
    "nursing": ("Healthcare Recruitment", "Healthcare"),
    # Education
    "kvs": ("Kendriya Vidyalaya Sangathan (KVS)", "Teaching"),
    "kendriya vidyalaya": ("Kendriya Vidyalaya Sangathan (KVS)", "Teaching"),
    "nvs": ("Navodaya Vidyalaya Samiti (NVS)", "Teaching"),
    "navodaya": ("Navodaya Vidyalaya Samiti (NVS)", "Teaching"),
    "army public school": ("Army Public School", "Teaching"),
    # Postal
    "india post": ("India Post", "Postal"),
    "post office": ("India Post", "Postal"),
    "gds": ("India Post (GDS)", "Postal"),
    "gramin dak sevak": ("India Post (GDS)", "Postal"),
    "postman": ("India Post", "Postal"),
    # Judiciary
    "high court": ("High Court of India", "Judiciary"),
    "district court": ("District Court", "Judiciary"),
    "supreme court": ("Supreme Court of India", "Judiciary"),
    # Agriculture / Research
    "icar": ("Indian Council of Agricultural Research (ICAR)", "PSU"),
    "csir": ("Council of Scientific & Industrial Research (CSIR)", "PSU"),
}


class AggregatorScraper(BaseScraper):
    """
    Scrapes popular aggregator sites that often publish notification links
    before official websites update. Every notification returned is flagged
    ``is_verified = False`` and must be confirmed against the official source.
    """

    SCRAPER_NAME = "aggregator"
    BASE_URL = ""  # No single base; we scrape multiple sites.
    EXAM_CATEGORY = "SSC"  # Fallback; overridden per-notification.
    MIN_REQUEST_INTERVAL = 2.0

    TARGETS: list[dict[str, str]] = [
        {"name": "SarkariResult", "url": "https://www.sarkariresult.com/", "base": "https://www.sarkariresult.com"},
        {"name": "FreeJobAlert", "url": "https://www.freejobalert.com/latest-notifications/", "base": "https://www.freejobalert.com"},
        {"name": "SarkariExam", "url": "https://www.sarkariexam.com/latest-jobs", "base": "https://www.sarkariexam.com"},
        {"name": "RojgarResult", "url": "https://www.rojgarresult.com/", "base": "https://www.rojgarresult.com"},
        {"name": "EmploymentNews", "url": "https://www.employmentnews.gov.in/", "base": "https://www.employmentnews.gov.in"},
        {"name": "NCS_Portal", "url": "https://www.ncs.gov.in/job-seekers/Pages/Search.aspx", "base": "https://www.ncs.gov.in"},
        {"name": "SarkariNaukriBlog", "url": "https://www.sarkarinaukriblog.com/", "base": "https://www.sarkarinaukriblog.com"},
        {"name": "GovtJobsAlert", "url": "https://www.govtjobsalert.com/", "base": "https://www.govtjobsalert.com"},
    ]

    def scrape(self) -> list[dict[str, Any]]:
        notifications: list[dict[str, Any]] = []

        for target in self.TARGETS:
            self.logger.info("Scraping aggregator: %s", target["name"])
            response = self.fetch(target["url"])
            if response is None:
                continue
            notifications.extend(
                self._parse_target(response, target)
            )

        self.logger.info(
            "Aggregator scraper extracted %d unverified notifications",
            len(notifications),
        )
        return notifications

    def parse_page(self, response: requests.Response) -> list[dict[str, Any]]:
        """Generic parse; delegates to _parse_target with a synthetic target."""
        target = {
            "name": "unknown",
            "url": response.url,
            "base": response.url.rstrip("/"),
        }
        return self._parse_target(response, target)

    def _parse_target(
        self,
        response: requests.Response,
        target: dict[str, str],
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        soup = BeautifulSoup(response.text, "html.parser")
        base_url = target["base"]

        selectors = [
            # SarkariResult uses a plain list of anchors.
            "#post a",
            ".post a",
            ".box a",
            # FreeJobAlert uses widget / post-list layouts.
            ".widget_flavflavor_flavors a",
            ".post-list a",
            "article a",
            ".entry-content a",
            "table tr a",
            # Additional for new aggregators
            ".job-list a",
            ".latest-jobs a",
            ".notification-list a",
            ".noti-box a",
            ".content a",
            "ul.list li a",
            ".jobs-listing a",
            ".vacancy-list a",
            "main a",
            ".page-content a",
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
        link_tag: Tag,
        base_url: str,
        seen: set[str],
    ) -> Optional[dict[str, Any]]:
        href = (link_tag.get("href") or "").strip()
        if not href or href in seen or href == "#":
            return None

        text = link_tag.get_text(strip=True)
        if not text or len(text) < 10:
            return None

        # Must look recruitment-related.
        if not self._is_recruitment_text(text):
            return None

        seen.add(href)
        source_url = self.resolve_url(base_url, href)
        pdf_url = source_url if href.lower().endswith(".pdf") else None

        recruiting_body, exam_category = self._identify_body(text)

        return self.build_notification_dict(
            recruiting_body=recruiting_body,
            post_name=text[:200],  # Use the link text as a preliminary post name.
            source_url=source_url,
            pdf_url=pdf_url,
            exam_category=exam_category,
            notification_type="new_recruitment",
            official_website=base_url,
            is_verified=False,  # Always unverified from aggregators.
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_recruitment_text(text: str) -> bool:
        """Return True if the text looks like a recruitment notification."""
        text_lower = text.lower()
        signals = (
            "recruitment",
            "vacancy",
            "notification",
            "online form",
            "apply online",
            "admit card",
            "result",
            "advt",
            "advertisement",
            "bharti",  # Hindi for recruitment
            "niyukti",  # Hindi for appointment
            "sarkari naukri",
            "government job",
            "new vacancy",
            "latest job",
            "walk-in",
            "contractual",
            "apprentice",
        )
        return any(sig in text_lower for sig in signals)

    @staticmethod
    def _identify_body(text: str) -> tuple[str, str]:
        """
        Best-effort mapping of link text to (recruiting_body, exam_category).
        Falls back to a generic placeholder.
        """
        text_lower = text.lower()
        for keyword, (body, category) in _BODY_MAP.items():
            if keyword in text_lower:
                return body, category
        return "Government of India", "SSC"  # Safe fallback
