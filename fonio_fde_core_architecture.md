# Fonio FDE Lab — Core Architecture

## Goal

Build only the **core architecture** for a fictional property-management customer integration.

The project simulates how a Forward Deployment Engineer could connect Fonio with a customer's internal systems.

Do **not** build a frontend yet.
Do **not** build the full workflow yet.
Do **not** integrate with the real Fonio API yet.
Do **not** add unnecessary abstractions.

## Architecture

```text
Fonio
  ↓
n8n
  ↓ HTTP
FastAPI
  ↓
Mock customer systems
```

Responsibilities:

- **n8n** = workflow orchestration
- **FastAPI** = APIs, business logic, validation, and customer-system integration
- **Mock data** = simulate the property-management CRM/database

## Tech Stack

- Python
- FastAPI
- Pydantic
- pytest
- Docker
- n8n via Docker Compose

Use in-memory/mock data initially. No PostgreSQL yet.

## Project Structure

Create approximately this structure:

```text
fonio-fde-lab/
├── app/
│   ├── main.py
│   ├── customers/
│   │   ├── router.py
│   │   ├── service.py
│   │   └── schemas.py
│   ├── properties/
│   │   ├── router.py
│   │   ├── service.py
│   │   └── schemas.py
│   ├── tickets/
│   │   ├── router.py
│   │   ├── service.py
│   │   └── schemas.py
│   └── data/
│       └── mock_data.py
├── tests/
│   └── test_customers.py
├── n8n/
│   └── workflows/
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env.example
└── README.md
```

Small deviations are fine if they make the structure cleaner.

## Initial Domain

The fictional customer is:

**HausPilot Immobilienverwaltung GmbH**

A Vienna property-management company managing around 2,500 apartments.

Its internal systems contain:

- tenants
- properties
- apartments
- property managers
- maintenance tickets
- emergency contacts

## Core Models

Create simple Pydantic models for:

### Customer

```text
id
first_name
last_name
phone
property_id
unit
property_manager_id
```

### Property

```text
id
address
property_manager_id
emergency_contact_id
```

### Ticket

```text
id
customer_id
property_id
category
description
priority
status
```

## Seed Data

Add several fake records.

Include at least:

1. A normal tenant:
   - Anna Müller
   - phone: +436601234567
   - Neubaugasse 17
   - unit 4B

2. A tenant with an existing maintenance ticket.

3. Two people sharing the same phone number so ambiguous identity can be supported later.

## API Endpoints

Implement only these initial endpoints:

### Health

```http
GET /health
```

Response:

```json
{
  "status": "ok"
}
```

### Find customer by phone

```http
GET /customers/by-phone/{phone}
```

Important:

A phone number may match:

- zero customers
- one customer
- multiple customers

Return a structured response that supports all three cases.

### Customer open tickets

```http
GET /customers/{customer_id}/open-tickets
```

### Get property

```http
GET /properties/{property_id}
```

### Create maintenance ticket

```http
POST /tickets
```

Validate the request using Pydantic.

## n8n

Add n8n to `docker-compose.yml`.

The FastAPI service and n8n should be on the same Docker network.

n8n should be able to call FastAPI using:

```text
http://api:8000
```

Do not build the full n8n workflow yet.

Optionally create a very small example workflow or document how to create:

```text
Manual Trigger
    ↓
HTTP Request
    ↓
GET http://api:8000/customers/by-phone/+436601234567
```

## Docker Compose

`docker-compose up --build` should start:

- FastAPI on port 8000
- n8n on port 5678

## Tests

Add basic pytest tests for:

- known phone → one customer
- unknown phone → zero customers
- shared phone → multiple customers
- getting open tickets
- creating a valid ticket

## README

Keep the README short.

Explain:

1. what the project simulates
2. architecture
3. how to run it
4. API endpoints
5. how n8n communicates with FastAPI

## Scope Restrictions

For this first version, **do not implement**:

- real Fonio integration
- LLM calls
- real CRM integrations
- PostgreSQL
- authentication
- retries
- idempotency
- notifications
- emergency escalation
- frontend/dashboard
- Kubernetes
- complex observability

Those will be added later.

The objective of this task is only to create a **clean, runnable foundation** that can be extended incrementally.

## Definition of Done

The task is complete when:

1. `docker-compose up --build` starts FastAPI and n8n.
2. `GET /health` works.
3. Customer lookup by phone works.
4. Customer open-ticket lookup works.
5. Property lookup works.
6. Maintenance-ticket creation works.
7. Tests pass.
8. n8n can reach FastAPI over the Docker network.
