import io
import json
import logging
import os
import re
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.data.database import Base, get_db
from app.data.models import (
    CallOutcomeRecord,
    EmergencyContactRecord,
    ProcessedEventRecord,
    PropertyManagerRecord,
    TicketRecord,
)
from app.data.seed import seed_database
from app.security.api_key import validate_api_key_configuration
from app.observability.logging import JsonFormatter, application_logger
from app.idempotency import service as idempotency_service

TEST_API_KEY = "test-api-key-123456789"
TEST_EVENT_ID = "event-test-default"
os.environ["API_KEY"] = TEST_API_KEY

from app.main import app

test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Base.metadata.create_all(bind=test_engine)
test_session = Session(test_engine, expire_on_commit=False)
seed_database(test_session)


def override_get_db():
    yield test_session


app.dependency_overrides[get_db] = override_get_db
client = TestClient(
    app,
    headers={"X-API-Key": TEST_API_KEY, "X-Event-ID": TEST_EVENT_ID},
)
authenticated_client_without_event = TestClient(
    app, headers={"X-API-Key": TEST_API_KEY}
)
unauthenticated_client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_database():
    global test_session
    test_session.close()
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    test_session = Session(test_engine, expire_on_commit=False)
    seed_database(test_session)
    yield
    test_session.rollback()


@pytest.fixture
def captured_application_logs():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    application_logger.addHandler(handler)
    yield stream
    application_logger.removeHandler(handler)
    handler.close()


def parsed_logs(stream: io.StringIO) -> list[dict[str, object]]:
    return [json.loads(line) for line in stream.getvalue().splitlines()]


def test_health() -> None:
    response = unauthenticated_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize(
    "path",
    ["/health", "/ready", "/docs", "/redoc", "/openapi.json"],
)
def test_public_endpoints_do_not_require_api_key(path: str) -> None:
    response = unauthenticated_client.get(path)
    assert response.status_code == 200


def test_ready_checks_database() -> None:
    response = unauthenticated_client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok"}


def test_ready_returns_structured_503_when_database_is_unavailable(
    captured_application_logs: io.StringIO,
) -> None:
    class UnavailableSession:
        def execute(self, _statement: object) -> None:
            raise OperationalError("SELECT 1", {}, Exception("database offline"))

    def unavailable_database():
        yield UnavailableSession()

    app.dependency_overrides[get_db] = unavailable_database
    try:
        response = unauthenticated_client.get(
            "/ready", headers={"X-Conversation-ID": "conv-ready-failure"}
        )
    finally:
        app.dependency_overrides[get_db] = override_get_db

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "DATABASE_UNAVAILABLE",
            "message": "Database is temporarily unavailable",
            "retryable": True,
            "conversation_id": "conv-ready-failure",
        }
    }
    assert response.headers["x-conversation-id"] == "conv-ready-failure"
    assert "x-request-id" in response.headers
    database_log = next(
        log
        for log in parsed_logs(captured_application_logs)
        if log["event"] == "database_unavailable"
    )
    assert database_log["conversation_id"] == "conv-ready-failure"
    assert database_log["error_type"] == "OperationalError"


def test_health_does_not_access_database() -> None:
    def broken_database():
        raise RuntimeError("Database dependency must not be called")
        yield

    app.dependency_overrides[get_db] = broken_database
    try:
        response = unauthenticated_client.get("/health")
    finally:
        app.dependency_overrides[get_db] = override_get_db
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_unexpected_error_returns_safe_correlated_response(
    captured_application_logs: io.StringIO,
) -> None:
    def broken_database():
        raise RuntimeError("sensitive internal failure")
        yield

    app.dependency_overrides[get_db] = broken_database
    try:
        response = client.get(
            "/properties/property-neubaugasse-17",
            headers={"X-Conversation-ID": "conv-internal-error"},
        )
    finally:
        app.dependency_overrides[get_db] = override_get_db

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "INTERNAL_ERROR",
            "message": "An unexpected error occurred",
            "retryable": False,
            "conversation_id": "conv-internal-error",
        }
    }
    assert "sensitive internal failure" not in response.text
    assert response.headers["x-conversation-id"] == "conv-internal-error"
    assert "x-request-id" in response.headers
    events = [log["event"] for log in parsed_logs(captured_application_logs)]
    assert "http_request_failed" in events
    assert "http_request_completed" in events


def test_unknown_route_uses_structured_error_envelope() -> None:
    response = unauthenticated_client.get(
        "/does-not-exist", headers={"X-Conversation-ID": "conv-not-found"}
    )
    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "NOT_FOUND",
            "message": "Not Found",
            "retryable": False,
            "conversation_id": "conv-not-found",
        }
    }


