import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.data.database import Base, get_db
from app.data.models import CallOutcomeRecord, TicketRecord
from app.data.seed import seed_database
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
client = TestClient(app)


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


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


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
