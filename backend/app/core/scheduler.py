import logging
from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.core.db import SessionLocal
from app.services.reminders import run_expiry_reminders

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def _run_job() -> None:
    """Open a session and run the expiry-reminder sweep for today."""
    async with SessionLocal() as session:
        count = await run_expiry_reminders(session, datetime.now(UTC).date())
    logger.info("expiry reminders: sent %s", count)


def start_scheduler() -> None:
    """Register the daily reminder job and start the scheduler."""
    scheduler.add_job(
        _run_job,
        CronTrigger(hour=settings.reminder_hour),
        id="expiry_reminders",
        replace_existing=True,
    )
    scheduler.start()
