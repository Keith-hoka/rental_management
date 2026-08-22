from decimal import Decimal

from app.models import LeaseFrequency
from app.services.rent_math import weekly_rent


def test_weekly_rent_conversions_round_to_whole_dollars():
    assert weekly_rent(Decimal(600), LeaseFrequency.weekly) == Decimal(600)
    assert weekly_rent(Decimal(1200), LeaseFrequency.fortnightly) == Decimal(600)
    assert weekly_rent(Decimal(1500), LeaseFrequency.monthly) == Decimal(346)
    assert weekly_rent(Decimal(2610), LeaseFrequency.monthly) == Decimal(602)
