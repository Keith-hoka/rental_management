from datetime import date

from app.models import Lease, LeaseFrequency
from app.services.charges import _period_start, _period_starts


def test_period_start_monthly_clamps_month_end():
    assert _period_start(date(2026, 1, 31), LeaseFrequency.monthly, 1) == date(2026, 2, 28)
    assert _period_start(date(2026, 1, 31), LeaseFrequency.monthly, 2) == date(2026, 3, 31)


def test_period_start_weekly():
    assert _period_start(date(2026, 1, 1), LeaseFrequency.weekly, 3) == date(2026, 1, 22)


def test_period_start_fortnightly():
    assert _period_start(date(2026, 1, 1), LeaseFrequency.fortnightly, 2) == date(2026, 1, 29)


def test_period_starts_monthly_up_to_horizon():
    lease = Lease(
        start_date=date(2026, 1, 15),
        end_date=date(2026, 12, 31),
        rent_frequency=LeaseFrequency.monthly,
    )
    assert _period_starts(lease, date(2026, 3, 20)) == [
        date(2026, 1, 15),
        date(2026, 2, 15),
        date(2026, 3, 15),
    ]


def test_period_starts_stops_at_lease_end():
    lease = Lease(
        start_date=date(2026, 1, 1),
        end_date=date(2026, 2, 15),
        rent_frequency=LeaseFrequency.monthly,
    )
    # horizon is far out; the cap is lease.end_date, so only Jan 1 and Feb 1 qualify.
    assert _period_starts(lease, date(2026, 12, 31)) == [date(2026, 1, 1), date(2026, 2, 1)]
