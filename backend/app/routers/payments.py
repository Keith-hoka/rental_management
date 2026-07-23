import csv
import io
import uuid
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.models import Lease, Membership, Payment, Property
from app.routers.leases import get_owned_lease, manager
from app.schemas.payment import BalanceInfo, PaymentCreate, PaymentInfo, RecentPayment
from app.services.payments import lease_balance

router = APIRouter(prefix="/api/v1", tags=["payments"])


@router.get("/payments/recent", response_model=list[RecentPayment])
async def recent_payments(
    limit: int = 10,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> list[RecentPayment]:
    """The organization's most recent payments, newest first."""
    result = await session.execute(
        select(Payment, Property.address, Lease.tenant_name)
        .join(Lease, Lease.id == Payment.lease_id)
        .join(Property, Property.id == Lease.property_id)
        .where(Payment.organization_id == membership.organization_id)
        .order_by(Payment.paid_on.desc(), Payment.created_at.desc())
        .limit(limit)
    )
    return [
        RecentPayment(
            id=payment.id,
            amount=payment.amount,
            paid_on=payment.paid_on,
            method=payment.method,
            property_address=address,
            tenant_name=tenant_name,
        )
        for payment, address, tenant_name in result.all()
    ]


@router.get("/payments/export")
async def export_payments(
    start: date | None = None,
    end: date | None = None,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """The organization's payments as CSV, optionally within an inclusive date range."""
    query = (
        select(Payment, Property.address, Lease.tenant_name)
        .join(Lease, Lease.id == Payment.lease_id)
        .join(Property, Property.id == Lease.property_id)
        .where(Payment.organization_id == membership.organization_id)
    )
    if start is not None:
        query = query.where(Payment.paid_on >= start)
    if end is not None:
        query = query.where(Payment.paid_on <= end)
    query = query.order_by(Payment.paid_on.asc(), Property.address.asc())
    rows = (await session.execute(query)).all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["paid_on", "property_address", "tenant_name", "method", "amount", "note"])
    for payment, address, tenant_name in rows:
        writer.writerow(
            [
                payment.paid_on,
                address,
                tenant_name,
                payment.method.value,
                payment.amount,
                payment.note or "",
            ]
        )

    today = datetime.now(UTC).date()
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="payments-{today}.csv"'},
    )


@router.post("/leases/{lease_id}/payments", status_code=201, response_model=PaymentInfo)
async def record_payment(
    lease_id: uuid.UUID,
    body: PaymentCreate,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> PaymentInfo:
    """Record a payment against a lease in the caller's organization."""
    lease = await get_owned_lease(lease_id, membership, session)
    payment = Payment(
        organization_id=lease.organization_id,
        lease_id=lease.id,
        amount=body.amount,
        paid_on=body.paid_on,
        method=body.method,
        note=body.note,
    )
    session.add(payment)
    await session.commit()
    await session.refresh(payment)
    return PaymentInfo(
        id=payment.id,
        amount=payment.amount,
        paid_on=payment.paid_on,
        method=payment.method,
        note=payment.note,
    )


@router.get("/leases/{lease_id}/payments", response_model=list[PaymentInfo])
async def list_payments(
    lease_id: uuid.UUID,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> list[PaymentInfo]:
    """List a lease's payments, newest first."""
    await get_owned_lease(lease_id, membership, session)
    result = await session.execute(
        select(Payment)
        .where(Payment.lease_id == lease_id)
        .order_by(Payment.paid_on.desc(), Payment.created_at.desc())
    )
    return [
        PaymentInfo(id=p.id, amount=p.amount, paid_on=p.paid_on, method=p.method, note=p.note)
        for p in result.scalars().all()
    ]


@router.delete("/leases/{lease_id}/payments/{payment_id}", status_code=204)
async def delete_payment(
    lease_id: uuid.UUID,
    payment_id: uuid.UUID,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Delete a payment on a lease in the caller's organization."""
    await get_owned_lease(lease_id, membership, session)
    payment = (
        await session.execute(
            select(Payment).where(Payment.id == payment_id, Payment.lease_id == lease_id)
        )
    ).scalar_one_or_none()
    if payment is None:
        raise HTTPException(status_code=404, detail="Payment not found")
    await session.delete(payment)
    await session.commit()
    return Response(status_code=204)


@router.get("/leases/{lease_id}/balance", response_model=BalanceInfo)
async def get_balance(
    lease_id: uuid.UUID,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> BalanceInfo:
    """Outstanding / overdue / credit summary for a lease in the caller's organization."""
    await get_owned_lease(lease_id, membership, session)
    balance = await lease_balance(session, lease_id, datetime.now(UTC).date())
    return BalanceInfo(
        outstanding=balance.outstanding,
        overdue_amount=balance.overdue_amount,
        credit=balance.credit,
    )
