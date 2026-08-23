from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.properties import service
from app.properties.schemas import EmergencyContact, Property, PropertyManager
from app.data.database import get_db
from app.security.api_key import require_api_key
from app.errors import ApplicationError

router = APIRouter(
    prefix="/properties",
    tags=["properties"],
    dependencies=[Depends(require_api_key)],
)


@router.get("/{property_id}/emergency-contact", response_model=EmergencyContact)
def get_property_emergency_contact(
    property_id: str, session: Session = Depends(get_db)
) -> EmergencyContact:
    if service.get_by_id(property_id, session) is None:
        raise ApplicationError(
            code="PROPERTY_NOT_FOUND",
            message="Property not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    contact = service.get_emergency_contact(property_id, session)
    if contact is None:
        raise ApplicationError(
            code="EMERGENCY_CONTACT_NOT_FOUND",
            message="Emergency contact not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return contact


@router.get("/{property_id}/manager", response_model=PropertyManager)
def get_property_manager(
    property_id: str, session: Session = Depends(get_db)
) -> PropertyManager:
    if service.get_by_id(property_id, session) is None:
        raise ApplicationError(
            code="PROPERTY_NOT_FOUND",
            message="Property not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    manager = service.get_manager(property_id, session)
    if manager is None:
        raise ApplicationError(
            code="PROPERTY_MANAGER_NOT_FOUND",
            message="Property manager not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return manager


@router.get("/{property_id}", response_model=Property)
def get_property(
    property_id: str, session: Session = Depends(get_db)
) -> Property:
    property_record = service.get_by_id(property_id, session)
    if property_record is None:
        raise ApplicationError(
            code="PROPERTY_NOT_FOUND",
            message="Property not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return property_record
