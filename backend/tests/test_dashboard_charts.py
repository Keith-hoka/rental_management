import uuid
from dataclasses import dataclass
from datetime import date

from dateutil.relativedelta import relativedelta

from app.services.stats import dashboard_stats, occupancy_series
from tests.test_portal import make_lease, onboard_tenant
from tests.test_properties_crud import landlord_headers
from tests.test_stats import _org_id


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

    series = occupancy_series(leases, {prop: date(2026, 1, 1)}, MONTHS)

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
    series = occupancy_series(
        [], {uuid.uuid4(): date(2026, 1, 1), uuid.uuid4(): date(2026, 6, 15)}, MONTHS
    )

    assert [(p.month, p.total) for p in series] == [
        ("2026-02", 1),
        ("2026-03", 1),
        ("2026-04", 1),
        ("2026-05", 1),
        ("2026-06", 2),
        ("2026-07", 2),
    ]


def test_zero_properties_gives_zero_rate_not_a_crash():
    series = occupancy_series([], {}, MONTHS)

    assert [p.rate for p in series] == [0.0] * 6
    assert [p.total for p in series] == [0] * 6


def test_rate_is_rounded_to_one_decimal_place():
    ids = [uuid.uuid4() for _ in range(7)]
    props = {pid: date(2026, 1, 1) for pid in ids}
    occupied = [FakeLease(pid, date(2026, 1, 1), date(2026, 12, 31)) for pid in ids[:3]]

    series = occupancy_series(occupied, props, MONTHS)

    # 3/7 is 42.857142857142854 unrounded, which is what a tooltip would print.
    assert series[0].rate == 42.9


def test_backdated_lease_counts_its_property_in_the_denominator():
    """A property recorded today can carry a lease that started long before.

    That is the normal onboarding path -- a landlord enters an existing tenancy
    on their first day -- and counting it in the numerator while excluding it
    from the denominator produced "1 of 0" and a flat 0% for every earlier month.
    """
    prop = uuid.uuid4()
    leases = [FakeLease(prop, date(2026, 1, 1), date(2026, 12, 31))]

    # The row was created in July; the tenancy has run since January.
    series = occupancy_series(leases, {prop: date(2026, 7, 20)}, MONTHS)

    assert [(p.occupied, p.total) for p in series] == [(1, 1)] * 6
    assert all(p.rate == 100.0 for p in series)


REQ = {"title": "Tap", "description": "Drips", "priority": "low"}


async def _report(client, tenant_headers, lease_id):
    return (
        await client.post(
            f"/api/v1/me/leases/{lease_id}/maintenance", json=REQ, headers=tenant_headers
        )
    ).json()["id"]


async def test_counts_every_status_including_the_empty_ones(client, db_session):
    email = "mstat@example.com"
    headers = await landlord_headers(client, email)
    org_id = await _org_id(db_session, email)
    lease_id = await make_lease(client, headers, "1 Status St")
    tenant = await onboard_tenant(client, db_session, headers, lease_id, "mstat-t@example.com")
    first = await _report(client, tenant, lease_id)
    await _report(client, tenant, lease_id)
    await client.patch(f"/api/v1/maintenance/{first}", json={"status": "resolved"}, headers=headers)

    stats = await dashboard_stats(db_session, org_id, date.today())
    counts = {c.status: c.count for c in stats.maintenance_by_status}

    assert counts["open"] == 1
    assert counts["resolved"] == 1
    # Absent statuses report zero rather than vanishing, so the legend is stable.
    assert counts["in_progress"] == 0
    assert counts["cancelled"] == 0


async def test_requests_older_than_the_window_are_excluded(client, db_session):
    email = "mold@example.com"
    headers = await landlord_headers(client, email)
    org_id = await _org_id(db_session, email)
    lease_id = await make_lease(client, headers, "1 Old St")
    tenant = await onboard_tenant(client, db_session, headers, lease_id, "mold-t@example.com")
    await _report(client, tenant, lease_id)

    # Seven months on, the same request has fallen out of the six-month window.
    future = date.today() + relativedelta(months=7)
    stats = await dashboard_stats(db_session, org_id, future)

    assert sum(c.count for c in stats.maintenance_by_status) == 0
