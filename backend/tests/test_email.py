from app.core.config import settings
from app.core.email import send_email

SIGNUP = {
    "email": "emaillink@example.com",
    "password": "secret123",
    "name": "Keith",
    "organization_name": "Keith Properties",
}


async def test_forgot_password_sends_reset_link(client, monkeypatch):
    sent = {}

    async def fake_send(to: str, subject: str, html: str) -> None:
        sent["to"] = to
        sent["html"] = html

    monkeypatch.setattr("app.routers.auth.send_email", fake_send)

    await client.post("/api/v1/auth/signup", json=SIGNUP)
    response = await client.post("/api/v1/auth/forgot-password", json={"email": SIGNUP["email"]})

    assert response.status_code == 202
    assert sent["to"] == SIGNUP["email"]
    assert "/reset-password?token=" in sent["html"]


async def test_send_email_posts_to_resend_when_configured(monkeypatch):
    calls = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

    async def fake_post(self, url, **kwargs):
        calls["url"] = url
        calls["json"] = kwargs.get("json")
        calls["headers"] = kwargs.get("headers")
        return FakeResponse()

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)
    monkeypatch.setattr(settings, "resend_api_key", "test-key")

    await send_email("a@b.com", "Subject", "<p>hi</p>")

    assert calls["url"] == "https://api.resend.com/emails"
    assert calls["json"]["to"] == ["a@b.com"]
    assert "Bearer test-key" in calls["headers"]["Authorization"]


async def test_send_email_stub_when_no_key(monkeypatch):
    monkeypatch.setattr(settings, "resend_api_key", "")

    async def fail_post(self, url, **kwargs):
        raise AssertionError("should not call Resend without an API key")

    monkeypatch.setattr("httpx.AsyncClient.post", fail_post)

    await send_email("a@b.com", "Subject", "<p>hi</p>")
