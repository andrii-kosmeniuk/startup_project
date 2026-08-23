import io
import json
import logging
import os
import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.data.database import Base, get_db
from app.data.models import CallOutcomeRecord, TicketRecord
from app.data.seed import seed_database
from app.security.api_key import validate_api_key_configuration
from app.observability.logging import JsonFormatter, application_logger

TEST_API_KEY = "test-api-key-123456789"
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
client = TestClient(app, headers={"X-API-Key": TEST_API_KEY})
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
    ["/health", "/docs", "/redoc", "/openapi.json"],
)
def test_public_endpoints_do_not_require_api_key(path: str) -> None:
    response = unauthenticated_client.get(path)
    assert response.status_code == 200


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
        "detail": {
            "code": "UNAUTHORIZED",
            "message": "Invalid or missing API key",
            "retryable": False,
        }
    }
    assert response.headers["www-authenticate"] == "ApiKey"


def test_invalid_api_key_is_rejected() -> None:
    response = unauthenticated_client.get(
        "/customers/by-phone/+436601234567",
        headers={"X-API-Key": "incorrect-api-key-value"},
    )
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "UNAUTHORIZED"


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
    assert response.json()["detail"] == expected_detail
    assert test_session.scalar(select(func.count()).select_from(TicketRecord)) == before


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
    assert response.json()["detail"] == (
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
    assert response.json()["detail"] == expected_detail
    assert (
        test_session.scalar(select(func.count()).select_from(CallOutcomeRecord))
        == before
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
