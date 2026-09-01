# Architecture

## System overview

```text
Mocked Fonio event
        |
        v
   n8n webhook
        |
        v
 FastAPI service
        |
        v
   PostgreSQL
```

The mocked event has the same structured fields that a configured Fonio
during-call or post-call action would send. Replacing the mock does not change
the n8n-to-backend contracts.

## Responsibilities

### Fonio boundary

Fonio would conduct the call, extract variables, invoke during-call and
post-call actions, and perform a supported human transfer. In this repository,
scenario JSON files stand in for those outputs. No private or undocumented
Fonio API is used.

### n8n

n8n decides what happens next. Four small workflows perform caller-context
assembly, maintenance orchestration, emergency escalation, and post-call
processing. They branch on business and error results, send correlation
headers, keep retries bounded, and return caller-safe responses.

### FastAPI

FastAPI performs operations safely. It owns authentication, request validation,
business rules, duplicate-ticket detection, idempotent writes, database
transactions, structured errors, integration retry policy, and request logs.
Keeping those guarantees out of workflow code makes them reusable and testable.

### PostgreSQL

PostgreSQL stores customers, properties, managers, emergency contacts, tickets,
call outcomes, and processed event records. A PostgreSQL advisory transaction
lock serializes concurrent attempts to create the same customer/property/
category issue.

## Network boundaries

| Caller | Address |
| --- | --- |
| Browser, curl, or Insomnia | `http://localhost:8000` |
| n8n workflow | `http://api:8000` |
| API container | `db:5432` |
| Host PostgreSQL client | `localhost:5433` |
| n8n browser UI | `http://localhost:5678` |

Only API traffic inside the Compose network uses the service names `api` and
`db`. A host browser cannot resolve those names.

## API surface

Public endpoints:

- `GET /health`
- `GET /ready`
- `GET /docs`
- `GET /redoc`
- `GET /openapi.json`

Endpoints protected by `X-API-Key`:

- `GET /customers/by-phone/{phone}`
- `GET /customers/{customer_id}/open-tickets`
- `GET /properties/{property_id}`
- `GET /properties/{property_id}/manager`
- `GET /properties/{property_id}/emergency-contact`
- `POST /tickets`
- `POST /call-outcomes`

Every backend call from n8n sends `X-Conversation-ID`. Side-effecting calls also
send a stable `X-Event-ID`. The API returns `X-Request-ID` and echoes correlation
headers where applicable.

## Data model

- `customers`: identity, phone, property, unit, and manager reference.
- `properties`: address plus manager and emergency-contact references.
- `property_managers`: contact details and availability.
- `emergency_contacts`: contact details, type, and availability.
- `tickets`: customer, property, category, description, priority, and status.
- `call_outcomes`: conversation summary, related records, transfer result, and
  follow-up state.
- `processed_events`: event ID, operation, request hash, status, stored response,
  result reference, and processing time.

Startup creates missing tables and inserts only missing canonical records. It
does not overwrite user-created data. The guarded reset command deletes
application rows and reseeds all canonical records in one transaction.

## Idempotent transaction

For `POST /tickets` and `POST /call-outcomes`:

1. Validate the API key, correlation headers, event ID, and request body.
2. Normalize and hash the side-effect payload.
3. Claim the unique event ID inside the database transaction.
4. Perform the write and store its response with the processed event.
5. Commit both together.
6. Return the stored response with `X-Idempotent-Replay: true` on redelivery.
7. Return `409 IDEMPOTENCY_KEY_REUSED` if the same ID carries different data.

Ticket creation additionally checks for an open ticket with the same customer,
property, and category. It returns that ticket and safely raises its priority
when required.

## Request observability and errors

Middleware creates a request ID, reads the conversation ID, measures elapsed
time, and writes a JSON `http_request_completed` event. Business events record
important outcomes without logging secrets. Central handlers return:

```json
{
  "error": {
    "code": "CUSTOMER_NOT_FOUND",
    "message": "Customer not found",
    "retryable": false,
    "conversation_id": "conversation-123"
  }
}
```

`/health` checks only whether the process is alive. `/ready` executes a
lightweight database query and returns `503` when PostgreSQL is unavailable.

## External-system retry boundary

The reusable HTTP adapter uses a 2-second connect timeout, 5-second read
timeout, and at most three attempts with 0.25- and 0.75-second delays. It retries
network errors, timeouts, and `502`, `503`, or `504`; permanent HTTP failures
are returned immediately. The current customer records are local PostgreSQL
data, so this adapter is tested but is not attached to a real legacy CRM.

## Normal maintenance sequence

1. n8n receives extracted maintenance fields.
2. It loads the customer's open tickets.
3. It returns a matching ticket when one is obvious.
4. Otherwise it posts the ticket with stable correlation and event headers.
5. FastAPI repeats duplicate detection under transaction protection and returns
   the existing or newly created record.

## Emergency sequence

1. n8n receives a critical request.
2. It retrieves the property's emergency contact.
3. An available contact follows the simulated transfer branch.
4. Unavailability or failure follows the fallback branch.
5. The fallback creates or preserves a critical ticket, attempts the simulated
   manager notification, and marks follow-up as required.
6. Post-call processing persists the structured final outcome idempotently.
