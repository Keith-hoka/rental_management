import logging
from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import settings
from app.core.db import SessionLocal
from app.services.charges import generate_charges
from app.services.clause_audit import poll_clause_audits
from app.services.compliance import drain_audit_queue
from app.services.compliance import enabled as compliance_enabled
from app.services.compliance import poll_audit_changes
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


async def _compliance_drain_job() -> None:
    """Open a session and drain the compliance audit queue."""
    async with SessionLocal() as session:
        count = await drain_audit_queue(session)
    if count:
        logger.info("compliance queue: audited %s", count)


async def _compliance_poll_job() -> None:
    """Open a session and apply the compliance change feed."""
    async with SessionLocal() as session:
        count = await poll_audit_changes(session)
    logger.info("compliance changes: applied %s", count)


async def _clause_poll_job() -> None:
    """Open a session and advance in-flight clause audits."""
    async with SessionLocal() as session:
        count = await poll_clause_audits(session)
    if count:
        logger.info("clause audits: %s reached a terminal state", count)


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
    if compliance_enabled():
        scheduler.add_job(
            _compliance_drain_job,
            IntervalTrigger(minutes=settings.compliance_queue_interval_minutes),
            id="compliance_drain",
            replace_existing=True,
        )
        scheduler.add_job(
            _compliance_poll_job,
            CronTrigger(hour=settings.compliance_poll_hour),
            id="compliance_poll",
            replace_existing=True,
        )
        scheduler.add_job(
            _clause_poll_job,
            IntervalTrigger(minutes=settings.clause_poll_interval_minutes),
            id="clause_poll",
            replace_existing=True,
        )
    scheduler.start()
