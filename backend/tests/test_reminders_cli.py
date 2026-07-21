from contextlib import asynccontextmanager

from app.jobs import expiry_reminders


async def test_main_prints_count(monkeypatch, capsys):
    @asynccontextmanager
    async def fake_sessionmaker():
        yield object()

    async def fake_run(session, today):
        return 3

    monkeypatch.setattr(expiry_reminders, "SessionLocal", lambda: fake_sessionmaker())
    monkeypatch.setattr(expiry_reminders, "run_expiry_reminders", fake_run)

    await expiry_reminders._main()

    assert "expiry reminders: sent 3" in capsys.readouterr().out
