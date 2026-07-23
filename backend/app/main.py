import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.scheduler import scheduler, start_scheduler
from app.routers.auth import router as auth_router
from app.routers.calendar import router as calendar_router
from app.routers.contractors import router as contractors_router
from app.routers.documents import router as documents_router
from app.routers.expenses import router as expenses_router
from app.routers.invitations import router as invitations_router
from app.routers.leases import router as leases_router
from app.routers.maintenance import router as maintenance_router
from app.routers.notifications import router as notifications_router
from app.routers.payments import router as payments_router
from app.routers.portal import router as portal_router
from app.routers.properties import router as properties_router
from app.routers.rent import router as rent_router
from app.routers.search import router as search_router
from app.routers.stats import router as stats_router

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start the reminder scheduler on boot; stop it on shutdown."""
    if settings.reminders_enabled:
        start_scheduler()
    yield
    if scheduler.running:
        scheduler.shutdown(wait=False)


app = FastAPI(title="Rental Management API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router)
app.include_router(calendar_router)
app.include_router(contractors_router)
app.include_router(documents_router)
app.include_router(expenses_router)
app.include_router(properties_router)
app.include_router(rent_router)
app.include_router(invitations_router)
app.include_router(leases_router)
app.include_router(maintenance_router)
app.include_router(notifications_router)
app.include_router(payments_router)
app.include_router(portal_router)
app.include_router(search_router)
app.include_router(stats_router)

Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}
