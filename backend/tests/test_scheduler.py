from app.core.config import settings
from app.core.scheduler import scheduler, start_scheduler


async def test_start_scheduler_registers_daily_job():
    try:
        start_scheduler()
        job = scheduler.get_job("expiry_reminders")
        assert job is not None
        assert f"hour='{settings.reminder_hour}'" in str(job.trigger)
    finally:
        scheduler.shutdown(wait=False)
