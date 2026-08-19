# Fonio FDE Lab

A runnable foundation that simulates Fonio calling an n8n workflow, which then
uses a FastAPI integration service to access HausPilot Immobilienverwaltung
GmbH's mock property-management systems.

```text
Fonio -> n8n -> HTTP -> FastAPI -> in-memory customer systems
```

## Run

```bash
cp .env.example .env
docker compose up --build
```

FastAPI is available at <http://localhost:8000> (interactive docs at
<http://localhost:8000/docs>) and n8n at <http://localhost:5678>.

Run tests locally after installing the dependencies:

```bash
python -m pip install -r requirements.txt
pytest
```

## API

- `GET /health`
- `GET /customers/by-phone/{phone}`
- `GET /customers/{customer_id}/open-tickets`
- `GET /properties/{property_id}`
- `POST /tickets`

Phone lookup always returns a status (`not_found`, `unique`, or `ambiguous`), a
match count, and a customer list.

## n8n connectivity

Compose places both services on its default network, where n8n reaches the API
at `http://api:8000`. To try it, create a Manual Trigger followed by an HTTP
Request node using:

```text
GET http://api:8000/customers/by-phone/+436601234567
```

Workflow exports can be stored in `n8n/workflows/`.
