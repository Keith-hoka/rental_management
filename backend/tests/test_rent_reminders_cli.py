from contextlib import asynccontextmanager

from app.jobs import rent_reminders as cli


async def test_main_prints_count(monkeypatch, capsys):
    @asynccontextmanager
    async def fake_sessionmaker():
        yield object()

    async def fake_run(session, today):
        return 4

    monkeypatch.setattr(cli, "SessionLocal", lambda: fake_sessionmaker())
    monkeypatch.setattr(cli, "run_rent_reminders", fake_run)

    await cli._main()

    assert "rent reminders: sent 4" in capsys.readouterr().out
