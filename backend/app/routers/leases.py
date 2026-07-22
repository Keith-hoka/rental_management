import logging
import secrets
import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_session
from app.core.deps import require_roles
from app.core.email import send_email
from app.models import (
    Invitation,
    InvitationStatus,
    Lease,
    LeaseReminder,
    LeaseTenant,
    Membership,
    Property,
    Role,
    User,
)
from app.routers.properties import get_owned_property
from app.schemas.charge import ChargeInfo
from app.services.invites import reject_duplicate_invite
from app.services.notify import lease_tenant_user_ids, manager_user_ids, notify_users
from app.services.payments import lease_statuses
from app.schemas.invitation import InvitationResponse
from app.schemas.lease import LeaseCreate, LeaseRenew, LeaseResponse, LeaseSummary, LeaseUpdate
from app.schemas.tenant import (
    TenantDirectoryEntry,
    LeaseInvitationInfo,
    LeaseReminderInfo,
    LeaseTenantInfo,
    TenantInviteRequest,
)

router = APIRouter(prefix="/api/v1", tags=["leases"])

manager = require_roles(Role.landlord, Role.property_manager)


async def overlapping_lease_exists(
    session: AsyncSession,
    property_id: uuid.UUID,
    start_date: date,
    end_date: date,
    exclude_id: uuid.UUID | None = None,
) -> bool:
    """True if another lease on the property overlaps the given date range (inclusive)."""
    query = select(Lease.id).where(
        Lease.property_id == property_id,
        Lease.start_date <= end_date,
        start_date <= Lease.end_date,
    )
    if exclude_id is not None:
        query = query.where(Lease.id != exclude_id)
    return (await session.execute(query)).first() is not None


