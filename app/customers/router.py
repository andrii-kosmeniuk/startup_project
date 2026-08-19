from fastapi import APIRouter, HTTPException, status

from app.customers import service
from app.customers.schemas import CustomerLookupResponse
from app.tickets.schemas import Ticket

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("/by-phone/{phone}", response_model=CustomerLookupResponse)
def find_customer_by_phone(phone: str) -> CustomerLookupResponse:
    return service.find_by_phone(phone)


@router.get("/{customer_id}/open-tickets", response_model=list[Ticket])
def get_customer_open_tickets(customer_id: str) -> list[Ticket]:
    if not service.customer_exists(customer_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )
    return service.get_open_tickets(customer_id)
