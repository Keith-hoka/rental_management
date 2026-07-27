import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.db import Base, get_session
from app.main import app


@pytest.fixture(autouse=True)
def disable_real_email(monkeypatch):
    """Route send_email onto its log-stub branch so tests never call Resend.

    Tests that specifically exercise the Resend branch set their own key,
    which overrides this within the test.
    """
    monkeypatch.setattr(settings, "resend_api_key", None)


@pytest.fixture
async def engine():
    engine = create_async_engine(settings.test_database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(engine):
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session


@pytest.fixture
async def client(engine):
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def override():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_session] = override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


FAKE_AUDIT = {
    "id": "00000000-0000-0000-0000-000000000000",
    "jurisdiction": "NSW",
    "as_at": "2026-07-27",
    "engine_version": "1.0.0",
    "client_ref": None,
    "findings": [
        {
            "rule_id": "nsw.bond_max_4_weeks",
            "verdict": "green",
            "summary": "Bond ok.",
            "evidence": {},
            "citations": [],
            "skip_reason": None,
        }
    ],
    "created_at": "2026-07-27T00:00:00Z",
}


@pytest.fixture
def compliance_on(monkeypatch):
    """Enable the compliance integration with fake endpoint settings."""
    monkeypatch.setattr(settings, "compliance_api_url", "http://localhost:8100")
    monkeypatch.setattr(settings, "compliance_api_key", "dev-key")


@pytest.fixture
def fake_create(monkeypatch):
    """Fake the compliance create_audit call with a fresh audit id per call."""
    import uuid

    async def _fake(payload):
        body = dict(FAKE_AUDIT)
        body["id"] = str(uuid.uuid4())
        body["client_ref"] = payload["client_ref"]
        return body

    monkeypatch.setattr("app.services.compliance.create_audit", _fake)
