# Final Demo Script

Target length: 5–7 minutes.

## 1. Set expectations

Say:

> This case study uses mocked JSON at the Fonio boundary because I do not have
> access to a Fonio account. The payload represents variables extracted during
> or after a call. Everything after that boundary—n8n orchestration, FastAPI,
> PostgreSQL writes, validation, idempotency, and logs—runs locally. Transfer
> and manager notification are clearly labelled simulations.

Show the architecture section in the README.

## 2. Show healthy services

```bash
docker compose ps
curl -sS http://localhost:8000/health
curl -sS http://localhost:8000/ready
```

Show the n8n workflows and the API documentation briefly.

## 3. Reset canonical data

```bash
docker compose run --rm \
  -e CONFIRM_DEMO_DATA_RESET=reset-fonio-demo-data \
  api python -m app.data.reset_demo
```

Explain that the reset is guarded and transactional.

## 4. Caller context

```bash
curl -sS -X POST http://localhost:5678/webhook/caller-context \
  -H 'Content-Type: application/json' \
  --data '{"conversation_id":"demo-caller-001","phone":"+436601234567"}'
```

Show Anna Müller, the property, and the existing heating ticket. Briefly mention
that `unknown-caller.json` and `ambiguous-caller.json` take safe branches rather
than guessing an identity.

## 5. Normal maintenance and idempotency

```bash
curl -sS -X POST http://localhost:5678/webhook/maintenance-request \
  -H 'Content-Type: application/json' \
  --data @scenarios/normal-maintenance.json
```

Show:

- the n8n execution path;
- the returned ticket;
- one ticket row and one processed-event row;
- API logs carrying the scenario conversation ID.

Send the same command again. Show the same logical result and confirm that the
database still contains only one side effect.

## 6. Emergency fallback

```bash
curl -sS -X POST http://localhost:5678/webhook/emergency-escalation \
  -H 'Content-Type: application/json' \
  --data @scenarios/transfer-failure.json
```

Show the unavailable-contact/failure path, critical ticket, simulated manager
notification, persisted call outcome, and `follow_up_required=true`. Do not
describe the transfer as a real phone call.

## 7. Reliability evidence

Show the automated test result. Explain:

- malformed requests are rejected without writes;
- event IDs make retries safe;
- transient integration failures use bounded retries;
- permanent failures are not retried;
- `/health` and `/ready` distinguish process and database state;
- every request receives a request ID and structured duration log.

The timeout and unavailable CRM fixtures do not inject a runtime failure into
the PostgreSQL-backed caller lookup. Point to
`tests/test_integration_client.py`, where those outcomes are tested with a
deterministic in-memory transport.

## 8. Close

Say:

> The real Fonio integration would replace the input mock with documented
> during-call and post-call actions. The workflow and backend contracts would
> remain unchanged. I have deliberately not claimed that voice, forwarding, or
> notifications were tested through Fonio.
