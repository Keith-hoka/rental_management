from app.core.config import settings
from app.core.scheduler import scheduler, start_scheduler


async def test_start_scheduler_registers_both_daily_jobs():
    try:
        start_scheduler()

        reminders = scheduler.get_job("expiry_reminders")
        assert reminders is not None
        assert f"hour='{settings.reminder_hour}'" in str(reminders.trigger)

        charges = scheduler.get_job("generate_charges")
        assert charges is not None
        assert f"hour='{settings.charge_generation_hour}'" in str(charges.trigger)
    finally:
        scheduler.shutdown(wait=False)