def test_validation_error_has_sanitized_field_details() -> None:
    response = client.post(
        "/tickets",
        headers={"X-Conversation-ID": "conv-validation"},
        json={
            "customer_id": "customer-anna-mueller",
            "property_id": "property-neubaugasse-17",
            "category": "   ",
            "description": "Heating is not working.",
            "priority": "urgent",
        },
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["message"] == "Request validation failed"
    assert error["retryable"] is False
    assert error["conversation_id"] == "conv-validation"
    assert {"location", "message", "type"} == set(error["details"][0])
    assert all("input" not in detail for detail in error["details"])


def test_domain_error_exposes_stable_code() -> None:
    response = client.get(
        "/customers/unknown-customer/open-tickets",
        headers={"X-Conversation-ID": "conv-domain-error"},
    )
    assert response.status_code == 404
    assert response.json()["error"] == {
        "code": "CUSTOMER_NOT_FOUND",
        "message": "Customer not found",
        "retryable": False,
        "conversation_id": "conv-domain-error",
    }


def test_every_response_has_a_generated_request_id() -> None:
    first = unauthenticated_client.get("/health")
    second = unauthenticated_client.get("/health")
    request_id_pattern = re.compile(r"^req_[0-9a-f]{32}$")

    assert request_id_pattern.fullmatch(first.headers["x-request-id"])
    assert request_id_pattern.fullmatch(second.headers["x-request-id"])
    assert first.headers["x-request-id"] != second.headers["x-request-id"]


def test_conversation_id_is_propagated_and_logged(
    captured_application_logs: io.StringIO,
) -> None:
    response = client.get(
        "/customers/by-phone/+436601234567",
        headers={"X-Conversation-ID": "conv-123"},
    )
    assert response.status_code == 200
    assert response.headers["x-conversation-id"] == "conv-123"

    logs = parsed_logs(captured_application_logs)
    request_log = next(
        log for log in logs if log["event"] == "http_request_completed"
    )
    business_log = next(
        log for log in logs if log["event"] == "customer_lookup_completed"
    )
    assert request_log["conversation_id"] == "conv-123"
    assert request_log["request_id"] == response.headers["x-request-id"]
    assert request_log["method"] == "GET"
    assert request_log["path"] == "/customers/by-phone/+436601234567"
    assert request_log["status_code"] == 200
    assert isinstance(request_log["duration_ms"], (int, float))
    assert request_log["duration_ms"] >= 0
    assert business_log["conversation_id"] == "conv-123"
    assert business_log["request_id"] == response.headers["x-request-id"]
    assert business_log["match_status"] == "unique"
    assert business_log["match_count"] == 1


def test_conversation_id_is_trimmed_before_propagation() -> None:
    response = client.get(
        "/properties/property-neubaugasse-17",
        headers={"X-Conversation-ID": "  conv-trimmed  "},
    )
    assert response.status_code == 200
    assert response.headers["x-conversation-id"] == "conv-trimmed"


@pytest.mark.parametrize("conversation_id", ["", "x" * 101])
def test_invalid_conversation_id_header_is_rejected(
    conversation_id: str,
    captured_application_logs: io.StringIO,
) -> None:
    response = client.get(
        "/customers/by-phone/+436601234567",
        headers={"X-Conversation-ID": conversation_id},
    )
    assert response.status_code == 422
    assert "x-request-id" in response.headers
    logs = parsed_logs(captured_application_logs)
    request_log = next(
        log for log in logs if log["event"] == "http_request_completed"
    )
    assert request_log["status_code"] == 422


def test_unauthorized_request_is_correlated_and_timed(
    captured_application_logs: io.StringIO,
) -> None:
    response = unauthenticated_client.get(
        "/properties/property-neubaugasse-17",
        headers={"X-Conversation-ID": "conv-unauthorized"},
    )
    assert response.status_code == 401
    assert response.headers["x-conversation-id"] == "conv-unauthorized"
    request_log = next(
        log
        for log in parsed_logs(captured_application_logs)
        if log["event"] == "http_request_completed"
    )
    assert request_log["conversation_id"] == "conv-unauthorized"
    assert request_log["status_code"] == 401


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("GET", "/customers/by-phone/+436601234567", None),
        ("GET", "/customers/customer-lukas-huber/open-tickets", None),
        ("GET", "/properties/property-neubaugasse-17", None),
        ("GET", "/properties/property-neubaugasse-17/manager", None),
        ("GET", "/properties/property-neubaugasse-17/emergency-contact", None),
        (
            "POST",
            "/tickets",
            {
                "customer_id": "customer-anna-mueller",
                "property_id": "property-neubaugasse-17",
                "category": "heating",
                "description": "Heating is not working.",
                "priority": "high",
            },
        ),
        (
            "POST",
            "/call-outcomes",
            {
                "conversation_id": "conv-auth-test",
                "intent": "maintenance",
                "summary": "Authentication test.",
            },
        ),
    ],
)
def test_all_business_endpoints_require_api_key(
    method: str, path: str, payload: dict[str, object] | None
) -> None:
    response = unauthenticated_client.request(method, path, json=payload)
    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "UNAUTHORIZED",
            "message": "Invalid or missing API key",
            "retryable": False,
            "conversation_id": None,
        }
    }
    assert response.headers["www-authenticate"] == "ApiKey"


