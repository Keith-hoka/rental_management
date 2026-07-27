# Compliance Money Fields Design

Give leases the four money fields the NSW compliance rules need —
`rent_in_advance_amount`, `holding_deposit_amount`, `other_security_amount`,
`break_fee_amount` — so the deterministic checks for s33, s24, s160 and
s107 produce real verdicts instead of "skipped", without waiting for the
LLM clause-audit milestone. The compliance service already accepts all
four; this is purely a data-capture gap on the app side.

## Decisions (brainstorm outcomes)

- **Names match the service API exactly.** The app already does this for
  `bond_amount`; the mapper stays a plain field copy.
- **Editing re-audits automatically.** Saving a lease edit that changes
  any compliance-relevant field re-enqueues the lease in the same
  transaction, via the existing outbox. Manual "Check now" remains for
  everything else.
- **No backfill.** Existing leases keep null fields and their rules keep
  skipping honestly; filling the fields in an edit triggers the re-audit
  naturally.
- **The compliance service is untouched.**

## Data model

`Lease` gains four nullable `Numeric(10, 2)` columns named as above, plus
one Alembic migration (add columns; downgrade drops them). They follow
`bond_amount` in every respect.

## Schemas and handlers

- `LeaseCreate`, `LeaseUpdate`, `LeaseRenew`, `LeaseResponse` each gain
  the four optional `Decimal` fields.
- `renew_lease` copies each from the source lease unless the body
  overrides it — the exact `bond_amount` pattern.
- `update_lease` compares the compliance-relevant fields before and after
  applying the body: `rent_amount`, `rent_frequency`, `start_date`,
  `end_date`, `bond_amount` and the four new fields. When any differ and
  the integration is enabled, it calls `enqueue_audit` in the same
  transaction. Edits that touch nothing compliance-relevant (tenant
  details, notice period, co-tenants) do not enqueue.

## Mapper

`chain_to_audit_payload` sends each of the four fields from the newest
lease in the chain when it is non-null, omitting it otherwise — the same
omit-when-null semantics `bond_amount` already has. With values present,
the rent-in-advance (s33), holding-fee (s24), other-security (s160) and
break-fee (s107) rules return red/green verdicts.

## Frontend

- New-lease form and the detail page's edit form gain four optional
  amount inputs, grouped under a small "Upfront money & fees" heading,
  using the existing Bond input's empty-string-to-null handling.
- The renew page gains the same four inputs if it exposes money fields;
  blank means "copy from source".
- The detail page's facts list shows the four values, `—` when unset.
- No change to `ComplianceSection`: the skipped-explanation copy already
  says these fields are "not recorded in this app"; once recorded, the
  rules simply stop skipping. Update the `FIELD_HINTS` strings that claim
  the app does not record these fields — after this milestone that claim
  is false; the hint becomes "not filled in for this lease".

## Testing

- Mapper eval extension (exact-assert): all four fields sent when set on
  the newest lease; omitted when null; renewal chain uses the newest
  lease's values.
- Endpoint tests: create with the four fields persists and returns them;
  renew copies and overrides; update changing a compliance field
  enqueues (queue row appears), update changing only tenant details does
  not; enqueue skipped when the integration is disabled.
- Migration verified up -> down -> up locally.
- Frontend: lint; existing e2e unaffected (all fields optional). The live
  compliance e2e keeps passing because the skipped hint change is
  reflected in its assertions if any assert those strings.

## Out of scope

Compliance service changes, historical backfill, LLM clause audit,
holding-fee capture at application time (the field lives on the lease,
not on a tenancy application object), and any required-field validation —
all four stay optional.
