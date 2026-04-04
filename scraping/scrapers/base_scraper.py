from __future__ import annotations
"""
Abstract base scraper with retry logic, rate limiting, rotating User-Agents,
and standardised error handling for all government job notification scrapers.
"""

import hashlib
import logging
import random
import time
from abc import ABC, abstractmethod
from datetime import date, datetime
from typing import Any, Optional
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.4; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]


class BaseScraper(ABC):
    """
    Base class for all notification scrapers.

    Provides:
    - HTTP session with automatic retries and exponential back-off
    - Rotating User-Agent headers
    - Configurable rate limiting between requests
    - Deduplication hash generation
    - Standardised logging and error handling
    """

    # Subclasses must set these.
    SCRAPER_NAME: str = "base"
    BASE_URL: str = ""
    EXAM_CATEGORY: str = ""  # One of ExamCategory values

    # Retry / rate-limit defaults (overridable per scraper).
    MAX_RETRIES: int = 3
    BACKOFF_FACTOR: float = 1.0  # seconds; actual delay = factor * 2^(retry_number)
    REQUEST_TIMEOUT: int = 30  # seconds
    MIN_REQUEST_INTERVAL: float = 2.0  # minimum seconds between requests

    def __init__(self, rate_limit: Optional[float] = None) -> None:
        self.logger = logging.getLogger(f"scraper.{self.SCRAPER_NAME}")
        self._min_interval = rate_limit if rate_limit is not None else self.MIN_REQUEST_INTERVAL
        self._last_request_time: float = 0.0
        self._session = self._build_session()

    # ------------------------------------------------------------------
    # HTTP session helpers
    # ------------------------------------------------------------------

    def _build_session(self) -> requests.Session:
        session = requests.Session()
        retry_strategy = Retry(
            total=self.MAX_RETRIES,
            backoff_factor=self.BACKOFF_FACTOR,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "HEAD"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def _get_headers(self) -> dict[str, str]:
        return {
            "User-Agent": random.choice(_USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,hi;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        }

    def _rate_limit(self) -> None:
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < self._min_interval:
            sleep_for = self._min_interval - elapsed
            self.logger.debug("Rate-limiting: sleeping %.2fs", sleep_for)
            time.sleep(sleep_for)

    def fetch(self, url: str, **kwargs: Any) -> Optional[requests.Response]:
        """
        Fetch a URL with rate limiting, rotating headers, and retries.
        Returns the Response on success, or None on failure.
        """
        self._rate_limit()
        headers = self._get_headers()
        headers.update(kwargs.pop("headers", {}))

        try:
            self.logger.info("Fetching %s", url)
            self._last_request_time = time.monotonic()
            response = self._session.get(
                url,
                headers=headers,
                timeout=self.REQUEST_TIMEOUT,
                **kwargs,
            )
            response.raise_for_status()
            return response
        except requests.exceptions.HTTPError as exc:
            self.logger.error(
                "HTTP error %s for %s: %s",
                getattr(exc.response, "status_code", "N/A"),
                url,
                exc,
            )
        except requests.exceptions.ConnectionError:
            self.logger.error("Connection error for %s", url)
        except requests.exceptions.Timeout:
            self.logger.error("Timeout fetching %s", url)
        except requests.exceptions.RequestException as exc:
            self.logger.error("Request failed for %s: %s", url, exc)

        return None

    # ------------------------------------------------------------------
    # Dedup / utility helpers
    # ------------------------------------------------------------------

    @staticmethod
    def generate_dedup_hash(recruiting_body: str, post_name: str, source_url: str) -> str:
        """
        Deterministic SHA-256 hash for deduplication.
        Normalises inputs to lower-case and strips whitespace before hashing.
        """
        raw = "|".join(
            part.strip().lower() for part in (recruiting_body, post_name, source_url)
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def resolve_url(base: str, relative: str) -> str:
        """Resolve a potentially relative URL against a base URL."""
        return urljoin(base, relative)

    @staticmethod
    def parse_date(text: str, formats: Optional[list[str]] = None) -> Optional[date]:
        """
        Try to parse a date string using common Indian government-site formats.
        Returns None if no format matches.
        """
        if not text:
            return None
        text = text.strip()
        _formats = formats or [
            "%d/%m/%Y",
            "%d-%m-%Y",
            "%d.%m.%Y",
            "%d %b %Y",
            "%d %B %Y",
            "%Y-%m-%d",
        ]
        for fmt in _formats:
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        return None

    def build_notification_dict(
        self,
        *,
        recruiting_body: str,
        post_name: str,
        source_url: str,
        pdf_url: Optional[str] = None,
        notification_type: str = "new_recruitment",
        min_qualification: Optional[str] = None,
        qualification_stream: Optional[str] = None,
        min_age: Optional[int] = None,
        max_age: Optional[int] = None,
        notification_date: Optional[date] = None,
        application_start_date: Optional[date] = None,
        application_end_date: Optional[date] = None,
        total_vacancies: Optional[int] = None,
        official_website: Optional[str] = None,
        is_verified: bool = False,
        **extra: Any,
    ) -> dict[str, Any]:
        """
        Construct a dict that is compatible with the Notification model.
        Automatically generates the dedup_hash and fills exam_category.
        """
        data: dict[str, Any] = {
            "source_url": source_url,
            "pdf_url": pdf_url,
            "dedup_hash": self.generate_dedup_hash(recruiting_body, post_name, source_url),
            "recruiting_body": recruiting_body,
            "post_name": post_name,
            "exam_category": self.EXAM_CATEGORY,
            "notification_type": notification_type,
            "min_qualification": min_qualification,
            "qualification_stream": qualification_stream,
            "min_age": min_age,
            "max_age": max_age,
            "notification_date": notification_date,
            "application_start_date": application_start_date,
            "application_end_date": application_end_date,
            "total_vacancies": total_vacancies,
            "official_website": official_website or self.BASE_URL,
            "is_verified": is_verified,
        }
        data.update(extra)
        return data

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    def scrape(self) -> list[dict[str, Any]]:
        """
        Run the full scrape cycle and return a list of Notification-compatible
        dicts for any new notifications found.
        """
        ...

    @abstractmethod
    def parse_page(self, response: requests.Response) -> list[dict[str, Any]]:
        """
        Parse a single fetched page/response and extract notification dicts.
        """
        ...

    def run(self) -> list[dict[str, Any]]:
        """
        Public entry-point. Wraps scrape() with top-level error handling.
        """
        self.logger.info("Starting %s scraper", self.SCRAPER_NAME)
        try:
            results = self.scrape()
            self.logger.info(
                "%s scraper finished: %d notifications found",
                self.SCRAPER_NAME,
                len(results),
            )
            return results
        except Exception:
            self.logger.exception("Unhandled error in %s scraper", self.SCRAPER_NAME)
            return []
