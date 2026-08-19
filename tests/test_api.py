from fastapi.testclient import TestClient

from app.main import app

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


def test_get_property() -> None:
    response = client.get("/properties/property-neubaugasse-17")
    assert response.status_code == 200
    assert response.json()["address"] == "Neubaugasse 17, 1070 Wien"
