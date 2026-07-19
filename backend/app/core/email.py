import logging

logger = logging.getLogger(__name__)


def send_email(to: str, subject: str, body: str) -> None:
    """Development email sender: logs instead of sending.

    Replaced by a real provider (e.g. Resend) at deployment.
    """
    logger.info("EMAIL to=%s subject=%s body=%s", to, subject, body)
