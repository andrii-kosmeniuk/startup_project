# Deployment Playbook

This playbook describes how to adapt the pattern to another customer without
turning the case study into a one-off script.

## 1. Discover the operation

- Interview the call-handling team and system owners.
- Identify caller intents, peak volume, emergency definitions, routing rules,
  after-hours behavior, and ownership of follow-up.
- Write acceptance examples before selecting tools.
- Separate required launch behavior from optional future improvements.

## 2. Map systems and trust boundaries

- Inventory the CRM, ticketing, property, calendar, notification, and identity
  systems involved.
- Confirm documented authentication and rate limits.
- Record which data Fonio can extract during a call and send after a call.
- Do not depend on undocumented or private APIs.
- Decide which data may appear in logs, workflow history, and test fixtures.

## 3. Define contracts

- Assign a stable conversation ID to the complete call.
- Assign a stable event ID to every logical side effect.
- Define request schemas, response schemas, status codes, retryability, and
  error codes.
- Specify how unknown and ambiguous identities are represented.
- Define duplicate detection independently from webhook idempotency.
- Version contracts before changing fields used by active workflows.

## 4. Configure secrets

- Keep local values in `.env`, never in Git.
- Store shared API keys in the workflow platform's credential store.
- Give each environment separate credentials and rotate them through an agreed
  operational process.
- Restrict database and API network exposure to what operators need.

## 5. Adapt orchestration

- Keep validation, transactions, and reusable business rules in the backend.
- Keep customer-specific sequencing and branching in n8n.
- Use small workflows for caller context, primary actions, escalation, and
  post-call processing.
- Give every node a descriptive name and every remote call an explicit error
  path.
- Carry the conversation ID through every request and the event ID through
  retries.

## 6. Set reliability policy

- Set finite connect and read timeouts.
- Retry only network failures and explicitly transient statuses.
- Cap attempts and delays; never create a workflow loop without a limit.
- Make every retried write idempotent at the database boundary.
- Define the final caller-facing outcome before implementing each fallback.
- Keep health checks independent from dependency readiness checks.

## 7. Prepare data

- Use realistic, non-sensitive records for development and acceptance tests.
- Seed only missing canonical records during normal startup.
- Separate ordinary startup from destructive reset behavior.
- Migrate production data with reviewed migrations rather than demo seed code.
- Back up customer data before any destructive operation.

## 8. Validate failures

Test at least:

- known, unknown, and ambiguous callers;
- existing and new tickets;
- duplicate delivery and conflicting event IDs;
- malformed requests and invalid credentials;
- customer-system timeout, connection failure, and permanent rejection;
- unavailable manager or emergency contact;
- failed transfer and duplicate post-call processing;
- database readiness failure.

For each case, inspect the workflow path, API status and body, committed rows,
correlation headers, and logs.

## 9. Connect Fonio

- Preserve the working mock while configuring the documented Fonio action.
- Map real extracted fields to the already tested webhook contract.
- Validate a during-call lookup, one side-effecting action, and the post-call
  callback in a non-production environment.
- Test supported call forwarding only through documented Fonio configuration.
- Remove test triggers only after the real route is proven.
- Record exactly which paths were tested with real telephony.

If account access is unavailable, retain the mock and document the boundary.
Never present simulated voice, transfer, or notification as a production test.

## 10. Acceptance and rollout

- Import sanitized workflows into a clean environment.
- Run the complete scenario suite and automated backend tests.
- Confirm dashboards or logs can trace a conversation end to end.
- Agree on rollback criteria, business hours, and an initial traffic limit.
- Keep the previous routing path available during the first release.
- Obtain customer sign-off on normal and emergency outcomes.

## 11. Operations and ownership

Assign owners for:

- API and workflow credentials;
- n8n workflow changes and exports;
- database backups and migrations;
- customer-system outages;
- emergency-routing rules and contact availability;
- failed-call review and follow-up;
- schema changes and regression tests.

Review timeout policy, contact records, fallback wording, and credentials on a
regular schedule. A deployment is not complete until failures have an owner.

## Local reference procedure

1. Copy `.env.example` to `.env` and replace the local API key.
2. Start with `docker compose up -d --build`.
3. Wait for `http://localhost:8000/ready` to report ready.
4. Open `http://localhost:5678` and import all four workflow JSON files.
5. Create the `Fonio FastAPI API Key` Header Auth credential.
6. Activate the workflows and submit the payloads under `scenarios/`.
7. Inspect n8n execution history, API logs, and PostgreSQL records.
8. Run `pytest` and retain the result with the release notes.

To restore canonical local records:

```bash
docker compose run --rm \
  -e CONFIRM_DEMO_DATA_RESET=reset-fonio-demo-data \
  api python -m app.data.reset_demo
```

This command is destructive for application records in the configured database.
It does not delete Docker volumes or n8n credentials.
