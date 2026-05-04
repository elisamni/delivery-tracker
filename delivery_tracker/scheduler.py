from __future__ import annotations

import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from delivery_tracker.config import get_settings
from delivery_tracker.services.tracker import TrackingService

logger = logging.getLogger(__name__)


def run_scheduler() -> None:
    settings = get_settings()
    tracker = TrackingService()
    scheduler = BlockingScheduler(timezone=settings.scheduler_timezone)
    scheduler.add_job(
        lambda: tracker.run_once(send_cycle_summary=False),
        trigger=IntervalTrigger(minutes=settings.check_interval_minutes),
        id="tracking-check-job",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
    scheduler.add_job(
        lambda: tracker.run_once(send_cycle_summary=True),
        trigger=CronTrigger(
            hour=settings.daily_summary_hour,
            minute=settings.daily_summary_minute,
            timezone=settings.scheduler_timezone,
        ),
        id="daily-summary-job",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
    logger.info(
        "Scheduler started with interval=%s minutes and daily summary at %02d:%02d (%s)",
        settings.check_interval_minutes,
        settings.daily_summary_hour,
        settings.daily_summary_minute,
        settings.scheduler_timezone,
    )
    tracker.run_once(send_cycle_summary=False)
    scheduler.start()
