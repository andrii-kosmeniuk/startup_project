# Fonio FDE Lab

A runnable foundation that simulates Fonio calling an n8n workflow, which then
uses a FastAPI integration service to access HausPilot Immobilienverwaltung
GmbH's PostgreSQL-backed property-management system.

```text
Fonio -> n8n -> HTTP -> FastAPI -> PostgreSQL
```

## Run

```bash
cp .env.example .env
docker compose up --build
```

FastAPI is available at <http://localhost:8000> (interactive docs at
<http://localhost:8000/docs>), n8n at <http://localhost:5678>, and PostgreSQL
on port `5433`. The API creates the tables and inserts initial seed records on
its first startup. The canonical demo data contains one unique caller, two
callers sharing a phone number, available and unavailable escalation contacts,
and one realistic open heating ticket.

Run tests locally after installing the dependencies:

```bash
python -m pip install -r requirements.txt
pytest
```

## Reset demo data

To delete the application records in the local PostgreSQL database and restore
only the canonical demo dataset, run:

```bash
docker compose run --rm \
  -e CONFIRM_DEMO_DATA_RESET=reset-fonio-demo-data \
  api python -m app.data.reset_demo
```

The exact confirmation value prevents accidental execution. The reset is
transactional: if reseeding fails, the deletion is rolled back. It does not
delete Docker volumes or n8n workflows and credentials. Existing application
records are not recoverable after a successful reset unless they were backed
up separately.

## API

- `GET /health`
- `GET /ready`
- `GET /customers/by-phone/{phone}`
- `GET /customers/{customer_id}/open-tickets`
- `GET /properties/{property_id}`
- `POST /tickets`

All business endpoints require the shared API key:

```http
X-API-Key: <value of API_KEY from .env>
```

`/health`, `/docs`, `/redoc`, and `/openapi.json` remain public. In Swagger,
select **Authorize** and enter the API key before calling protected endpoints.

Phone lookup always returns a status (`not_found`, `unique`, or `ambiguous`), a
match count, and a customer list.

## n8n connectivity

Compose places both services on its default network, where n8n reaches the API
at `http://api:8000`. Import the four workflow exports from
`n8n/workflows/`:

```text
01-caller-context.json
02-maintenance-request.json
03-emergency-escalation.json
04-post-call-processing.json
```

Configure an n8n Header Auth credential named `Fonio FastAPI API Key`, with
header name `X-API-Key` and the same `API_KEY` value used by the API container.
After importing, select this credential on every FastAPI HTTP Request node.
The exports contain only the credential reference; they never contain its
secret value.

Send `X-Conversation-ID` with each n8n request to correlate API and workflow
logs. The API returns the same header together with a generated `X-Request-ID`.
Side-effect requests whose body contains `conversation_id` must use the same
value in the header.

`POST /tickets` and `POST /call-outcomes` also require a stable `X-Event-ID`.
n8n must reuse that value when retrying the same logical event. Duplicate
delivery returns the original result with `X-Idempotent-Replay: true`; reusing
an event ID for different data returns `409 IDEMPOTENCY_KEY_REUSED`.

The reusable customer-system HTTP client applies explicit connect/read timeouts
and at most three attempts. It retries only network errors, timeouts, and HTTP
`502`, `503`, or `504`; permanent `4xx` responses and other status errors are
never retried. This client is ready to be wired into the explicit legacy-system
operations introduced by the failure-handling phase.

The n8n HTTP nodes use bounded retries and explicit error outputs. Workflow
fallback responses are safe for the caller and do not expose backend error
details. Emergency transfer and manager notification nodes remain clearly
labelled simulations until the documented Fonio integration is connected in
Phase 11.

Example webhook payloads for normal, duplicate, ambiguous, unavailable, and
emergency paths are stored under `scenarios/`. To verify the exports
statically, run:

```bash
pytest tests/test_n8n_workflows.py
```

For runtime validation, import the workflows into a clean n8n instance,
configure the credential, activate each workflow, submit the corresponding
scenario payloads, and confirm that repeated event IDs create only one ticket
or call outcome.

Ticket creation checks for an existing open ticket with the same customer,
property, and category. A match is returned with `X-Existing-Ticket: true`
instead of creating a duplicate; a higher submitted priority safely escalates
the existing ticket. PostgreSQL advisory transaction locks serialize concurrent
requests for the same issue. Unavailable managers and emergency contacts return
retryable `503` errors. An unresolved emergency call outcome is accepted only
when it references a critical ticket and has `follow_up_required=true`.

`/health` reports whether the API process is alive. `/ready` additionally checks
PostgreSQL and returns `503` when the database is unavailable. API failures use
a consistent `{"error": {...}}` response containing a stable code, message,
retryability flag, and conversation ID.

Workflow exports can be stored in `n8n/workflows/`.

## pgAdmin

Register a server with host `localhost`, port `5433`, database `fonio_fde`,
username `fonio`, and password `fonio_dev_password`. The tables are under
`Databases > fonio_fde > Schemas > public > Tables`; pgAdmin does not need to
create them manually.
