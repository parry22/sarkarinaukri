from __future__ import annotations
from scraping.scrapers.base_scraper import BaseScraper
from scraping.scrapers.ssc_scraper import SSCScraper
from scraping.scrapers.upsc_scraper import UPSCScraper
from scraping.scrapers.ibps_scraper import IBPSScraper
from scraping.scrapers.rrb_scraper import RRBScraper
from scraping.scrapers.nta_scraper import NTAScraper
from scraping.scrapers.aggregator_scraper import AggregatorScraper
from scraping.scrapers.banking_scraper import BankingScraper
from scraping.scrapers.defence_scraper import DefenceScraper
from scraping.scrapers.paramilitary_scraper import ParamilitaryScraper
from scraping.scrapers.psu_scraper import PSUScraper
from scraping.scrapers.state_psc_scraper import StatePSCScraper
from scraping.scrapers.education_scraper import EducationScraper
from scraping.scrapers.healthcare_scraper import HealthcareScraper
from scraping.scrapers.india_post_scraper import IndiaPostScraper
from scraping.scrapers.misc_scraper import MiscGovtScraper

ALL_SCRAPERS: list[type[BaseScraper]] = [
    # Original scrapers
    SSCScraper,
    UPSCScraper,
    IBPSScraper,
    RRBScraper,
    NTAScraper,
    AggregatorScraper,
    # New scrapers — Tier 1
    BankingScraper,
    DefenceScraper,
    ParamilitaryScraper,
    PSUScraper,
    StatePSCScraper,
    # New scrapers — Tier 2
    EducationScraper,
    HealthcareScraper,
    IndiaPostScraper,
    MiscGovtScraper,
]

__all__ = [
    "BaseScraper",
    "SSCScraper",
    "UPSCScraper",
    "IBPSScraper",
    "RRBScraper",
    "NTAScraper",
    "AggregatorScraper",
    "BankingScraper",
    "DefenceScraper",
    "ParamilitaryScraper",
    "PSUScraper",
    "StatePSCScraper",
    "EducationScraper",
    "HealthcareScraper",
    "IndiaPostScraper",
    "MiscGovtScraper",
    "ALL_SCRAPERS",
]
