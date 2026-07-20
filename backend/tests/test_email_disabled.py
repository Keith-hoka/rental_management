from app.core.config import settings


def test_email_is_disabled_during_tests():
    """An autouse conftest fixture must keep the suite off the real Resend API."""
    assert not settings.resend_api_key
