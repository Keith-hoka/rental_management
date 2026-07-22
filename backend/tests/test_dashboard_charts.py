import uuid
from dataclasses import dataclass
from datetime import date

from app.services.stats import occupancy_series


@dataclass
class FakeLease:
    """Only the three fields occupancy_series reads."""

    property_id: uuid.UUID
    start_date: date
    end_date: date


MONTHS = [date(2026, m, 1) for m in (2, 3, 4, 5, 6, 7)]


def test_lease_covering_part_of_the_window_marks_only_those_months():
    prop = uuid.uuid4()
    leases = [FakeLease(prop, date(2026, 4, 10), date(2026, 5, 20))]

    series = occupancy_series(leases, [date(2026, 1, 1)], MONTHS)

    assert [(p.month, p.occupied) for p in series] == [
        ("2026-02", 0),
        ("2026-03", 0),
        ("2026-04", 1),
        ("2026-05", 1),
        ("2026-06", 0),
        ("2026-07", 0),
    ]
    assert all(p.total == 1 for p in series)


def test_property_created_mid_window_is_not_in_earlier_denominators():
    """The denominator must be the properties that existed then, not today's count.

    Every other test still passes if this is got wrong, so it needs its own.
    """
    series = occupancy_series([], [date(2026, 1, 1), date(2026, 6, 15)], MONTHS)

    assert [(p.month, p.total) for p in series] == [
        ("2026-02", 1),
        ("2026-03", 1),
        ("2026-04", 1),
        ("2026-05", 1),
        ("2026-06", 2),
        ("2026-07", 2),
    ]


def test_zero_properties_gives_zero_rate_not_a_crash():
    series = occupancy_series([], [], MONTHS)

    assert [p.rate for p in series] == [0.0] * 6
    assert [p.total for p in series] == [0] * 6


def test_rate_is_rounded_to_one_decimal_place():
    props = [date(2026, 1, 1)] * 7
    occupied = [FakeLease(uuid.uuid4(), date(2026, 1, 1), date(2026, 12, 31)) for _ in range(3)]

    series = occupancy_series(occupied, props, MONTHS)

    # 3/7 is 42.857142857142854 unrounded, which is what a tooltip would print.
    assert series[0].rate == 42.9
