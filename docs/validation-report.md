# Validation Report

Validated on 2026-08-31.

## Environment

- Docker Engine 29.7.2
- n8n 2.35.5
- API image based on Python 3.12
- PostgreSQL 17
- Host-side tests run with Python 3.12.14

## Automated checks

```text
165 passed in 1.44s
```

The complete pytest suite passed, including API behavior, authentication,
validation, structured errors, correlation logs, idempotency, seed/reset rules,
integration retry policy, workflow export contracts, webhook identity, empty
ticket-array handling, and scenario fixtures.

`docker compose config --quiet` and `git diff --check` also passed.

## Compose runtime

`docker compose up -d --build` built the API and started:

- `fonio_project-api-1`: healthy on port 8000;
- `fonio_project-db-1`: healthy on host port 5433;
- `fonio_project-n8n-1`: running on port 5678.

`/health` and `/ready` returned `200`. Requests without an API key and with an
invalid API key returned `401`; the configured key succeeded. Correlated API
logs included request ID, conversation ID, status, and duration.

With PostgreSQL stopped, `/health` remained `200` and `/ready` returned
structured `503 DATABASE_UNAVAILABLE`. PostgreSQL was restarted and readiness
recovered.

## Clean n8n validation

All four workflow exports imported and published in an isolated n8n 2.35.5
instance with an isolated Header Auth credential. Production webhook paths were:

- `/webhook/caller-context`
- `/webhook/maintenance-request`
- `/webhook/emergency-escalation`
- `/webhook/fonio-post-call-processing`

Clean runtime validation found and fixed two issues that static checks did not
catch:

1. caller context needed a stable `webhookId` to register after import;
2. maintenance needed a full-response wrapper so an empty `[]` open-ticket
   response still produced one n8n item and continued to ticket creation.

Regression assertions were added for both behaviors.

## Scenario outcomes

- Unknown caller returned `match_status=not_found`.
- Shared phone returned two identity choices and did not select one.
- Known caller returned customer, property, and open tickets.
- Existing heating report returned canonical `ticket-932`.
- Normal plumbing maintenance created a medium-priority open ticket.
- Sending the electrical duplicate payload twice returned one ticket ID.
- Available-contact emergency followed the input-driven simulated-transfer
  failure branch and created/preserved a critical ticket with follow-up.
- Unavailable-contact emergency skipped transfer, created a critical ticket,
  and required follow-up.
- Duplicate post-call delivery returned `already_processed` and produced one
  call-outcome row.
- Reusing a processed event ID with changed data returned
  `409 IDEMPOTENCY_KEY_REUSED`.

PostgreSQL verification showed one electrical ticket, one plumbing ticket, two
water-leak tickets for the two different properties, one processed event per
logical side effect, and one call outcome per demonstrated conversation.

The `crm-timeout.json` and `crm-unavailable.json` payloads were accepted as
caller-context contract examples. They intentionally do not inject failure into
the PostgreSQL-backed lookup. Timeout, transient `503`, and permanent-error
retry behavior passed deterministic integration-client tests.

## Demo boundary

Webhook JSON represented Fonio-extracted variables. n8n, FastAPI, PostgreSQL,
and the side effects above were executed locally. Voice, real call transfer,
and manager notification were simulated. Use `docs/demo-script.md` to record
the final narrated video without overstating Fonio access.
