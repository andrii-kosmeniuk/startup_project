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
its first startup.

Run tests locally after installing the dependencies:

```bash
python -m pip install -r requirements.txt
pytest
```

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
at `http://api:8000`. To try it, create a Manual Trigger followed by an HTTP
Request node using:

```text
GET http://api:8000/customers/by-phone/+436601234567
```

Configure an n8n Header Auth credential with header name `X-API-Key` and the
same `API_KEY` value used by the API container. Do not store the secret directly
in workflow exports.

Send `X-Conversation-ID` with each n8n request to correlate API and workflow
logs. The API returns the same header together with a generated `X-Request-ID`.
Side-effect requests whose body contains `conversation_id` must use the same
value in the header.

`POST /tickets` and `POST /call-outcomes` also require a stable `X-Event-ID`.
n8n must reuse that value when retrying the same logical event. Duplicate
delivery returns the original result with `X-Idempotent-Replay: true`; reusing
an event ID for different data returns `409 IDEMPOTENCY_KEY_REUSED`.

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
