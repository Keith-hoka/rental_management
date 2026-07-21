from datetime import date
from decimal import Decimal

from app.models import Charge
from app.services.payments import allocate, summarize

TODAY = date(2026, 6, 1)


def _charge(due, amount):
    return Charge(period_start=due, period_end=due, due_date=due, amount_due=Decimal(amount))


def test_exact_payment_marks_paid():
    st = allocate([_charge(date(2026, 1, 1), 1000)], Decimal(1000), TODAY)
    assert st[0].status == "paid"
    assert st[0].amount_paid == Decimal(1000)
    assert st[0].overdue is False


def test_partial_payment_is_overdue_when_past_due():
    st = allocate([_charge(date(2026, 1, 1), 1000)], Decimal(400), TODAY)
    assert st[0].status == "partial"
    assert st[0].amount_paid == Decimal(400)
    assert st[0].overdue is True


def test_waterfall_across_three():
    charges = [
        _charge(date(2026, 1, 1), 1000),
        _charge(date(2026, 2, 1), 1000),
        _charge(date(2026, 3, 1), 1000),
    ]
    by_due = {s.charge.due_date: s for s in allocate(charges, Decimal(1500), TODAY)}
    assert by_due[date(2026, 1, 1)].status == "paid"
    assert by_due[date(2026, 2, 1)].status == "partial"
    assert by_due[date(2026, 2, 1)].amount_paid == Decimal(500)
    assert by_due[date(2026, 3, 1)].status == "unpaid"


def test_overpay_leaves_credit():
    st = allocate([_charge(date(2026, 1, 1), 1000)], Decimal(1500), TODAY)
    bal = summarize(st, Decimal(1500), TODAY)
    assert st[0].status == "paid"
    assert bal.credit == Decimal(500)
    assert bal.outstanding == Decimal(0)


def test_summarize_outstanding_and_overdue():
    charges = [
        _charge(date(2026, 1, 1), 1000),  # past due
        _charge(date(2026, 6, 1), 1000),  # due today
        _charge(date(2026, 12, 1), 1000),  # upcoming
    ]
    st = allocate(charges, Decimal(0), TODAY)
    bal = summarize(st, Decimal(0), TODAY)
    assert bal.outstanding == Decimal(2000)  # Jan + Jun (due_date <= today)
    assert bal.overdue_amount == Decimal(1000)  # only Jan (< today)
    assert bal.credit == Decimal(0)
