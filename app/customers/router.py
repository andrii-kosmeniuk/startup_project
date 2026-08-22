from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.customers import service
from app.customers.phone import InvalidPhoneNumberError
from app.customers.schemas import CustomerLookupResponse
from app.tickets.schemas import Ticket
from app.data.database import get_db

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("/by-phone/{phone}", response_model=CustomerLookupResponse)
def find_customer_by_phone(
    phone: str, session: Session = Depends(get_db)
) -> CustomerLookupResponse:
    try:
        return service.find_by_phone(phone, session)
    except InvalidPhoneNumberError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error


@router.get("/{customer_id}/open-tickets", response_model=list[Ticket])
def get_customer_open_tickets(
    customer_id: str, session: Session = Depends(get_db)
) -> list[Ticket]:
    if not service.customer_exists(customer_id, session):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )
    return service.get_open_tickets(customer_id, session)
