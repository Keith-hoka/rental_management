# Rental Management SaaS — Design

Date: 2026-07-19
Status: Approved pending user review

## 1. Overview

A two-sided SaaS for long-term residential rental management. Landlords and
property managers manage properties, tenants, leases, rent, and maintenance;
tenants log in to a portal to view their lease, payment history, and submit
maintenance requests.

Market: international. Currency and payment cycle (weekly / fortnightly /
monthly) are configurable per organization and per lease — no hard-coded
locale assumptions.

## 2. Tech Stack

- **Backend**: Python, FastAPI, SQLAlchemy 2.0 (async), Alembic migrations, managed with `uv`
- **Database**: PostgreSQL (Docker Compose locally, managed Postgres in prod)
- **Frontend**: Next.js (App Router, TypeScript), Tailwind CSS + shadcn/ui, TanStack Query, Recharts for charts
- **Auth**: JWT (access + refresh), Google OAuth, email-based password reset
- **Scheduler**: APScheduler inside the FastAPI process (rent charge generation, reminders)
- **Email**: provider-agnostic sender interface; SMTP in dev, a service (e.g. Resend) in prod
- **File storage**: local disk volume in MVP (property images, maintenance photos); S3-compatible storage with signed URLs in v3
- **AI features**: Claude API (post-v2)
- **Deploy**: frontend on Vercel; API + Postgres on Railway or Render

## 3. Architecture

Single FastAPI application with modular routers (`auth`, `organizations`,
`properties`, `tenants`, `leases`, `rent`, `maintenance`, `notifications`).
No microservices. Next.js SPA-style frontend (mostly client components)
calling the API through one shared typed client.

### Multi-tenancy (day 1, not v3)

Every domain record carries `organization_id`. Every query is scoped through
the authenticated user's organization membership. One database, row-level
scoping enforced in a shared dependency — no schema-per-tenant. v3 adds
enterprise management on top (teams, audit log, analytics), not isolation
itself.

### Roles and access (RBAC)

Three roles, stored on the user's organization membership:

| Role | Access |
|---|---|
| `landlord` | Org owner. Everything, including org settings and member management. |
| `property_manager` | Manage properties, tenants, leases, rent, maintenance. Cannot delete the org or manage members. |
| `tenant` | Own lease(s) only: view lease and payment history, submit/track maintenance requests. |

Tenants never sign up openly — they join via an email invitation tied to a
lease. This links tenant identity to lease data safely.

### Frontend route trees

- `/app/*` — landlord / property-manager dashboard
- `/portal/*` — tenant portal
- One codebase, shared API client and UI components. Route guards by role.

## 4. Data Model

```
Organization (currency code, name, settings)
 ├─ Membership (user_id, org_id, role)          — User is global; role lives here
 ├─ Property (address, type, bedrooms, bathrooms, parking, images,
 │            description, status: occupied/vacant)
 │   └─ Lease (property_id, tenant_user_id, start_date, end_date,
 │             rent_amount, payment_cycle: weekly/fortnightly/monthly,
 │             bond_amount, notice_period_days, status: active/ended/pending_renewal)
 │       ├─ RentCharge (due_date, amount, status: due/paid/late/partial)
 │       │   └─ Payment (amount, paid_date, method, notes;
 │       │              stripe_payment_id in v3)
 │       └─ MaintenanceRequest (title, description, priority, images[],
 │                              status: open/assigned/in_progress/completed,
 │                              contractor_name, comments[])
 ├─ TenantProfile (user_id, phone, emergency_contact, documents[])
 ├─ Notification (user_id, type, payload, read_at, created_at)
 └─ Document (v2: owner refs, file, version, type)
```

Key decisions:

- **No separate Unit table.** A property is the rentable unit. A multi-unit
  building is multiple property records (can share an address). Simplest
  model that fits the confirmed feature set; revisit only if real demand
  appears.
- **Lease owns lease data.** Rent, start/end, bond, notice period live on
  Lease, not Property. Property lists display them via the active lease.
- **RentCharge vs Payment split.** "What is owed" and "what was received"
  are separate records: supports partial payment, late detection, and later
  Stripe integration without model changes.
