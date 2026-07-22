from datetime import date, timedelta

import pytest

from app.services.rent_reminders import _due_soon, _kind, _overdue_kind


@pytest.mark.parametrize(
    ("days_until", "expected"),
    [(-1, False), (0, True), (1, True), (3, True), (4, False)],
)
def test_due_soon(days_until, expected):
    assert _due_soon(days_until) is expected


@pytest.mark.parametrize(
    ("days_overdue", "expected"),
    [
        (0, None),
        (6, None),
        (7, "overdue_7"),
        (13, "overdue_7"),
        (14, "overdue_14"),
        (29, "overdue_14"),
        (30, "overdue_30"),
        (45, "overdue_30"),
    ],
)
def test_overdue_kind(days_overdue, expected):
    assert _overdue_kind(days_overdue) == expected


@pytest.mark.parametrize(
    ("offset", "expected"),
    [
        (4, None),
        (3, "due_soon"),
        (0, "due_soon"),
        (-6, None),
        (-7, "overdue_7"),
        (-30, "overdue_30"),
    ],
)
def test_kind_from_dates(offset, expected):
    today = date(2026, 6, 15)
    assert _kind(today + timedelta(days=offset), today) == expected
