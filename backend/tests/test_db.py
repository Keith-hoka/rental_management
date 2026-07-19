from sqlalchemy import text


async def test_database_connects(db_session):
    result = await db_session.execute(text("SELECT 1"))
    assert result.scalar() == 1
