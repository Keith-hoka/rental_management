import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.deps import get_current_user
from app.core.uploads import delete_document_file, save_document
from app.models import Document, DocumentCategory, DocumentVersion, LeaseTenant, Membership, User
from app.routers.leases import get_owned_lease, manager
from app.schemas.document import DocumentInfo, DocumentVersionInfo
from app.services.notify import lease_tenant_user_ids, notify_users

router = APIRouter(prefix="/api/v1", tags=["documents"])


def _version_info(version: DocumentVersion) -> DocumentVersionInfo:
    return DocumentVersionInfo(
        id=version.id,
        version_number=version.version_number,
        original_filename=version.original_filename,
        content_type=version.content_type,
        size_bytes=version.size_bytes,
        created_at=version.created_at,
    )


async def _document_info(session: AsyncSession, document: Document) -> DocumentInfo:
    versions = (
        (
            await session.execute(
                select(DocumentVersion)
                .where(DocumentVersion.document_id == document.id)
                .order_by(DocumentVersion.version_number.desc())
            )
        )
        .scalars()
        .all()
    )
    return DocumentInfo(
        id=document.id,
        title=document.title,
        category=document.category,
        version_count=len(versions),
        current_version=_version_info(versions[0]),
        created_at=document.created_at,
    )


async def get_owned_document(
    document_id: uuid.UUID, membership: Membership, session: AsyncSession
) -> Document:
    """A document in the caller's organization, or 404."""
    document = (
        await session.execute(
            select(Document).where(
                Document.id == document_id,
                Document.organization_id == membership.organization_id,
            )
        )
    ).scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


async def _add_version(
    session: AsyncSession, document: Document, file: UploadFile, uploaded_by: uuid.UUID
) -> DocumentVersion:
    stored_name, size = await save_document(file)
    highest = (
        await session.execute(
            select(func.coalesce(func.max(DocumentVersion.version_number), 0)).where(
                DocumentVersion.document_id == document.id
            )
        )
    ).scalar_one()
    version = DocumentVersion(
        document_id=document.id,
        version_number=highest + 1,
        stored_name=stored_name,
        original_filename=file.filename or "document",
        content_type=file.content_type or "application/octet-stream",
        size_bytes=size,
        uploaded_by=uploaded_by,
    )
    session.add(version)
    return version


async def _notify_document_upload(session: AsyncSession, document: Document, title: str) -> None:
    tenant_ids = await lease_tenant_user_ids(session, document.lease_id)
    await notify_users(
        session,
        tenant_ids,
        document.organization_id,
        "document_uploaded",
        "Document shared",
        f"{title} was added to your lease.",
        f"/app/leases/{document.lease_id}",
    )


@router.post("/leases/{lease_id}/documents", status_code=201, response_model=DocumentInfo)
async def create_document(
    lease_id: uuid.UUID,
    title: str = Form(...),
    category: DocumentCategory = Form(...),
    file: UploadFile = File(...),
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> DocumentInfo:
    """Create a document on a lease with its first version, and tell the tenant."""
    lease = await get_owned_lease(lease_id, membership, session)
    document = Document(
        organization_id=lease.organization_id,
        lease_id=lease.id,
        title=title,
        category=category,
        created_by=membership.user_id,
    )
    session.add(document)
    await session.flush()
    await _add_version(session, document, file, membership.user_id)
    await _notify_document_upload(session, document, title)
    await session.commit()
    return await _document_info(session, document)


@router.post("/documents/{document_id}/versions", status_code=201, response_model=DocumentInfo)
async def add_version(
    document_id: uuid.UUID,
    file: UploadFile = File(...),
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> DocumentInfo:
    """Upload a new version of an existing document, and tell the tenant."""
    document = await get_owned_document(document_id, membership, session)
    await _add_version(session, document, file, membership.user_id)
    await _notify_document_upload(session, document, document.title)
    await session.commit()
    return await _document_info(session, document)


@router.get("/leases/{lease_id}/documents", response_model=list[DocumentInfo])
async def list_documents(
    lease_id: uuid.UUID,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> list[DocumentInfo]:
    """The documents on a lease in the caller's organization, newest first."""
    await get_owned_lease(lease_id, membership, session)
    documents = (
        (
            await session.execute(
                select(Document)
                .where(Document.lease_id == lease_id)
                .order_by(Document.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [await _document_info(session, d) for d in documents]


@router.get("/documents/{document_id}/versions", response_model=list[DocumentVersionInfo])
async def list_versions(
    document_id: uuid.UUID,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> list[DocumentVersionInfo]:
    """Every version of a document, newest first."""
    document = await get_owned_document(document_id, membership, session)
    versions = (
        (
            await session.execute(
                select(DocumentVersion)
                .where(DocumentVersion.document_id == document.id)
                .order_by(DocumentVersion.version_number.desc())
            )
        )
        .scalars()
        .all()
    )
    return [_version_info(v) for v in versions]


@router.delete("/documents/{document_id}", status_code=204)
async def delete_document(
    document_id: uuid.UUID,
    membership: Membership = Depends(manager),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Delete a document, all its versions, and their files."""
    document = await get_owned_document(document_id, membership, session)
    versions = (
        (
            await session.execute(
                select(DocumentVersion).where(DocumentVersion.document_id == document.id)
            )
        )
        .scalars()
        .all()
    )
    for version in versions:
        delete_document_file(version.stored_name)
        await session.delete(version)
    # Flush the version deletes before removing the document: there is no ORM
    # relationship to order them, so the FK would otherwise be violated.
    await session.flush()
    await session.delete(document)
    await session.commit()
    return Response(status_code=204)


async def _tenant_lease_or_404(lease_id: uuid.UUID, user: User, session: AsyncSession) -> None:
    """Raise 404 unless the caller is a tenant of the lease."""
    owned = (
        await session.execute(
            select(LeaseTenant.id).where(
                LeaseTenant.lease_id == lease_id, LeaseTenant.user_id == user.id
            )
        )
    ).first()
    if owned is None:
        raise HTTPException(status_code=404, detail="Lease not found")


@router.get("/me/leases/{lease_id}/documents", response_model=list[DocumentInfo])
async def list_my_documents(
    lease_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[DocumentInfo]:
    """The documents on a lease the caller is a tenant of."""
    await _tenant_lease_or_404(lease_id, user, session)
    documents = (
        (
            await session.execute(
                select(Document)
                .where(Document.lease_id == lease_id)
                .order_by(Document.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [await _document_info(session, d) for d in documents]
