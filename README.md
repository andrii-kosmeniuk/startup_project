# Fonio FDE Lab

A Forward Deployment Engineer case study for HausPilot Immobilienverwaltung
GmbH, a fictional Vienna property manager. It shows how structured call events
can identify tenants, retrieve property context, avoid duplicate maintenance
tickets, escalate emergencies, and persist reliable post-call outcomes.

```text
Mocked Fonio JSON -> n8n -> FastAPI -> PostgreSQL
```

The Fonio boundary is mocked because this project has no Fonio account. n8n,
FastAPI, PostgreSQL, validation, authentication, idempotency, retries, and logs
are real local components. Voice, call transfer, and manager notification are
simulations and are never presented as tested telephony.

## Architecture and workflows

- `01-caller-context`: returns a unique tenant with property/tickets, possible
  identities for a shared number, or an unknown-caller fallback.
- `02-maintenance-request`: checks open tickets and idempotently creates or
  returns a matching ticket.
- `03-emergency-escalation`: checks contact availability and follows simulated
  transfer or critical-ticket/follow-up fallback branches.
- `04-post-call-processing`: idempotently stores the final call outcome and
  follows the simulated notification branch when required.

FastAPI owns data integrity and stable contracts. n8n owns customer-specific
branching and sequencing. See [architecture](docs/architecture.md), [customer
requirements](docs/customer-requirements.md), [failure
modes](docs/failure-modes.md), and the [deployment
playbook](docs/deployment-playbook.md). A concise [recording
script](docs/demo-script.md) is included for the final video, and the
[validation report](docs/validation-report.md) records the verified results.

## Run locally

Docker must be installed and its daemon running:

```bash
cp .env.example .env
# Replace API_KEY in .env with a local secret.
docker compose up -d --build
docker compose ps
```

Service addresses:

- FastAPI: <http://localhost:8000>
- Swagger: <http://localhost:8000/docs>
- n8n: <http://localhost:5678>
- PostgreSQL from the host: `localhost:5433`
- FastAPI from n8n: `http://api:8000`

The API creates missing tables and canonical records at startup without
overwriting user data.

Check liveness and database readiness:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

## Import n8n workflows

Import these files into a clean n8n instance:

```text
n8n/workflows/01-caller-context.json
n8n/workflows/02-maintenance-request.json
n8n/workflows/03-emergency-escalation.json
n8n/workflows/04-post-call-processing.json
```

Create a Header Auth credential named `Fonio FastAPI API Key`:

```text
Header: X-API-Key
Value:  the API_KEY value from .env
```

Attach it to every FastAPI HTTP Request node and activate the workflows. The
production webhook paths are:

```text
POST /webhook/caller-context
POST /webhook/maintenance-request
POST /webhook/emergency-escalation
POST /webhook/fonio-post-call-processing
```

During manual editing, n8n may expose the equivalent `/webhook-test/...` URL
while listening for a test event.

## Mocked Fonio demo

Scenario payloads are in `scenarios/`. They represent variables extracted by
Fonio during or after a call.

Unique caller:

```bash
curl -sS -X POST http://localhost:5678/webhook/caller-context \
  -H 'Content-Type: application/json' \
  --data '{"conversation_id":"demo-caller-001","phone":"+436601234567"}'
```

Normal maintenance:

```bash
curl -sS -X POST http://localhost:5678/webhook/maintenance-request \
  -H 'Content-Type: application/json' \
  --data @scenarios/normal-maintenance.json
```

Emergency fallback:

```bash
curl -sS -X POST http://localhost:5678/webhook/emergency-escalation \
  -H 'Content-Type: application/json' \
  --data @scenarios/transfer-failure.json
```

For `scenarios/duplicate-webhook.json`, send each object in `deliveries`
separately to the maintenance webhook. Both responses should identify the same
logical result and only one side effect should exist.

`crm-timeout.json` and `crm-unavailable.json` document caller-context contracts;
the current customer source is PostgreSQL, so these payloads do not inject an
outage by themselves. Timeout, retry, and terminal error behavior is verified
deterministically in `tests/test_integration_client.py`.

## API contracts

Public:

- `GET /health`
- `GET /ready`
- `GET /docs`, `/redoc`, and `/openapi.json`

Protected by `X-API-Key`:

- `GET /customers/by-phone/{phone}`
- `GET /customers/{customer_id}/open-tickets`
- `GET /properties/{property_id}`
- `GET /properties/{property_id}/manager`
- `GET /properties/{property_id}/emergency-contact`
- `POST /tickets`
- `POST /call-outcomes`

n8n sends `X-Conversation-ID` on backend requests. `POST /tickets` and
`POST /call-outcomes` also require a stable `X-Event-ID`. Redelivery returns the
stored response with `X-Idempotent-Replay: true`; conflicting reuse returns
`409 IDEMPOTENCY_KEY_REUSED`.

Errors share this shape:

```json
{
  "error": {
    "code": "CUSTOMER_NOT_FOUND",
    "message": "Customer not found",
    "retryable": false,
    "conversation_id": "demo-caller-001"
  }
}
```

## Reliability behavior

- Unknown and ambiguous callers are normal, safe business outcomes.
- Ticket duplicate detection uses customer, property, and category.
- PostgreSQL transactions and advisory locks protect concurrent ticket writes.
- Side effects and processed-event records commit atomically.
- Customer-system HTTP calls use explicit timeouts and at most three attempts.
- Only network failures, timeouts, `502`, `503`, and `504` are retried.
- `/health` does not query PostgreSQL; `/ready` does.
- Requests emit JSON logs with request ID, conversation ID, status, and duration.

## Tests

Use an isolated environment:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest -q
```

The current verified result is `165 passed`.

Use Python 3.12 or 3.13 for host-side tests. The pinned Pydantic version does
not build on Python 3.14; the Docker image already uses Python 3.12.

The suite uses isolated SQLite sessions for API behavior and deterministic
in-memory HTTP transports for integration failures. PostgreSQL/n8n runtime
validation remains a separate acceptance step:

```bash
.venv/bin/python -m pytest -q tests/test_n8n_workflows.py
```

## Reset demo data

This deletes all application records from the configured local database and
restores only canonical demo records:

```bash
docker compose run --rm \
  -e CONFIRM_DEMO_DATA_RESET=reset-fonio-demo-data \
  api python -m app.data.reset_demo
```

The exact confirmation value is required. Deletion and reseeding happen in one
transaction. Docker volumes, workflow definitions, and n8n credentials are not
removed.

## Intentional scope limits

- No custom telephony, speech-to-text, text-to-speech, SIP, or Twilio layer.
- No undocumented Fonio endpoints.
- No production notification provider.
- No real legacy CRM call; the reusable adapter is implemented and tested.
- n8n webhook ingress is unauthenticated for this local demo; a production
  deployment must add webhook authentication or private network controls.
- Tables are created with SQLAlchemy `create_all`; production schema evolution
  would require reviewed migrations.
- No claim that simulated transfer or notifications were executed by Fonio.
- No monitoring platform beyond correlated structured logs and health checks.
