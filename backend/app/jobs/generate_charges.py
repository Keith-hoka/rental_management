import asyncio
from datetime import UTC, datetime

from app.core.db import SessionLocal
from app.services.charges import generate_charges


async def _main() -> None:
    async with SessionLocal() as session:
        count = await generate_charges(session, datetime.now(UTC).date())
    print(f"rent charges: generated {count}")


if __name__ == "__main__":
    asyncio.run(_main())
