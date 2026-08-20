from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.data.database import Base, get_db
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


def test_get_property() -> None:
    response = client.get("/properties/property-neubaugasse-17")
    assert response.status_code == 200
    assert response.json()["address"] == "Neubaugasse 17, 1070 Wien"


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
