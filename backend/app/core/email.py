import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

RESEND_ENDPOINT = "https://api.resend.com/emails"


async def send_email(to: str, subject: str, html: str) -> None:
    """Send an email via Resend when configured, otherwise log it (development)."""
    if not settings.resend_api_key:
        logger.info("EMAIL (stub) to=%s subject=%s body=%s", to, subject, html)
        return

    async with httpx.AsyncClient() as client:
        response = await client.post(
            RESEND_ENDPOINT,
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json={"from": settings.email_from, "to": [to], "subject": subject, "html": html},
        )
        response.raise_for_status()
