# State-to-jurisdiction wiring design

Sub-project (d), the final piece of the VIC milestone. The compliance
service (api.leasekoala.com) accepts `NSW|VIC` for both audit types;
this app still hardcodes `"jurisdiction": "NSW"` in both submit paths
(`services/compliance.py`, `services/clause_audit.py`). Wire
`Property.state` to the submitted jurisdiction end-to-end, stop
silently auditing non-NSW properties against NSW law, and re-audit the
stored results that ran under the wrong jurisdiction.

Decisions taken with the owner: unmapped or missing state skips the
audit and surfaces a prompt (no silent NSW default); the property form
becomes a state dropdown; the backfill CLI re-audits mismatched rows.
Carry-in decisions closed here: the capability matrix is a local
constant (`SUPPORTED_JURISDICTIONS = {"NSW", "VIC"}`, shared by both
audit types until they diverge); the finding `skip_reason` convention
stays as-is (summary is the display carrier, skip_reason is
diagnostic) - no change, recorded as settled.

## Mapper and models

`backend/app/services/jurisdiction.py` (pure functions, no I/O):

- `normalize_state(text: str | None) -> str | None` - maps free text to
  one of the eight state/territory codes (NSW, VIC, QLD, SA, WA, TAS,
  ACT, NT): case-insensitive, whitespace/punctuation-tolerant, full-name
  aliases ("New South Wales" -> NSW, "Victoria"/"Vic." -> VIC, and the
  analogous names for the other six). Unrecognisable -> None.
- `SUPPORTED_JURISDICTIONS = {"NSW", "VIC"}`.
- `jurisdiction_for(property) -> tuple[str | None, str]` with reason
  `"ok"` (supported code), `"missing"` (state null or unparseable), or
  `"unsupported"` (valid state outside the supported set). The three
  reasons drive every downstream behaviour.

`LeaseAudit` and `LeaseClauseAudit` each gain a
`jurisdiction: Mapped[str]` column; one Alembic migration backfills
existing rows to `"NSW"` (historically true - they ran as NSW). The UI
can then label results with the jurisdiction they were audited under,
and the backfill CLI can find rows whose stored jurisdiction no longer
matches the property.

## Submit paths, queue, backfill

- `chain_to_audit_payload(chain, jurisdiction)` takes the resolved code;
  `run_lease_audit` resolves via the lease's property first and raises
  `JurisdictionUnresolved(reason)` for `missing`/`unsupported` without
  calling the service. `submit_document_audit` (clause) gets the same
  resolution and exception.
- Manual-trigger endpoints catch it and return 422 with the reason.
- The queue drain catches it and dequeues without retry - an unset state
  is not transient; the next lease change re-enqueues after the user
  fixes it. Enqueue itself stays judgment-free (state may be fixed
  between enqueue and drain).
- Poll and notifications are untouched (rule ids are
  jurisdiction-prefixed already).
- Backfill CLI gains `--fix-jurisdictions`: for every lease whose
  property maps to a supported jurisdiction X but whose latest
  `LeaseAudit.jurisdiction != X`, re-run the deterministic audit; same
  logic for the latest clause audit per document (costs LLM quota, small
  volume). Per-row reporting; idempotent (matching rows skipped);
  `missing`/`unsupported` properties are listed but not acted on.

## Frontend

- Property new/edit forms: state becomes a dropdown of the eight codes
  plus an empty option, following the forms' existing field pattern; a
  legacy free-text value that normalises is pre-selected on load.
- Lease compliance sections (deterministic and clause): result rows get
  a jurisdiction badge ("audited as NSW/VIC") read from the new column;
  the section's data source gains a computed `jurisdiction_status`
  (derived live from the property, never stored, so fixing the state
  flips it immediately): `ok` renders normally; `missing` shows a
  set-the-property-state prompt linking to the property edit page with
  the trigger button disabled; `unsupported` shows "(state) is not yet
  supported for compliance audits" with the button disabled - old
  results, if any, stay visible under their own badge.
- Finding rendering is untouched: it is already generic per rule_id
  (verified during exploration - no family hardcoding exists), which
  closes the display carry-in from sub-project (c).

## Testing

- Mapper: exhaustive unit tests - all eight codes in several spellings,
  garbage, None, and the three `jurisdiction_for` reasons.
- Services (respx-mocked compliance API): a VIC property produces
  `"jurisdiction": "VIC"` in the payload; `missing` raises, the router
  returns 422, and the drain dequeues with zero service calls asserted;
  clause submit likewise.
- Backfill selection: mismatched rows selected, matching rows skipped,
  missing/unsupported listed only.
- Migration: existing rows read back as "NSW".
- The env-gated e2e adds a VIC property + lease case asserting `vic.*`
  rule ids and the jurisdiction fields in the responses.

## Rollout (interactive)

1. Deploy the migration through the app's own flow.
2. Run `--fix-jurisdictions`, review its report first (how many
   missing/unsupported/re-audits, clause-quota cost), then execute.
3. Live acceptance: one real VIC property end-to-end (dropdown -> VIC ->
   trigger -> `vic.*` findings with the VIC badge) and one property with
   no state showing the prompt card.
4. Ledger and milestone memory: (d) done - the VIC milestone is
   complete.

## Out of scope

- Any compliance-service change.
- Opening further jurisdictions (QLD etc.) - the dropdown lists them,
  audits report them unsupported.
- Stripe/portal work.
