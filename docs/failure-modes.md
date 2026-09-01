# Failure Modes

Each failure is handled at the lowest layer that can enforce the required
guarantee. n8n owns orchestration fallbacks; FastAPI owns data integrity and
stable error contracts.

## Unknown caller

- Detection: phone lookup finds no customer.
- API: returns `200` with `match_status=not_found` and no customers.
- n8n: selects the unknown-caller response instead of treating it as an outage.
- Caller outcome: asked for identifying details or routed to a safe fallback.

## Ambiguous caller

- Detection: multiple customers share the normalized phone number.
- API: returns `200`, `match_status=ambiguous`, and all possible identities.
- n8n: does not select a customer automatically.
- Caller outcome: asked to confirm a name or unit.

## Existing maintenance ticket

- Detection: an open ticket has the same customer, property, and normalized
  category.
- API: returns that ticket with status `200` and `X-Existing-Ticket: true`;
  raises its priority if the new report is more severe.
- n8n: returns the existing ticket rather than posting another issue.
- Caller outcome: receives the existing reference and confirmation.

## Duplicate event delivery

- Detection: `X-Event-ID` already exists with the same operation and request
  hash.
- API: returns the stored result and `X-Idempotent-Replay: true`.
- n8n: treats the replay as the original success.
- Caller outcome: receives a stable response; no duplicate ticket or call
  outcome is created.

## Event ID reused for different data

- Detection: an existing event ID has a different operation or request hash.
- API: returns `409 IDEMPOTENCY_KEY_REUSED`.
- n8n: stops retrying that payload and follows an integration-error branch.
- Caller outcome: receives a safe fallback; the conflicting side effect is not
  performed.

## Customer-system timeout

- Detection: the integration adapter exhausts three attempts after timeout.
- API: returns `503 CUSTOMER_SYSTEM_TIMEOUT`, `retryable=true`, and attempt
  details.
- n8n: uses its bounded retry and then the temporary-unavailable fallback.
- Caller outcome: informed that the customer system is temporarily unavailable;
  no partial side effect remains.

## Customer-system unavailable

- Detection: connection failures or repeated `502`, `503`, or `504` responses.
- API: returns `503 CUSTOMER_SYSTEM_UNAVAILABLE`, `retryable=true`.
- n8n: follows the bounded fallback path after retries are exhausted.
- Caller outcome: receives a temporary-service message without backend details.

The customer-system adapter is currently tested against deterministic mocks. It
is not wired to a real CRM because canonical customer data is stored directly
in PostgreSQL.

## Permanent customer-system error

- Detection: an upstream error outside the transient retry set.
- API: does not retry and maps the rejection to a non-retryable structured
  error.
- n8n: avoids a retry loop and selects an operator or caller fallback.
- Caller outcome: safe failure message; no duplicate or partial write.

## Malformed or inconsistent request

- Detection: Pydantic validation, unknown fields, invalid priorities, missing
  IDs, mismatched customer/property references, or contradictory transfer
  state.
- API: returns `422 VALIDATION_ERROR` with field details or a specific stable
  reference code.
- n8n: stops retrying permanent input errors.
- Caller outcome: safe fallback; no database side effect occurs.

## Missing or invalid API key

- Detection: `X-API-Key` is absent or does not safely match configuration.
- API: returns `401 UNAUTHORIZED`.
- n8n: execution fails through its explicit error output.
- Caller outcome: generic integration fallback; credentials are never exposed.

## Database unavailable

- Detection: SQLAlchemy cannot complete the operation or `/ready` cannot execute
  its lightweight query.
- API: `/health` stays `200`; `/ready` and database operations return structured
  `503 DATABASE_UNAVAILABLE`.
- n8n: may retry a safe operation only with the same event ID, then falls back.
- Caller outcome: temporary-service response with no partial committed write.

## Emergency contact missing

- Detection: the property exists but its referenced contact record does not.
- API: returns `404 EMERGENCY_CONTACT_NOT_FOUND`.
- n8n: skips transfer and enters the critical fallback.
- Caller outcome: critical ticket is preserved and follow-up is required.

## Emergency contact unavailable

- Detection: the emergency-contact record exists with `available=false`.
- API: returns `503 EMERGENCY_CONTACT_UNAVAILABLE`, `retryable=true`.
- n8n: skips the transfer simulation, creates or preserves a critical ticket,
  tries the manager notification branch, and requires follow-up.
- Caller outcome: told that immediate transfer was unavailable and that the
  emergency was recorded for follow-up.

## Manager missing or unavailable

- Detection: the referenced manager is missing or has `available=false`.
- API: returns `404 PROPERTY_MANAGER_NOT_FOUND` or retryable
  `503 MANAGER_UNAVAILABLE`.
- n8n: keeps the ticket/outcome and records that notification could not be
  completed.
- Caller outcome: issue remains recorded and follow-up remains required.

## Failed transfer

- Detection: the simulated transfer branch reports failure or the emergency
  contact is unavailable.
- API: accepts an unresolved emergency outcome only when it references a
  critical ticket and sets `follow_up_required=true`.
- n8n: creates or preserves the critical ticket and attempts manager
  notification.
- Caller outcome: no claim of a successful handover; receives explicit fallback
  confirmation.

## Duplicate manager notification

- Detection: post-call workflow derives stable event identifiers and the
  persisted call outcome is idempotent.
- API: stores only one call outcome for the repeated logical event.
- n8n: avoids taking a second notification path when the event is a replay.
- Caller outcome: unchanged; operational staff should receive one logical
  follow-up.

## Unexpected internal error

- Detection: uncaught exception reaches middleware.
- API: logs the failure and returns `500 INTERNAL_ERROR` without a stack trace.
- n8n: uses the generic failure branch.
- Caller outcome: generic temporary-failure message; implementation details are
  not exposed.
