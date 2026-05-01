from __future__ import annotations

import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

from delivery_tracker.config import get_settings
from delivery_tracker.services.tracker import TrackingService

logger = logging.getLogger(__name__)


def run_scheduler() -> None:
    settings = get_settings()
    tracker = TrackingService()
    scheduler = BlockingScheduler()
    scheduler.add_job(
        tracker.run_once,
        trigger=IntervalTrigger(minutes=settings.check_interval_minutes),
        id="tracking-check-job",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
    logger.info("Scheduler started with interval=%s minutes", settings.check_interval_minutes)
    tracker.run_once()
    scheduler.start()
