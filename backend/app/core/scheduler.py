import logging
from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.core.db import SessionLocal
from app.services.charges import generate_charges
from app.services.reminders import run_expiry_reminders

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def _run_job() -> None:
    """Open a session and run the expiry-reminder sweep for today."""
    async with SessionLocal() as session:
        count = await run_expiry_reminders(session, datetime.now(UTC).date())
    logger.info("expiry reminders: sent %s", count)


async def _charges_job() -> None:
    """Open a session and generate rent charges due within the lead window."""
    async with SessionLocal() as session:
        count = await generate_charges(session, datetime.now(UTC).date())
    logger.info("rent charges: generated %s", count)


def start_scheduler() -> None:
    """Register the daily reminder and charge-generation jobs and start the scheduler."""
    scheduler.add_job(
        _run_job,
        CronTrigger(hour=settings.reminder_hour),
        id="expiry_reminders",
        replace_existing=True,
    )
    scheduler.add_job(
        _charges_job,
        CronTrigger(hour=settings.charge_generation_hour),
        id="generate_charges",
        replace_existing=True,
    )
    scheduler.start()
