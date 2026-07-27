from app.core.config import settings
from app.services.compliance import enabled


def test_disabled_by_default():
    assert enabled() is False


def test_enabled_needs_both_values(monkeypatch):
    monkeypatch.setattr(settings, "compliance_api_url", "http://localhost:8100")
    assert enabled() is False
    monkeypatch.setattr(settings, "compliance_api_key", "dev-key")
    assert enabled() is True
