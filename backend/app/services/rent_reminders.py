from datetime import date

DUE_SOON = "due_soon"
DUE_SOON_LEAD = 3
OVERDUE_THRESHOLDS = [7, 14, 30]


def _due_soon(days_until: int) -> bool:
    """True from DUE_SOON_LEAD days before the due date through the due date itself."""
    return 0 <= days_until <= DUE_SOON_LEAD


def _overdue_kind(days_overdue: int) -> str | None:
    """The largest overdue threshold reached, or None below the first one.

    Largest-reached rather than smallest-crossed keeps the job self-healing: after a
    missed run, a charge 16 days overdue still gets overdue_14 instead of stalling.
    """
    reached = [t for t in OVERDUE_THRESHOLDS if t <= days_overdue]
    return f"overdue_{max(reached)}" if reached else None


def _kind(due_date: date, today: date) -> str | None:
    """The reminder kind a charge qualifies for today, if any."""
    days_until = (due_date - today).days
    if days_until >= 0:
        return DUE_SOON if _due_soon(days_until) else None
    return _overdue_kind(-days_until)
