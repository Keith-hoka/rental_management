from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

from app.models import Lease, LeaseFrequency


def _period_start(start_date: date, frequency: LeaseFrequency, n: int) -> date:
    """The nth period's start date, anchored to start_date and stepped by frequency."""
    if frequency == LeaseFrequency.weekly:
        return start_date + timedelta(weeks=n)
    if frequency == LeaseFrequency.fortnightly:
        return start_date + timedelta(weeks=2 * n)
    return start_date + relativedelta(months=n)


def _period_starts(lease: Lease, horizon: date) -> list[date]:
    """Every period start from the lease start up to min(horizon, lease.end_date)."""
    limit = min(horizon, lease.end_date)
    starts: list[date] = []
    n = 0
    while True:
        ps = _period_start(lease.start_date, lease.rent_frequency, n)
        if ps > limit:
            break
        starts.append(ps)
        n += 1
    return starts
