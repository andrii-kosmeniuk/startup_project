# Customer Requirements

## Customer and problem

HausPilot Immobilienverwaltung GmbH is a fictional Vienna property-management
company with roughly 35 employees and 2,500 residential units. Its reception
team handles 120–180 calls per day, repeatedly identifying tenants, finding
their buildings and managers, checking maintenance history, routing urgent
calls, and recording outcomes.

The deployment should make an AI phone assistant the first point of contact
without allowing conversational or workflow failures to corrupt the customer
system. Fonio is the intended voice layer; this repository implements and
demonstrates the orchestration and customer-system side of that integration.

## Functional requirements

1. Identify callers by international phone number.
2. Return a unique tenant, possible identities for a shared number, or a safe
   unknown-caller result.
3. Load the tenant's property and open maintenance tickets.
4. Accept structured maintenance requests and map critical severity to
   critical priority.
5. Return an existing matching open ticket instead of creating a duplicate.
6. Find the responsible emergency contact and property manager.
7. Attempt emergency transfer only when a contact is available.
8. Preserve a critical ticket and require follow-up when transfer cannot be
   completed.
9. Store a structured post-call outcome.
10. Avoid duplicate tickets and call outcomes when a webhook is retried.

## Reliability and safety requirements

- Protect business endpoints with a shared API key.
- Reject malformed, inconsistent, or unknown input before producing a side
  effect.
- Correlate workflow and API activity by `conversation_id`.
- Give every API request a request ID and record structured duration logs.
- Require stable event IDs for ticket and call-outcome writes.
- Retry only transient customer-system failures, with finite timeouts and a
  bounded number of attempts.
- Return machine-readable error codes so workflows can choose a safe fallback.
- Keep health and readiness separate so database failure does not make the
  process appear dead.
- Never expose credentials or unnecessary personal data in exports or logs.

## Acceptance criteria

- Docker Compose starts FastAPI, PostgreSQL, and n8n.
- Known, unknown, and ambiguous caller cases produce the expected result.
- Normal maintenance creates or returns the correct ticket.
- Critical requests create or preserve a critical ticket.
- Replaying an event does not duplicate its side effect.
- Reusing an event ID with a different payload is rejected.
- Failed or unavailable emergency transfer produces a follow-up path.
- Post-call processing stores one structured outcome.
- All automated tests pass and all four n8n workflows import cleanly.
- Every supplied scenario has a documented and observable outcome.
- The Fonio-compatible contract is demonstrated with mocked webhook input.

## Demonstration boundary

No real Fonio account is required for this case study. JSON sent to an n8n
webhook represents the structured variables that Fonio would produce during or
after a call. The n8n orchestration, FastAPI requests, validation, PostgreSQL
writes, retries, idempotency, and logs are real local executions.

Voice interaction, telephony transfer, and manager notification are explicitly
simulated. They must not be presented as tested Fonio capabilities. A real
deployment would replace only this mocked boundary after confirming the
customer's Fonio configuration and documented integration surfaces.
