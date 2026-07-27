"""Client, mapper and jobs for the lease-compliance-service integration."""

import httpx

from app.core.config import settings

TIMEOUT = 10.0


def enabled() -> bool:
    """True when the compliance integration is configured."""
    return bool(settings.compliance_api_url and settings.compliance_api_key)


def _headers() -> dict:
    return {"X-API-Key": settings.compliance_api_key}


async def create_audit(payload: dict) -> dict:
    """POST an audit to the compliance service and return its body."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.post(
            f"{settings.compliance_api_url}/v1/audits", json=payload, headers=_headers()
        )
        response.raise_for_status()
        return response.json()


async def get_audit(audit_id: str) -> dict:
    """Fetch one audit by the compliance service's audit id."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(
            f"{settings.compliance_api_url}/v1/audits/{audit_id}", headers=_headers()
        )
        response.raise_for_status()
        return response.json()


async def list_changes(since: str | None, limit: int = 100) -> list[dict]:
    """One page of the tenant's audit-changes feed, ascending."""
    params: dict = {"limit": limit}
    if since is not None:
        params["since"] = since
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(
            f"{settings.compliance_api_url}/v1/audit-changes",
            params=params,
            headers=_headers(),
        )
        response.raise_for_status()
        return response.json()
