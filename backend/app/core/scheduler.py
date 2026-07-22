import logging
from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.core.db import SessionLocal
from app.services.charges import generate_charges
from app.services.reminders import run_expiry_reminders
from app.services.rent_reminders import run_rent_reminders

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


async def _rent_job() -> None:
    """Open a session and send rent due-soon and overdue reminders for today."""
    async with SessionLocal() as session:
        count = await run_rent_reminders(session, datetime.now(UTC).date())
    logger.info("rent reminders: sent %s", count)


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
    scheduler.add_job(
        _rent_job,
        CronTrigger(hour=settings.rent_reminder_hour),
        id="rent_reminders",
        replace_existing=True,
    )
    scheduler.start()
