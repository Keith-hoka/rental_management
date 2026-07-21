import asyncio
from datetime import UTC, datetime

from app.core.db import SessionLocal
from app.services.reminders import run_expiry_reminders


async def _main() -> None:
    async with SessionLocal() as session:
        count = await run_expiry_reminders(session, datetime.now(UTC).date())
    print(f"expiry reminders: sent {count}")


if __name__ == "__main__":
    asyncio.run(_main())