def test_invalid_api_key_is_rejected() -> None:
    response = unauthenticated_client.get(
        "/customers/by-phone/+436601234567",
        headers={"X-API-Key": "incorrect-api-key-value"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_unauthenticated_posts_create_no_side_effects() -> None:
    tickets_before = test_session.scalar(
        select(func.count()).select_from(TicketRecord)
    )
    outcomes_before = test_session.scalar(
        select(func.count()).select_from(CallOutcomeRecord)
    )

    ticket_response = unauthenticated_client.post(
        "/tickets",
        json={
            "customer_id": "customer-anna-mueller",
            "property_id": "property-neubaugasse-17",
            "category": "heating",
            "description": "Heating is not working.",
            "priority": "high",
        },
    )
    outcome_response = unauthenticated_client.post(
        "/call-outcomes",
        json={
            "conversation_id": "conv-unauthorized",
            "intent": "maintenance",
            "summary": "This must not be stored.",
        },
    )

    assert ticket_response.status_code == 401
    assert outcome_response.status_code == 401
    assert (
        test_session.scalar(select(func.count()).select_from(TicketRecord))
        == tickets_before
    )
    assert (
        test_session.scalar(select(func.count()).select_from(CallOutcomeRecord))
        == outcomes_before
    )


@pytest.mark.parametrize("path", ["/tickets", "/call-outcomes"])
def test_side_effect_endpoints_require_event_id(path: str) -> None:
    payload = (
        {
            "customer_id": "customer-anna-mueller",
            "property_id": "property-neubaugasse-17",
            "category": "heating",
            "description": "Heating is not working.",
            "priority": "high",
        }
        if path == "/tickets"
        else {
            "conversation_id": "conv-event-required",
            "intent": "maintenance",
            "summary": "Caller requested help.",
        }
    )
    response = authenticated_client_without_event.post(path, json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert response.json()["error"]["details"][0]["location"] == [
        "header",
        "X-Event-ID",
    ]


@pytest.mark.parametrize("event_id", ["   ", "x" * 101])
def test_event_id_rejects_blank_or_oversized_values(event_id: str) -> None:
    response = client.post(
        "/tickets",
        headers={"X-Event-ID": event_id},
        json={
            "customer_id": "customer-anna-mueller",
            "property_id": "property-neubaugasse-17",
            "category": "heating",
            "description": "Heating is not working.",
            "priority": "high",
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_api_key_header_is_case_insensitive() -> None:
    response = unauthenticated_client.get(
        "/customers/by-phone/+436601234567",
        headers={"x-api-key": TEST_API_KEY},
    )
    assert response.status_code == 200


def test_openapi_documents_api_key_security_scheme() -> None:
    document = unauthenticated_client.get("/openapi.json").json()
    scheme = document["components"]["securitySchemes"]["ApiKeyAuth"]
    assert scheme == {
        "type": "apiKey",
        "description": "Shared API key used by n8n to call FastAPI.",
        "in": "header",
        "name": "X-API-Key",
    }
    assert document["paths"]["/tickets"]["post"]["security"] == [
        {"ApiKeyAuth": []}
    ]
    assert "security" not in document["paths"]["/health"]["get"]
    assert "security" not in document["paths"]["/ready"]["get"]


@pytest.mark.parametrize("configured_value", [None, "", "short-key", " " * 20])
def test_invalid_api_key_configuration_fails_fast(
    monkeypatch: pytest.MonkeyPatch, configured_value: str | None
) -> None:
    if configured_value is None:
        monkeypatch.delenv("API_KEY", raising=False)
    else:
        monkeypatch.setenv("API_KEY", configured_value)
    with pytest.raises(RuntimeError, match="API_KEY must be configured"):
        validate_api_key_configuration()


def test_known_phone_returns_one_customer() -> None:
    response = client.get("/customers/by-phone/+436601234567")
    assert response.status_code == 200
    assert response.json()["status"] == "unique"
    assert response.json()["count"] == 1
    assert response.json()["customers"][0]["first_name"] == "Anna"


@pytest.mark.parametrize(
    "phone",
    [
        "+43 660 123 45 67",
        "+43 (660) 123-45-67",
        "00436601234567",
    ],
)
def test_phone_lookup_normalizes_common_international_formats(phone: str) -> None:
    response = client.get(f"/customers/by-phone/{phone}")
    assert response.status_code == 200
    assert response.json()["status"] == "unique"
    assert response.json()["customers"][0]["id"] == "customer-anna-mueller"


@pytest.mark.parametrize(
    "phone",
    ["6601234567", "+0123456789", "+43ABC12345", "+43123", "+" + "1" * 16],
)
def test_phone_lookup_rejects_invalid_phone_numbers(phone: str) -> None:
    response = client.get(f"/customers/by-phone/{phone}")
    assert response.status_code == 422


def test_unknown_phone_returns_zero_customers() -> None:
    response = client.get("/customers/by-phone/+430000000000")
    assert response.status_code == 200
    assert response.json() == {
        "status": "not_found",
        "count": 0,
        "customers": [],
    }


def test_shared_phone_returns_multiple_customers() -> None:
    response = client.get("/customers/by-phone/+436601111111")
    assert response.status_code == 200
    assert response.json()["status"] == "ambiguous"
    assert response.json()["count"] == 2


def test_get_open_tickets_excludes_closed_tickets() -> None:
    response = client.get("/customers/customer-lukas-huber/open-tickets")
    assert response.status_code == 200
    assert [ticket["id"] for ticket in response.json()] == ["ticket-1"]


def test_open_ticket_lookup_rejects_unknown_customer() -> None:
    response = client.get("/customers/unknown-customer/open-tickets")
    assert response.status_code == 404


def test_create_valid_ticket() -> None:
    response = client.post(
        "/tickets",
        json={
            "customer_id": "customer-anna-mueller",
            "property_id": "property-neubaugasse-17",
            "category": "electrical",
            "description": "The hallway light is flickering.",
            "priority": "medium",
        },
    )
    assert response.status_code == 201
    assert response.json()["status"] == "open"
    assert response.json()["customer_id"] == "customer-anna-mueller"


def test_create_critical_ticket() -> None:
    response = client.post(
        "/tickets",
        json={
            "customer_id": "customer-anna-mueller",
            "property_id": "property-neubaugasse-17",
            "category": "water_leak",
            "description": "Water is pouring through the ceiling.",
            "priority": "critical",
        },
    )
    assert response.status_code == 201
    assert response.json()["priority"] == "critical"


def test_existing_open_ticket_is_returned_instead_of_creating_duplicate(
    captured_application_logs: io.StringIO,
) -> None:
    tickets_before = test_session.scalar(
        select(func.count()).select_from(TicketRecord)
    )
    response = client.post(
        "/tickets",
        headers={
            "X-Event-ID": "event-existing-ticket",
            "X-Conversation-ID": "conv-existing-ticket",
        },
        json={
            "customer_id": "customer-lukas-huber",
            "property_id": "property-landstrasser-42",
            "category": "plumbing",
            "description": "The kitchen sink is still leaking.",
            "priority": "high",
        },
    )
    assert response.status_code == 200
    assert response.json()["id"] == "ticket-1"
    assert response.json()["priority"] == "high"
    assert response.headers["x-existing-ticket"] == "true"
    assert "x-idempotent-replay" not in response.headers
    assert (
        test_session.scalar(select(func.count()).select_from(TicketRecord))
        == tickets_before
    )
    event = test_session.get(ProcessedEventRecord, "event-existing-ticket")
    assert event is not None
    assert event.response_status == 200
    assert event.result_reference == "ticket-1"
    events = [log["event"] for log in parsed_logs(captured_application_logs)]
    assert "existing_ticket_priority_escalated" in events
    assert "existing_ticket_found" in events


def test_existing_ticket_result_is_idempotently_replayed() -> None:
    payload = {
        "customer_id": "customer-lukas-huber",
        "property_id": "property-landstrasser-42",
        "category": "plumbing",
        "description": "The kitchen sink is still leaking.",
        "priority": "medium",
    }
    headers = {"X-Event-ID": "event-existing-replay"}
    first = client.post("/tickets", headers=headers, json=payload)
    second = client.post("/tickets", headers=headers, json=payload)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert first.headers["x-existing-ticket"] == "true"
    assert second.headers["x-existing-ticket"] == "true"
    assert second.headers["x-idempotent-replay"] == "true"


def test_different_event_ids_still_return_one_existing_ticket() -> None:
    payload = {
        "customer_id": "customer-lukas-huber",
        "property_id": "property-landstrasser-42",
        "category": "plumbing",
        "description": "The kitchen sink is still leaking.",
        "priority": "medium",
    }
    first = client.post(
        "/tickets", headers={"X-Event-ID": "event-report-one"}, json=payload
    )
    second = client.post(
        "/tickets", headers={"X-Event-ID": "event-report-two"}, json=payload
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"] == "ticket-1"
    assert (
        test_session.scalar(select(func.count()).select_from(TicketRecord)) == 2
    )


def test_closed_ticket_does_not_prevent_new_ticket_creation() -> None:
    response = client.post(
        "/tickets",
        headers={"X-Event-ID": "event-after-closed-ticket"},
        json={
            "customer_id": "customer-lukas-huber",
            "property_id": "property-landstrasser-42",
            "category": "heating",
            "description": "The heating stopped again.",
            "priority": "high",
        },
    )
    assert response.status_code == 201
    assert response.json()["id"] != "ticket-2"
    assert response.json()["status"] == "open"
    assert "x-existing-ticket" not in response.headers


def test_existing_ticket_matching_is_scoped_by_category() -> None:
    response = client.post(
        "/tickets",
        headers={"X-Event-ID": "event-different-category"},
        json={
            "customer_id": "customer-lukas-huber",
            "property_id": "property-landstrasser-42",
            "category": "electrical",
            "description": "The hallway light is out.",
            "priority": "medium",
        },
    )
    assert response.status_code == 201
    assert response.json()["category"] == "electrical"


def test_critical_duplicate_escalates_existing_ticket_to_critical() -> None:
    response = client.post(
        "/tickets",
        headers={"X-Event-ID": "event-critical-escalation"},
        json={
            "customer_id": "customer-lukas-huber",
            "property_id": "property-landstrasser-42",
            "category": "plumbing",
            "description": "The leak has become severe.",
            "priority": "critical",
        },
    )
    assert response.status_code == 200
    assert response.json()["id"] == "ticket-1"
    assert response.json()["priority"] == "critical"
    assert test_session.get(TicketRecord, "ticket-1").priority == "critical"


def test_duplicate_ticket_event_replays_original_result(
    captured_application_logs: io.StringIO,
) -> None:
    payload = {
        "customer_id": "customer-anna-mueller",
        "property_id": "property-neubaugasse-17",
        "category": "heating",
        "description": "Heating stopped during the night.",
        "priority": "high",
    }
    headers = {
        "X-Event-ID": "event-ticket-duplicate",
        "X-Conversation-ID": "conv-ticket-duplicate",
    }
    tickets_before = test_session.scalar(
        select(func.count()).select_from(TicketRecord)
    )

    first = client.post("/tickets", headers=headers, json=payload)
    second = client.post("/tickets", headers=headers, json=payload)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json() == second.json()
    assert "x-idempotent-replay" not in first.headers
    assert second.headers["x-idempotent-replay"] == "true"
    assert second.headers["x-event-id"] == "event-ticket-duplicate"
    assert (
        test_session.scalar(select(func.count()).select_from(TicketRecord))
        == tickets_before + 1
    )
    event = test_session.get(ProcessedEventRecord, "event-ticket-duplicate")
    assert event is not None
    assert event.operation == "create_ticket"
    assert event.status == "completed"
    assert event.response_status == 201
    assert event.result_reference == first.json()["id"]
    replay_log = next(
        log
        for log in parsed_logs(captured_application_logs)
        if log["event"] == "duplicate_event_replayed"
    )
    assert replay_log["event_id"] == "event-ticket-duplicate"
    assert replay_log["conversation_id"] == "conv-ticket-duplicate"
    assert sum(
        log["event"] == "ticket_created"
        for log in parsed_logs(captured_application_logs)
    ) == 1


def test_event_id_reuse_with_changed_payload_is_rejected() -> None:
    headers = {"X-Event-ID": "event-payload-mismatch"}
    payload = {
        "customer_id": "customer-anna-mueller",
        "property_id": "property-neubaugasse-17",
        "category": "heating",
        "description": "Heating is not working.",
        "priority": "high",
    }
    first = client.post("/tickets", headers=headers, json=payload)
    changed_payload = {**payload, "description": "A different problem."}
    second = client.post("/tickets", headers=headers, json=changed_payload)

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["error"] == {
        "code": "IDEMPOTENCY_KEY_REUSED",
        "message": "X-Event-ID was already used for a different request",
        "retryable": False,
        "conversation_id": None,
    }
    matching_tickets = test_session.scalars(
        select(TicketRecord).where(
            TicketRecord.id == first.json()["id"]
        )
    ).all()
    assert len(matching_tickets) == 1


def test_event_id_reuse_across_operations_is_rejected() -> None:
    event_id = "event-cross-operation"
    ticket_response = client.post(
        "/tickets",
        headers={"X-Event-ID": event_id},
        json={
            "customer_id": "customer-anna-mueller",
            "property_id": "property-neubaugasse-17",
            "category": "heating",
            "description": "Heating is not working.",
            "priority": "high",
        },
    )
    outcome_response = client.post(
        "/call-outcomes",
        headers={"X-Event-ID": event_id},
        json={
            "conversation_id": "conv-cross-operation",
            "intent": "maintenance",
            "summary": "Caller reported a heating problem.",
        },
    )
    assert ticket_response.status_code == 201
    assert outcome_response.status_code == 409
    assert outcome_response.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert (
        test_session.scalar(select(func.count()).select_from(CallOutcomeRecord)) == 0
    )


def test_event_still_processing_returns_retryable_conflict() -> None:
    payload = {
        "customer_id": "customer-anna-mueller",
        "property_id": "property-neubaugasse-17",
        "category": "heating",
        "description": "Heating is not working.",
        "priority": "high",
    }
    test_session.add(
        ProcessedEventRecord(
            event_id="event-processing",
            operation="create_ticket",
            request_hash=idempotency_service.request_hash(payload),
            status="processing",
            response_status=None,
            response_body=None,
            result_reference=None,
            processed_at=datetime.now(timezone.utc),
        )
    )
    test_session.commit()

    response = client.post(
        "/tickets",
        headers={"X-Event-ID": "event-processing"},
        json=payload,
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EVENT_PROCESSING"
    assert response.json()["error"]["retryable"] is True


def test_failed_ticket_transaction_rolls_back_event_and_side_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tickets_before = test_session.scalar(
        select(func.count()).select_from(TicketRecord)
    )

    def fail_completion(**_kwargs: object) -> None:
        raise RuntimeError("simulated completion failure")

    monkeypatch.setattr(idempotency_service, "complete_event", fail_completion)
    response = client.post(
        "/tickets",
        headers={"X-Event-ID": "event-rollback"},
        json={
            "customer_id": "customer-anna-mueller",
            "property_id": "property-neubaugasse-17",
            "category": "heating",
            "description": "Heating is not working.",
            "priority": "high",
        },
    )
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert test_session.get(ProcessedEventRecord, "event-rollback") is None
    assert (
        test_session.scalar(select(func.count()).select_from(TicketRecord))
        == tickets_before
    )

    monkeypatch.undo()
    retry = client.post(
        "/tickets",
        headers={"X-Event-ID": "event-rollback"},
        json={
            "customer_id": "customer-anna-mueller",
            "property_id": "property-neubaugasse-17",
            "category": "heating",
            "description": "Heating is not working.",
            "priority": "high",
        },
    )
    assert retry.status_code == 201
    assert test_session.get(ProcessedEventRecord, "event-rollback") is not None
    assert (
        test_session.scalar(select(func.count()).select_from(TicketRecord))
        == tickets_before + 1
    )


@pytest.mark.parametrize("field", ["customer_id", "property_id", "category", "description"])
def test_ticket_rejects_blank_required_strings(field: str) -> None:
    payload = {
        "customer_id": "customer-anna-mueller",
        "property_id": "property-neubaugasse-17",
        "category": "heating",
        "description": "Heating is not working.",
        "priority": "high",
    }
    payload[field] = "   "
    before = test_session.scalar(select(func.count()).select_from(TicketRecord))

    response = client.post("/tickets", json=payload)

    assert response.status_code == 422
    after = test_session.scalar(select(func.count()).select_from(TicketRecord))
    assert after == before


def test_ticket_rejects_unknown_fields_without_side_effect() -> None:
    before = test_session.scalar(select(func.count()).select_from(TicketRecord))
    response = client.post(
        "/tickets",
        json={
            "customer_id": "customer-anna-mueller",
            "property_id": "property-neubaugasse-17",
            "category": "heating",
            "description": "Heating is not working.",
            "priority": "high",
            "severity": "critical",
        },
    )
    assert response.status_code == 422
    assert test_session.scalar(select(func.count()).select_from(TicketRecord)) == before


def test_ticket_rejects_invalid_priority() -> None:
    response = client.post(
        "/tickets",
        json={
            "customer_id": "customer-anna-mueller",
            "property_id": "property-neubaugasse-17",
            "category": "heating",
            "description": "Heating is not working.",
            "priority": "urgent",
        },
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    ("customer_id", "property_id", "expected_detail"),
    [
        ("unknown", "property-neubaugasse-17", "Customer not found"),
        ("customer-anna-mueller", "unknown", "Property not found"),
        (
            "customer-anna-mueller",
            "property-landstrasser-42",
            "Customer does not belong to this property",
        ),
    ],
)
def test_ticket_rejects_invalid_database_references(
    customer_id: str, property_id: str, expected_detail: str
) -> None:
    before = test_session.scalar(select(func.count()).select_from(TicketRecord))
    response = client.post(
        "/tickets",
        json={
            "customer_id": customer_id,
            "property_id": property_id,
            "category": "heating",
            "description": "Heating is not working.",
            "priority": "high",
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["message"] == expected_detail
    assert test_session.scalar(select(func.count()).select_from(TicketRecord)) == before
    assert (
        test_session.scalar(select(func.count()).select_from(ProcessedEventRecord))
        == 0
    )


def test_get_property() -> None:
    response = client.get("/properties/property-neubaugasse-17")
    assert response.status_code == 200
    assert response.json()["address"] == "Neubaugasse 17, 1070 Wien"


@pytest.mark.parametrize(
    "path",
    [
        "/properties/unknown",
        "/properties/unknown/manager",
        "/properties/unknown/emergency-contact",
    ],
)
def test_property_endpoints_return_404_for_unknown_property(path: str) -> None:
    response = client.get(path)
    assert response.status_code == 404


def test_get_property_manager() -> None:
    response = client.get("/properties/property-neubaugasse-17/manager")
    assert response.status_code == 200
    assert response.json()["first_name"] == "Lukas"
    assert response.json()["available"] is True


def test_get_property_emergency_contact() -> None:
    response = client.get("/properties/property-neubaugasse-17/emergency-contact")
    assert response.status_code == 200
    assert response.json()["id"] == "emergency-1"


def test_unavailable_property_manager_returns_retryable_503() -> None:
    response = client.get(
        "/properties/property-landstrasser-42/manager",
        headers={"X-Conversation-ID": "conv-manager-unavailable"},
    )
    assert response.status_code == 503
    assert response.json()["error"] == {
        "code": "MANAGER_UNAVAILABLE",
        "message": "Property manager is currently unavailable",
        "retryable": True,
        "conversation_id": "conv-manager-unavailable",
    }


def test_unavailable_emergency_contact_returns_retryable_503() -> None:
    response = client.get(
        "/properties/property-landstrasser-42/emergency-contact",
        headers={"X-Conversation-ID": "conv-contact-unavailable"},
    )
    assert response.status_code == 503
    assert response.json()["error"] == {
        "code": "EMERGENCY_CONTACT_UNAVAILABLE",
        "message": "Emergency contact is currently unavailable",
        "retryable": True,
        "conversation_id": "conv-contact-unavailable",
    }


def test_missing_linked_manager_is_distinct_from_unavailable_manager() -> None:
    manager = test_session.get(PropertyManagerRecord, "manager-1")
    assert manager is not None
    test_session.delete(manager)
    test_session.commit()
    response = client.get("/properties/property-neubaugasse-17/manager")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PROPERTY_MANAGER_NOT_FOUND"
    assert response.json()["error"]["retryable"] is False


def test_missing_linked_contact_is_distinct_from_unavailable_contact() -> None:
    contact = test_session.get(EmergencyContactRecord, "emergency-1")
    assert contact is not None
    test_session.delete(contact)
    test_session.commit()
    response = client.get(
        "/properties/property-neubaugasse-17/emergency-contact"
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "EMERGENCY_CONTACT_NOT_FOUND"
    assert response.json()["error"]["retryable"] is False


def test_create_call_outcome() -> None:
    response = client.post(
        "/call-outcomes",
        json={
            "conversation_id": "conv-123",
            "customer_id": "customer-lukas-huber",
            "intent": "maintenance",
            "ticket_id": "ticket-1",
            "transfer_attempted": True,
            "transfer_success": False,
            "follow_up_required": True,
            "summary": "Tenant reported a leaking kitchen sink.",
        },
    )
    assert response.status_code == 201
    assert response.json()["conversation_id"] == "conv-123"
    assert response.json()["follow_up_required"] is True


def test_duplicate_call_outcome_event_replays_original_result() -> None:
    payload = {
        "conversation_id": "conv-outcome-duplicate",
        "customer_id": "customer-lukas-huber",
        "intent": "maintenance",
        "ticket_id": "ticket-1",
        "transfer_attempted": False,
        "transfer_success": False,
        "follow_up_required": True,
        "summary": "Tenant reported a leaking kitchen sink.",
    }
    headers = {
        "X-Event-ID": "event-outcome-duplicate",
        "X-Conversation-ID": "conv-outcome-duplicate",
    }
    first = client.post("/call-outcomes", headers=headers, json=payload)
    second = client.post("/call-outcomes", headers=headers, json=payload)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json() == second.json()
    assert second.headers["x-idempotent-replay"] == "true"
    assert second.headers["x-event-id"] == "event-outcome-duplicate"
    assert (
        test_session.scalar(select(func.count()).select_from(CallOutcomeRecord)) == 1
    )
    event = test_session.get(ProcessedEventRecord, "event-outcome-duplicate")
    assert event is not None
    assert event.operation == "create_call_outcome"
    assert event.result_reference == first.json()["id"]


def test_call_outcome_event_reuse_with_changed_payload_is_rejected() -> None:
    headers = {"X-Event-ID": "event-outcome-payload-mismatch"}
    payload = {
        "conversation_id": "conv-outcome-payload-mismatch",
        "intent": "maintenance",
        "summary": "Original summary.",
    }
    first = client.post("/call-outcomes", headers=headers, json=payload)
    second = client.post(
        "/call-outcomes",
        headers=headers,
        json={**payload, "summary": "Changed summary."},
    )
    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert (
        test_session.scalar(select(func.count()).select_from(CallOutcomeRecord)) == 1
    )


def add_critical_ticket(ticket_id: str = "ticket-critical-test") -> TicketRecord:
    ticket = TicketRecord(
        id=ticket_id,
        customer_id="customer-anna-mueller",
        property_id="property-neubaugasse-17",
        category="water_leak",
        description="Water is pouring through the ceiling.",
        priority="critical",
        status="open",
    )
    test_session.add(ticket)
    test_session.commit()
    return ticket


def test_unresolved_emergency_with_critical_ticket_and_followup_is_saved() -> None:
    ticket = add_critical_ticket()
    response = client.post(
        "/call-outcomes",
        headers={
            "X-Event-ID": "event-emergency-fallback",
            "X-Conversation-ID": "conv-emergency-fallback",
        },
        json={
            "conversation_id": "conv-emergency-fallback",
            "customer_id": "customer-anna-mueller",
            "intent": "emergency",
            "ticket_id": ticket.id,
            "transfer_attempted": True,
            "transfer_success": False,
            "follow_up_required": True,
            "summary": "Transfer failed; critical follow-up is required.",
        },
    )
    assert response.status_code == 201
    assert response.json()["ticket_id"] == ticket.id
    assert response.json()["transfer_success"] is False
    assert response.json()["follow_up_required"] is True


def test_unavailable_contact_fallback_can_be_saved_without_transfer_attempt() -> None:
    ticket = add_critical_ticket()
    response = client.post(
        "/call-outcomes",
        headers={"X-Event-ID": "event-contact-fallback"},
        json={
            "conversation_id": "conv-contact-fallback",
            "customer_id": "customer-anna-mueller",
            "intent": "emergency",
            "ticket_id": ticket.id,
            "transfer_attempted": False,
            "transfer_success": False,
            "follow_up_required": True,
            "summary": "Emergency contact unavailable; manager follow-up required.",
        },
    )
    assert response.status_code == 201
    assert response.json()["transfer_attempted"] is False
    assert response.json()["follow_up_required"] is True


def test_unresolved_emergency_requires_followup() -> None:
    ticket = add_critical_ticket()
    response = client.post(
        "/call-outcomes",
        headers={"X-Event-ID": "event-missing-followup"},
        json={
            "conversation_id": "conv-missing-followup",
            "customer_id": "customer-anna-mueller",
            "intent": "emergency",
            "ticket_id": ticket.id,
            "transfer_attempted": True,
            "transfer_success": False,
            "follow_up_required": False,
            "summary": "Transfer failed.",
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "EMERGENCY_FOLLOW_UP_REQUIRED"
    assert (
        test_session.scalar(select(func.count()).select_from(CallOutcomeRecord)) == 0
    )
    assert test_session.get(ProcessedEventRecord, "event-missing-followup") is None


@pytest.mark.parametrize("ticket_id", [None, "ticket-1"])
def test_unresolved_emergency_requires_critical_ticket(
    ticket_id: str | None,
) -> None:
    response = client.post(
        "/call-outcomes",
        headers={"X-Event-ID": f"event-noncritical-{ticket_id or 'none'}"},
        json={
            "conversation_id": "conv-critical-required",
            "customer_id": (
                "customer-lukas-huber" if ticket_id else "customer-anna-mueller"
            ),
            "intent": "emergency",
            "ticket_id": ticket_id,
            "transfer_attempted": True,
            "transfer_success": False,
            "follow_up_required": True,
            "summary": "Emergency transfer failed.",
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "CRITICAL_TICKET_REQUIRED"
    assert (
        test_session.scalar(select(func.count()).select_from(CallOutcomeRecord)) == 0
    )


def test_successful_emergency_transfer_does_not_require_fallback_ticket() -> None:
    response = client.post(
        "/call-outcomes",
        headers={"X-Event-ID": "event-successful-emergency-transfer"},
        json={
            "conversation_id": "conv-successful-emergency-transfer",
            "customer_id": "customer-anna-mueller",
            "intent": "emergency",
            "transfer_attempted": True,
            "transfer_success": True,
            "follow_up_required": False,
            "summary": "Caller was transferred to the emergency contact.",
        },
    )
    assert response.status_code == 201
    assert response.json()["transfer_success"] is True
    assert response.json()["ticket_id"] is None


def test_call_outcome_accepts_matching_conversation_header() -> None:
    response = client.post(
        "/call-outcomes",
        headers={"X-Conversation-ID": "conv-matching"},
        json={
            "conversation_id": "conv-matching",
            "intent": "maintenance",
            "summary": "Caller reported a maintenance issue.",
        },
    )
    assert response.status_code == 201
    assert response.headers["x-conversation-id"] == "conv-matching"


def test_call_outcome_rejects_mismatched_conversation_header_without_side_effect() -> None:
    before = test_session.scalar(
        select(func.count()).select_from(CallOutcomeRecord)
    )
    response = client.post(
        "/call-outcomes",
        headers={"X-Conversation-ID": "conv-header"},
        json={
            "conversation_id": "conv-body",
            "intent": "maintenance",
            "summary": "Caller reported a maintenance issue.",
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["message"] == (
        "X-Conversation-ID must match body conversation_id"
    )
    assert (
        test_session.scalar(select(func.count()).select_from(CallOutcomeRecord))
        == before
    )


def test_side_effect_logs_include_business_result_and_correlation(
    captured_application_logs: io.StringIO,
) -> None:
    response = client.post(
        "/tickets",
        headers={"X-Conversation-ID": "conv-ticket-log"},
        json={
            "customer_id": "customer-anna-mueller",
            "property_id": "property-neubaugasse-17",
            "category": "water_leak",
            "description": "Water is entering the apartment.",
            "priority": "critical",
        },
    )
    assert response.status_code == 201
    ticket_log = next(
        log
        for log in parsed_logs(captured_application_logs)
        if log["event"] == "ticket_created"
    )
    assert ticket_log["conversation_id"] == "conv-ticket-log"
    assert ticket_log["request_id"] == response.headers["x-request-id"]
    assert ticket_log["ticket_id"] == response.json()["id"]
    assert ticket_log["priority"] == "critical"


@pytest.mark.parametrize("field", ["conversation_id", "intent", "summary"])
def test_call_outcome_rejects_blank_required_strings(field: str) -> None:
    payload = {
        "conversation_id": "conv-123",
        "intent": "maintenance",
        "transfer_attempted": False,
        "transfer_success": False,
        "follow_up_required": False,
        "summary": "Caller requested help.",
    }
    payload[field] = "   "
    before = test_session.scalar(select(func.count()).select_from(CallOutcomeRecord))
    response = client.post("/call-outcomes", json=payload)
    assert response.status_code == 422
    assert (
        test_session.scalar(select(func.count()).select_from(CallOutcomeRecord))
        == before
    )


def test_call_outcome_rejects_success_without_transfer_attempt() -> None:
    response = client.post(
        "/call-outcomes",
        json={
            "conversation_id": "conv-123",
            "intent": "emergency",
            "transfer_attempted": False,
            "transfer_success": True,
            "follow_up_required": False,
            "summary": "Emergency transfer succeeded.",
        },
    )
    assert response.status_code == 422


def test_call_outcome_rejects_coerced_boolean_values() -> None:
    response = client.post(
        "/call-outcomes",
        json={
            "conversation_id": "conv-123",
            "intent": "maintenance",
            "transfer_attempted": "false",
            "summary": "Caller requested help.",
        },
    )
    assert response.status_code == 422


def test_call_outcome_rejects_unknown_fields() -> None:
    response = client.post(
        "/call-outcomes",
        json={
            "conversation_id": "conv-123",
            "intent": "maintenance",
            "summary": "Caller requested help.",
            "unexpected": "value",
        },
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    ("customer_id", "ticket_id", "expected_detail"),
    [
        ("unknown", None, "Customer not found"),
        (None, "unknown", "Ticket not found"),
        (
            "customer-anna-mueller",
            "ticket-1",
            "Ticket does not belong to this customer",
        ),
    ],
)
def test_call_outcome_rejects_invalid_references(
    customer_id: str | None, ticket_id: str | None, expected_detail: str
) -> None:
    payload = {
        "conversation_id": "conv-123",
        "customer_id": customer_id,
        "intent": "maintenance",
        "ticket_id": ticket_id,
        "summary": "Caller requested help.",
    }
    before = test_session.scalar(select(func.count()).select_from(CallOutcomeRecord))
    response = client.post("/call-outcomes", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["message"] == expected_detail
    assert (
        test_session.scalar(select(func.count()).select_from(CallOutcomeRecord))
        == before
    )
    assert (
        test_session.scalar(select(func.count()).select_from(ProcessedEventRecord))
        == 0
    )


def test_malformed_json_is_rejected_without_side_effect() -> None:
    before = test_session.scalar(select(func.count()).select_from(TicketRecord))
    response = client.post(
        "/tickets",
        content=b'{"customer_id":',
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert test_session.scalar(select(func.count()).select_from(TicketRecord)) == before
