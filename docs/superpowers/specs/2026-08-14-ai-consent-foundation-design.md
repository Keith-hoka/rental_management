# AI Consent Foundation Design

Date: 2026-08-14. Status: approved for planning.
Sub-project (a) of the rent-AI milestone; (b) renewal-increase suggestions
and (c) market rent estimation follow in their own spec cycles.

## Context and goal

The SaaS already sends lease document text to LLM providers (Anthropic,
with an OpenAI failover, via the compliance service) for clause audits,
and the upcoming rent-AI features will send rent and property data the
same way — yet the app carries no AI disclosure and no consent surface.
This sub-project builds the foundation both features stand on: a
versioned AI disclosure, per-feature organization-level consent with an
audit trail, and a backend gate every AI feature must pass.

Deterministic compliance audits (structured data through the rule engine,
no LLM) are out of the gate's scope and keep running for every
organization.

## Owner decisions (2026-08-14)

- **Coverage: all AI features** — the existing clause audit and the
  future rent AI share one foundation; the disclosure obligation for
  clause audits already exists today.
- **Per-feature toggles** at organization level, switchable only by the
  `landlord` role.
- **Existing organizations: off until consented.** After rollout, AI
  features are disabled everywhere until a landlord reads the disclosure
  and enables them. No grandfathering; consent records are never
  retroactive.
- **Disclosure artifact: a versioned AI-disclosure page only.** The full
  SaaS ToS / privacy policy is a separate, lawyer-reviewed effort; this
  sub-project must not block on it.

## Data model and consent semantics

New table `ai_feature_consents` — an append-only event stream:

- `id` (uuid pk), `organization_id` (fk, indexed)
- `feature` (enum `AiFeature`: `clause_audit`, `rent_ai` reserved)
- `enabled` (bool — the state this event set)
- `disclosure_version` (str, e.g. `"2026-08-14"` — the version shown when
  the landlord acted)
- `acted_by` (fk users.id), `created_at` (server default now)

Current state of a feature = the newest event's `enabled` for that
(organization, feature), ordered by a monotonic `seq` identity column
(amended 2026-08-14: review reproduced identical created_at timestamps for
two events in one transaction; `created_at` is informational); **no rows
means not consented**, which is exactly the migration semantics for
existing organizations — no backfill.
Every toggle inserts a new row, so who enabled/disabled what, when, and
against which disclosure version is answerable from the table alone.
Disabling never deletes data: completed audit results stay readable; only
new AI processing stops.

## Backend gate

- `require_ai_consent(feature)` — a dependency factory beside the
  existing `require_roles` (`app/core/deps.py`): resolves the current
  membership's organization, checks the newest consent event, and raises
  403 with a machine-readable body (`{"detail": {"code":
  "ai_consent_required", "feature": "clause_audit"}}`) when the feature
  is not enabled. Applied to the clause-audit submit endpoints.
- **Two LLM paths exist and both are gated: the submit endpoint and the
  operator backfill `fix_jurisdictions --execute`** (missed by the
  original verification, caught in final review): `drain_audit_queue`
  drains deterministic audits (no LLM, exempt by design) and the
  scheduled `poll_clause_audits` only advances already-submitted jobs —
  gating it would strand in-flight work. No scheduler changes.
- Toggle endpoints: `GET /api/ai-consents` (any member — read the current
  state and disclosure version for display) and
  `POST /api/ai-consents/{feature}` (body `{"enabled": bool}`,
  `require_roles(Role.landlord)`); the POST records the disclosure
  version it served and returns the new state.
- The consent check reads one indexed row; no caching layer until a
  measured need exists.

## Disclosure content and frontend

- The disclosure version has one owner: the backend constant
  `AI_DISCLOSURE_VERSION` (`app/services/ai_consent.py`, e.g.
  `"2026-08-14"`), served by the consent API and stamped into every
  consent event. The disclosure copy lives in a frontend content module
  (`frontend/src/content/aiDisclosure.tsx`) rendered on the settings
  page, which displays the version from the API. Content covers four
  points:
  what is sent (property attributes, rent figures, dates, lease document
  text), to whom (Anthropic, with an OpenAI backup, via our compliance
  service), **what is never sent (tenant names, emails, phone numbers,
  co-tenant details never appear in the structured data the app
  assembles — this line doubles as the implementation contract binding
  the future rent-AI prompts; uploaded lease documents are transmitted
  verbatim, so personal details written into the document itself are
  not covered by this guarantee)**, and the nature of results
  (general information, not legal advice).
- New page `app/settings/ai`: renders the disclosure and per-feature
  toggles. Landlords can switch; other roles see read-only state. Nav
  entry appears for all members.
- Where the clause-audit UI currently offers submission, an unconsented
  organization sees a prompt card ("AI features are disabled — a landlord
  can enable them in Settings") linking to the page instead of the
  submit control, mirroring the existing jurisdiction three-state prompt
  cards.

## Testing

- Backend unit tests: consent state machine (no rows -> disabled; toggle
  sequence -> newest wins; disclosure version recorded), gate 403 body,
  role enforcement on the POST (property_manager and tenant get 403).
- Frontend Playwright e2e: landlord enables clause audit (card ->
  settings -> toggle -> submit control appears); disable flips the UI
  back; non-landlord sees read-only state.
- No LLM eval: this sub-project never calls a model.

## Out of scope (YAGNI)

- Full SaaS ToS / privacy policy (separate lawyer-reviewed effort).
- Per-user consent, consent expiry, or re-consent on disclosure version
  bumps (a version bump simply shows the new text; forcing re-consent is
  a product decision deferred until a material change happens).
- Tenant-facing consent flows — tenant personal data never enters
  prompts by design, so tenant notice belongs to the future privacy
  policy, not this gate.
- Compliance-service changes: the gate lives entirely in the SaaS.
