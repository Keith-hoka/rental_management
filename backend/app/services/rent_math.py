"""Rent arithmetic shared by the rent features."""

from decimal import ROUND_HALF_UP, Decimal

from app.models import LeaseFrequency

_WEEKS_PER_PERIOD = {
    LeaseFrequency.weekly: Decimal(1),
    LeaseFrequency.fortnightly: Decimal(2),
    LeaseFrequency.monthly: Decimal(52) / Decimal(12),
}


def weekly_rent(amount: Decimal, frequency: LeaseFrequency) -> Decimal:
    """A rent amount per period as whole weekly dollars."""
    return (Decimal(amount) / _WEEKS_PER_PERIOD[frequency]).quantize(
        Decimal(1), rounding=ROUND_HALF_UP
    )


def gap_pct(current_weekly: Decimal, estimate_weekly: Decimal) -> Decimal:
    """How far the current rent sits from the estimate, in percent, one decimal."""
    change = (current_weekly - estimate_weekly) / estimate_weekly * 100
    return change.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
