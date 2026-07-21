import pytest

from app.services.reminders import _bucket

THRESHOLDS = [60, 30, 7]


@pytest.mark.parametrize(
    ("days_left", "expected"),
    [
        (61, None),
        (60, 60),
        (45, 60),
        (31, 60),
        (30, 30),
        (8, 30),
        (7, 7),
        (0, 7),
        (-1, None),
    ],
)
def test_bucket(days_left, expected):
    assert _bucket(days_left, THRESHOLDS) == expected
