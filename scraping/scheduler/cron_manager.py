from __future__ import annotations
"""
Cron/scheduling manager for the Sarkari Naukri Alert Bot.

Uses APScheduler to run scrapers on configured intervals, process the
alert queue, and queue deadline reminders. Each scraper job is isolated
so that a failure in one does not affect others.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from database.connection import get_supabase
from database.models import Notification
from scraping.scrapers import (
    SSCScraper,
    UPSCScraper,
    IBPSScraper,
    RRBScraper,
    NTAScraper,
    AggregatorScraper,
    BankingScraper,
    DefenceScraper,
    ParamilitaryScraper,
    PSUScraper,
    StatePSCScraper,
    EducationScraper,
    HealthcareScraper,
    IndiaPostScraper,
    MiscGovtScraper,
)
from scraping.storage.notification_store import store_notification
from scraping.parsers.eligibility_parser import parse_notification
from scraping.parsers.pdf_parser import extract_text_from_pdf
from alerts.alert_queue import queue_alerts_for_notification, process_pending_alerts, queue_deadline_reminders
from alerts.reminder_scheduler import check_and_send_reminders

logger = logging.getLogger(__name__)

_scheduler: Optional[BackgroundScheduler] = None

# ---------------------------------------------------------------------------
# Scraper job definitions: (scraper_class, interval_hours, job_id)
# ---------------------------------------------------------------------------

SCRAPER_SCHEDULE = [
    # --- Original scrapers ---
    (SSCScraper, 2, "scrape_ssc"),              # Every 2 hours
    (UPSCScraper, 4, "scrape_upsc"),            # Every 4 hours
    (IBPSScraper, 4, "scrape_ibps"),            # Every 4 hours
    (RRBScraper, 3, "scrape_rrb"),              # Every 3 hours (now covers 21 zones)
    (NTAScraper, 2, "scrape_nta"),              # Every 2 hours
    (AggregatorScraper, 1, "scrape_aggregator"),# Every 1 hour (early warning, 8 sites)

    # --- Tier 1: High-impact new scrapers ---
    (BankingScraper, 3, "scrape_banking"),       # SBI, RBI, LIC, NABARD, SEBI — every 3 hours
    (DefenceScraper, 4, "scrape_defence"),       # Army, Navy, AF, Coast Guard — every 4 hours
    (ParamilitaryScraper, 4, "scrape_paramilitary"),  # CRPF, BSF, CISF, ITBP, SSB — every 4 hours
    (PSUScraper, 6, "scrape_psu"),              # 36 PSUs — every 6 hours (large, polite interval)
    (StatePSCScraper, 6, "scrape_state_psc"),   # 35 state PSCs/SSBs — every 6 hours

    # --- Tier 2: Specialist scrapers ---
    (EducationScraper, 6, "scrape_education"),   # KVS, NVS, CBSE, NCERT — every 6 hours
    (HealthcareScraper, 6, "scrape_healthcare"), # AIIMS, ESIC, PGIMER, NHM — every 6 hours
    (IndiaPostScraper, 4, "scrape_india_post"),  # India Post GDS — every 4 hours
    (MiscGovtScraper, 6, "scrape_misc_govt"),    # EPFO, Employment News, Courts — every 6 hours
]


# ---------------------------------------------------------------------------
# Scraper runner
# ---------------------------------------------------------------------------

def _run_scraper_job(scraper_class: type) -> None:
    """
    Execute a single scraper job with full pipeline:
    1. Run the scraper to find notifications.
    2. For each notification with a PDF, extract text and parse eligibility.
    3. Store in DB via notification_store.
    4. Queue alerts for eligible users.
    5. Log the run in scraper_runs table.

    Errors are caught and logged so they do not propagate to the scheduler.
    """
    scraper_name = scraper_class.SCRAPER_NAME
    client = get_supabase()

    # Log the start of this run
    run_record = client.table("scraper_runs").insert({
        "scraper_name": scraper_name,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "status": "running",
    }).execute()

    run_id = run_record.data[0]["id"] if run_record.data else None

    notifications_found = 0
    new_notifications = 0

    try:
        scraper = scraper_class()
        raw_notifications = scraper.run()
        notifications_found = len(raw_notifications)

        for raw_notif in raw_notifications:
            try:
                # If there is a PDF URL, extract text and enrich with parsed data
                pdf_url = raw_notif.get("pdf_url")
                if pdf_url:
                    try:
                        pdf_text = extract_text_from_pdf(pdf_url)
                        if pdf_text:
                            parsed_data = parse_notification(pdf_text)
                            # Merge parsed data into raw notification (raw takes precedence
                            # for fields it already has)
                            for key, value in parsed_data.items():
                                if key not in raw_notif or raw_notif[key] is None:
                                    raw_notif[key] = value
                    except Exception as pdf_exc:
                        logger.warning(
                            "PDF parsing failed for %s: %s",
                            pdf_url,
                            pdf_exc,
                        )

                # Store the notification (upsert with dedup)
                stored = store_notification(raw_notif)

                if stored and stored.get("id"):
                    new_notifications += 1
                    # Queue alerts for eligible users
                    try:
                        notification = Notification(**stored)
                        queue_alerts_for_notification(notification)
                    except Exception as queue_exc:
                        logger.error(
                            "Failed to queue alerts for notification %s: %s",
                            stored.get("id"),
                            queue_exc,
                        )

            except Exception as notif_exc:
                logger.error(
                    "Failed to process notification from %s: %s",
                    scraper_name,
                    notif_exc,
                )

        # Update run record with success
        if run_id:
            client.table("scraper_runs").update({
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "status": "success",
                "notifications_found": notifications_found,
                "new_notifications": new_notifications,
            }).eq("id", run_id).execute()

        logger.info(
            "%s scraper completed: %d found, %d new",
            scraper_name,
            notifications_found,
            new_notifications,
        )

    except Exception as exc:
        logger.exception("Scraper job %s failed: %s", scraper_name, exc)

        if run_id:
            try:
                client.table("scraper_runs").update({
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                    "status": "failed",
                    "notifications_found": notifications_found,
                    "new_notifications": new_notifications,
                    "error_message": str(exc)[:500],
                }).eq("id", run_id).execute()
            except Exception:
                logger.error("Failed to update scraper_runs for %s", scraper_name)


def _process_alert_queue_job() -> None:
    """Process pending alerts from the queue. Isolated error handling."""
    try:
        results = process_pending_alerts(batch_size=50)
        logger.info("Alert queue processed: %s", results)
    except Exception as exc:
        logger.exception("Alert queue processing failed: %s", exc)


def _queue_deadline_reminders_job() -> None:
    """Queue deadline reminders and process due reminders. Isolated error handling."""
    try:
        queued = queue_deadline_reminders()
        logger.info("Deadline reminders queued: %d", queued)
    except Exception as exc:
        logger.exception("Deadline reminder queuing failed: %s", exc)

    try:
        results = check_and_send_reminders()
        logger.info("Reminders sent: %s", results)
    except Exception as exc:
        logger.exception("Reminder sending failed: %s", exc)


# ---------------------------------------------------------------------------
# Scheduler lifecycle
# ---------------------------------------------------------------------------

def setup_scheduler() -> BackgroundScheduler:
    """
    Configure and start the APScheduler with all scraper and alert jobs.

    Scraper jobs (15 scrapers, 100+ sources):
    - SSC: every 2 hours
    - UPSC: every 4 hours
    - IBPS: every 4 hours
    - RRB (21 zones): every 3 hours
    - NTA: every 2 hours
    - Aggregator (8 sites): every 1 hour (early warning)
    - Banking (SBI/RBI/LIC/NABARD/SEBI): every 3 hours
    - Defence (Army/Navy/AF/CG): every 4 hours
    - Paramilitary (CRPF/BSF/CISF/ITBP/SSB/AR/RPF): every 4 hours
    - PSU (36 orgs): every 6 hours
    - State PSC (35 PSCs+SSBs): every 6 hours
    - Education (KVS/NVS/CBSE/NCERT): every 6 hours
    - Healthcare (AIIMS/ESIC/PGIMER/NHM): every 6 hours
    - India Post: every 4 hours
    - Misc (EPFO/Courts/Employment News): every 6 hours

    Alert jobs:
    - Process alert queue: every 5 minutes
    - Queue deadline reminders: every 6 hours

    Returns:
        The configured and started BackgroundScheduler instance.
    """
    global _scheduler

    if _scheduler is not None and _scheduler.running:
        logger.warning("Scheduler is already running")
        return _scheduler

    _scheduler = BackgroundScheduler(
        job_defaults={
            "coalesce": True,       # Combine missed runs into one
            "max_instances": 1,     # No overlapping runs of the same job
            "misfire_grace_time": 600,  # 10 minutes grace for misfired jobs
        },
    )

    # Register scraper jobs
    for scraper_class, interval_hours, job_id in SCRAPER_SCHEDULE:
        _scheduler.add_job(
            _run_scraper_job,
            trigger=IntervalTrigger(hours=interval_hours),
            id=job_id,
            name=f"Scrape {scraper_class.SCRAPER_NAME}",
            args=[scraper_class],
            replace_existing=True,
        )
        logger.info(
            "Scheduled %s scraper every %d hour(s)",
            scraper_class.SCRAPER_NAME,
            interval_hours,
        )

    # Process alert queue every 5 minutes
    _scheduler.add_job(
        _process_alert_queue_job,
        trigger=IntervalTrigger(minutes=5),
        id="process_alert_queue",
        name="Process alert queue",
        replace_existing=True,
    )

    # Queue deadline reminders every 6 hours
    _scheduler.add_job(
        _queue_deadline_reminders_job,
        trigger=IntervalTrigger(hours=6),
        id="queue_deadline_reminders",
        name="Queue deadline reminders",
        replace_existing=True,
    )

    _scheduler.start()
    logger.info("Scheduler started with %d jobs", len(_scheduler.get_jobs()))
    return _scheduler


def get_scheduler() -> Optional[BackgroundScheduler]:
    """Return the current scheduler instance, or None if not set up."""
    return _scheduler


def shutdown_scheduler() -> None:
    """
    Cleanly shut down the scheduler, waiting for running jobs to finish.
    """
    global _scheduler

    if _scheduler is None:
        logger.warning("No scheduler to shut down")
        return

    if _scheduler.running:
        _scheduler.shutdown(wait=True)
        logger.info("Scheduler shut down gracefully")
    else:
        logger.warning("Scheduler was not running")

    _scheduler = None