@router.post("/properties/{property_id}/leases", status_code=201, response_model=LeaseResponse)
async def create_lease(
    property_id: uuid.UUID,
    body: LeaseCreate,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> Lease:
    """Create a lease for a property in the caller's organization."""
    prop = await get_owned_property(property_id, membership, session)
    if body.start_date > body.end_date:
        raise HTTPException(status_code=422, detail="start_date must be on or before end_date")
    if await overlapping_lease_exists(session, property_id, body.start_date, body.end_date):
        raise HTTPException(status_code=409, detail="Lease dates overlap an existing lease")

    lease = Lease(
        organization_id=prop.organization_id, property_id=property_id, **body.model_dump()
    )
    session.add(lease)
    await session.commit()
    await session.refresh(lease)
    return lease


async def get_owned_lease(
    lease_id: uuid.UUID, membership: Membership, session: AsyncSession
) -> Lease:
    """Fetch a lease in the caller's org, or raise 404."""
    lease = (
        await session.execute(
            select(Lease).where(
                Lease.id == lease_id,
                Lease.organization_id == membership.organization_id,
            )
        )
    ).scalar_one_or_none()
    if lease is None:
        raise HTTPException(status_code=404, detail="Lease not found")
    return lease


async def successor_id(session: AsyncSession, lease_id: uuid.UUID) -> uuid.UUID | None:
    """The id of the lease that renewed this one, if it has been renewed."""
    return (
        await session.execute(select(Lease.id).where(Lease.renewed_from_id == lease_id))
    ).scalar_one_or_none()


@router.post("/leases/{lease_id}/renew", status_code=201, response_model=LeaseResponse)
async def renew_lease(
    lease_id: uuid.UUID,
    body: LeaseRenew,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> Lease:
    """Create a successor lease for the same tenants, linked back to the source."""
    source = await get_owned_lease(lease_id, membership, session)
    if await successor_id(session, lease_id) is not None:
        raise HTTPException(status_code=409, detail="Lease has already been renewed")

    start = body.start_date or source.end_date + timedelta(days=1)
    if start > body.end_date:
        raise HTTPException(status_code=422, detail="start_date must be on or before end_date")
    if await overlapping_lease_exists(session, source.property_id, start, body.end_date):
        raise HTTPException(status_code=409, detail="Lease dates overlap an existing lease")

    renewal = Lease(
        organization_id=source.organization_id,
        property_id=source.property_id,
        tenant_name=source.tenant_name,
        tenant_email=source.tenant_email,
        tenant_phone=source.tenant_phone,
        co_tenants=source.co_tenants,
        rent_amount=body.rent_amount if body.rent_amount is not None else source.rent_amount,
        rent_frequency=body.rent_frequency or source.rent_frequency,
        bond_amount=body.bond_amount if body.bond_amount is not None else source.bond_amount,
        notice_period_days=(
            body.notice_period_days
            if body.notice_period_days is not None
            else source.notice_period_days
        ),
        start_date=start,
        end_date=body.end_date,
        renewed_from_id=source.id,
    )
    session.add(renewal)
    # flush, not commit: renewal.id is needed below, but the copy and the
    # notifications must still land in the same transaction as the lease itself.
    await session.flush()

    # LeaseTenant is what GET /me/leases reads, so without this copy the tenant
    # cannot see the lease they were just renewed onto.
    for user_id in await lease_tenant_user_ids(session, source.id):
        session.add(LeaseTenant(lease_id=renewal.id, user_id=user_id))

    recipients = await manager_user_ids(session, source.organization_id)
    recipients += await lease_tenant_user_ids(session, source.id)
    await notify_users(
        session,
        recipients,
        source.organization_id,
        "lease_renewal",
        "Lease renewed",
        f"The lease for {source.tenant_name} now runs to {renewal.end_date}.",
        f"/app/leases/{renewal.id}",
    )

    await session.commit()
    await session.refresh(renewal)
    return renewal


@router.get("/properties/{property_id}/leases", response_model=list[LeaseResponse])
async def list_leases(
    property_id: uuid.UUID,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> list[Lease]:
    """List a property's leases (newest first). 404 if the property is not in the org."""
    await get_owned_property(property_id, membership, session)
    result = await session.execute(
        select(Lease).where(Lease.property_id == property_id).order_by(Lease.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/leases/{lease_id}", response_model=LeaseResponse)
async def get_lease(
    lease_id: uuid.UUID,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> LeaseResponse:
    """Fetch a single lease in the caller's organization, including its renewal link.

    Only this endpoint resolves the reverse link; the list endpoints would pay one
    extra query per lease for a value nothing renders.
    """
    lease = await get_owned_lease(lease_id, membership, session)
    response = LeaseResponse.model_validate(lease)
    response.renewed_to_id = await successor_id(session, lease_id)
    return response


@router.patch("/leases/{lease_id}", response_model=LeaseResponse)
async def update_lease(
    lease_id: uuid.UUID,
    body: LeaseUpdate,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> Lease:
    """Update a lease; re-validate date order and overlap (excluding itself)."""
    lease = await get_owned_lease(lease_id, membership, session)
    data = body.model_dump(exclude_unset=True)
    start = data.get("start_date", lease.start_date)
    end = data.get("end_date", lease.end_date)
    if start > end:
        raise HTTPException(status_code=422, detail="start_date must be on or before end_date")
    if await overlapping_lease_exists(session, lease.property_id, start, end, exclude_id=lease.id):
        raise HTTPException(status_code=409, detail="Lease dates overlap an existing lease")

    for field, value in data.items():
        setattr(lease, field, value)
    await session.commit()
    await session.refresh(lease)
    return lease


@router.delete("/leases/{lease_id}", status_code=204)
async def delete_lease(
    lease_id: uuid.UUID,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Delete a lease in the caller's organization."""
    lease = await get_owned_lease(lease_id, membership, session)
    await session.delete(lease)
    await session.commit()
    return Response(status_code=204)


def _lease_state(lease: Lease, today: date) -> str:
    if lease.start_date > today:
        return "upcoming"
    if lease.end_date < today:
        return "ended"
    return "active"


@router.get("/leases", response_model=list[LeaseSummary])
async def list_all_leases(
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> list[LeaseSummary]:
    """List every lease in the caller's organization with its property address and state."""
    today = datetime.now(UTC).date()
    result = await session.execute(
        select(Lease, Property.address)
        .join(Property, Lease.property_id == Property.id)
        .where(Lease.organization_id == membership.organization_id)
        .order_by(Lease.created_at.desc())
    )
    return [
        LeaseSummary(
            id=lease.id,
            property_id=lease.property_id,
            property_address=address,
            tenant_name=lease.tenant_name,
            rent_amount=lease.rent_amount,
            rent_frequency=lease.rent_frequency,
            start_date=lease.start_date,
            end_date=lease.end_date,
            state=_lease_state(lease, today),
        )
        for lease, address in result.all()
    ]


@router.post("/leases/{lease_id}/invite", status_code=201, response_model=InvitationResponse)
async def invite_tenant(
    lease_id: uuid.UUID,
    body: TenantInviteRequest,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> Invitation:
    """Invite a tenant (by email) to a lease in the caller's organization."""
    lease = await get_owned_lease(lease_id, membership, session)
    already = (
        await session.execute(
            select(LeaseTenant.id)
            .join(User, User.id == LeaseTenant.user_id)
            .where(LeaseTenant.lease_id == lease_id, User.email == body.email)
        )
    ).first()
    if already is not None:
        raise HTTPException(status_code=409, detail="Already a tenant of this lease")
    await reject_duplicate_invite(session, body.email, lease.organization_id, lease.id)

    invite = Invitation(
        organization_id=lease.organization_id,
        email=body.email,
        role=Role.tenant,
        lease_id=lease.id,
        token=secrets.token_urlsafe(32),
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    session.add(invite)
    await session.commit()
    await session.refresh(invite)

    accept_url = f"{settings.frontend_url}/accept-invite?token={invite.token}"
    html = (
        "<p>You have been invited as a tenant on Rental Management.</p>"
        f'<p><a href="{accept_url}">Accept the invitation</a></p>'
        "<p>This link expires in 7 days.</p>"
    )
    try:
        await send_email(invite.email, "You have been invited", html)
    except Exception:  # noqa: BLE001 - email failure must not fail the invite
        logging.getLogger(__name__).exception("Failed to send invite email to %s", invite.email)

    return invite


@router.get("/tenants", response_model=list[TenantDirectoryEntry])
async def list_tenants(
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> list[TenantDirectoryEntry]:
    """Everyone named on a lease roster in the organization, main tenants and co-tenants."""
    result = await session.execute(
        select(Lease, Property.address)
        .join(Property, Property.id == Lease.property_id)
        .where(Lease.organization_id == membership.organization_id)
        .order_by(Property.address)
    )
    rows = list(result.all())

    joined_emails = set(
        (
            await session.execute(
                select(User.email)
                .join(LeaseTenant, LeaseTenant.user_id == User.id)
                .where(LeaseTenant.lease_id.in_([lease.id for lease, _ in rows]))
            )
        )
        .scalars()
        .all()
    )

    entries: list[TenantDirectoryEntry] = []
    for lease, address in rows:
        roster = [(lease.tenant_name, lease.tenant_email, lease.tenant_phone)] + [
            (c["name"], c["email"], c.get("phone")) for c in lease.co_tenants
        ]
        for name, email, phone in roster:
            entries.append(
                TenantDirectoryEntry(
                    name=name,
                    email=email,
                    phone=phone or None,
                    property_address=address,
                    lease_id=lease.id,
                    joined=email in joined_emails,
                )
            )
    return entries


@router.get("/leases/{lease_id}/tenants", response_model=list[LeaseTenantInfo])
async def list_lease_tenants(
    lease_id: uuid.UUID,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> list[LeaseTenantInfo]:
    """List the tenants who have joined the given lease."""
    await get_owned_lease(lease_id, membership, session)
    result = await session.execute(
        select(User.name, User.email)
        .join(LeaseTenant, LeaseTenant.user_id == User.id)
        .where(LeaseTenant.lease_id == lease_id)
    )
    return [LeaseTenantInfo(name=name, email=email) for name, email in result.all()]


@router.get("/leases/{lease_id}/invitations", response_model=list[LeaseInvitationInfo])
async def list_lease_invitations(
    lease_id: uuid.UUID,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> list[LeaseInvitationInfo]:
    """List pending tenant invitations for the given lease."""
    await get_owned_lease(lease_id, membership, session)
    result = await session.execute(
        select(Invitation.id, Invitation.email)
        .where(Invitation.lease_id == lease_id, Invitation.status == InvitationStatus.pending)
        .order_by(Invitation.created_at.desc())
    )
    return [LeaseInvitationInfo(id=id_, email=email) for id_, email in result.all()]


@router.delete("/leases/{lease_id}/invitations/{invitation_id}", status_code=204)
async def revoke_lease_invitation(
    lease_id: uuid.UUID,
    invitation_id: uuid.UUID,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Revoke a pending tenant invitation for the given lease."""
    await get_owned_lease(lease_id, membership, session)
    invite = (
        await session.execute(
            select(Invitation).where(
                Invitation.id == invitation_id, Invitation.lease_id == lease_id
            )
        )
    ).scalar_one_or_none()
    if invite is None:
        raise HTTPException(status_code=404, detail="Invitation not found")
    invite.status = InvitationStatus.revoked
    await session.commit()
    return Response(status_code=204)


@router.get("/leases/{lease_id}/charges", response_model=list[ChargeInfo])
async def list_lease_charges(
    lease_id: uuid.UUID,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> list[ChargeInfo]:
    """List rent charges for the given lease with payment status, newest due date first."""
    await get_owned_lease(lease_id, membership, session)
    statuses = await lease_statuses(session, lease_id, datetime.now(UTC).date())
    statuses.reverse()  # allocate sorts ascending by due date; newest first for the response
    return [
        ChargeInfo(
            id=s.charge.id,
            period_start=s.charge.period_start,
            period_end=s.charge.period_end,
            due_date=s.charge.due_date,
            amount_due=s.charge.amount_due,
            amount_paid=s.amount_paid,
            status=s.status,
            overdue=s.overdue,
        )
        for s in statuses
    ]


@router.get("/leases/{lease_id}/reminders", response_model=list[LeaseReminderInfo])
async def list_lease_reminders(
    lease_id: uuid.UUID,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> list[LeaseReminderInfo]:
    """List expiry reminders sent for the given lease, newest first."""
    await get_owned_lease(lease_id, membership, session)
    result = await session.execute(
        select(LeaseReminder.threshold_days, LeaseReminder.sent_at)
        .where(LeaseReminder.lease_id == lease_id)
        .order_by(LeaseReminder.sent_at.desc())
    )
    return [
        LeaseReminderInfo(threshold_days=threshold, sent_at=sent_at)
        for threshold, sent_at in result.all()
    ]