- **RentCharge generation.** A daily APScheduler job creates upcoming
  charges from active leases according to `payment_cycle`, and flips
  `due → late` past the due date.

## 5. Feature Phasing

### Phase 1 — MVP (all confirmed in scope)

1. **Authentication**: signup, login, Google OAuth, forgot password, JWT, RBAC (3 roles)
2. **Dashboard**: stat cards (properties, occupied/vacant, monthly income, upcoming rent, pending maintenance) + charts (monthly income, occupancy rate, maintenance status)
3. **Property management**: CRUD, search, filter, images
4. **Tenant management**: profile, invite/assign to property (via lease), end lease, payment history
5. **Lease management**: CRUD, expiry reminders, renewal flow (create successor lease)
6. **Rent tracking**: auto-generated charges, manual payment recording, overdue/upcoming views, outstanding balance
7. **Maintenance requests**: tenant submits with photos + priority; landlord assigns contractor, updates status
8. **Notifications**: in-app + email (rent due, lease expiring, maintenance assigned), driven by scheduler

### Phase 2 — SaaS depth

Document management (PDF preview, versions), inspections (rooms, photos,
notes), payment history export (CSV), full-text search, calendar view
(lease expiry / inspections / rent due / maintenance), monthly reports
(income, expenses, vacancy, ROI; PDF export).

### Phase 3 — AI features (differentiator, Claude API)

Priority order:
1. **AI Maintenance Assistant** — classify request, priority, cost estimate, contractor suggestion
2. **AI Lease Summary** — PDF extraction into structured lease fields
3. **AI Chatbot** — natural-language queries over org data ("who hasn't paid?")
4. **AI Email Generator** — draft reminders/notices for landlord approval
5. **AI Maintenance Image Analysis** — vision on uploaded photos
6. **AI Document OCR** — ID extraction (last: highest privacy sensitivity)

### Phase 4 — Enterprise

Stripe rent payment (ACH/card), audit log, finer-grained permissions
(admin/manager/staff), S3 + signed URLs, analytics (retention, maintenance
cost, average rent), subscription billing for landlords.

## 6. API Design

REST, JSON, versioned under `/api/v1`. Representative resources:

```
POST   /auth/signup | /auth/login | /auth/google | /auth/forgot-password
GET    /dashboard/summary
CRUD   /properties            (+ ?search= & filters)
CRUD   /tenants               (invite: POST /tenants/{id}/invite)
CRUD   /leases                (renew: POST /leases/{id}/renew)
GET    /rent/charges          (?status=overdue|upcoming)
POST   /rent/charges/{id}/payments
CRUD   /maintenance-requests  (tenant-scoped vs org-scoped by role)
GET    /notifications         (+ mark read)
```

All org-scoped endpoints resolve the org from the authenticated membership —
never from a client-supplied org id.

## 7. Error Handling

- FastAPI exception handlers map domain errors to consistent JSON
  (`{"detail": ...}`) with correct status codes (401/403/404/409/422).
- Frontend: TanStack Query error boundaries + toast notifications.
- Scheduler jobs log failures and continue; a failed reminder never blocks
  charge generation.
- No defensive programming beyond real failure points (per project style).

## 8. Testing

- **Backend**: pytest + httpx async client against a real Postgres
  (dockerized) — unit tests for charge-generation and RBAC logic,
  API tests per router. TDD per project convention.
- **Frontend**: Playwright for the critical flows (login, create property,
  invite tenant, record payment, submit maintenance request).
- **RBAC tests are mandatory**: every org-scoped endpoint gets a
  cross-org-access-denied test and a role-permission test.

## 9. Repository Layout

```
rental_management_app/
├─ backend/          # FastAPI app (uv project)
│  ├─ app/
│  │  ├─ routers/  models/  schemas/  services/  core/ (auth, deps, scheduler)
│  │  └─ main.py
│  └─ tests/
├─ frontend/         # Next.js app
│  └─ src/app/ (app)/ (portal)/ (auth)/  src/lib/api/
├─ docker-compose.yml   # Postgres (+ mailpit for dev email)
└─ docs/superpowers/specs/
```
