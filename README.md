# Rental Management App

Two-sided rental management SaaS: landlords and property managers run
properties, leases, rent, and maintenance; tenants pay and file requests.

- Backend: FastAPI + PostgreSQL (`backend/`)
- Frontend: Next.js (`frontend/`)
- Docs: `docs/superpowers/specs/` (design), `docs/superpowers/plans/` (plans)

## Development

    docker compose up -d          # Postgres
    cd backend && uv run uvicorn app.main:app --reload
    cd frontend && npm run dev
