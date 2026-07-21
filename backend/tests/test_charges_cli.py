from contextlib import asynccontextmanager

from app.jobs import generate_charges as cli


async def test_main_prints_count(monkeypatch, capsys):
    @asynccontextmanager
    async def fake_sessionmaker():
        yield object()

    async def fake_generate(session, today):
        return 5

    monkeypatch.setattr(cli, "SessionLocal", lambda: fake_sessionmaker())
    monkeypatch.setattr(cli, "generate_charges", fake_generate)

    await cli._main()

    assert "rent charges: generated 5" in capsys.readouterr().out
