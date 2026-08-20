from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.properties import service
from app.properties.schemas import EmergencyContact, Property, PropertyManager
from app.data.database import get_db

router = APIRouter(prefix="/properties", tags=["properties"])


@router.get("/{property_id}/emergency-contact", response_model=EmergencyContact)
def get_property_emergency_contact(
    property_id: str, session: Session = Depends(get_db)
) -> EmergencyContact:
    contact = service.get_emergency_contact(property_id, session)
    if contact is None:
        raise HTTPException(status_code=404, detail="Property or emergency contact not found")
    return contact


@router.get("/{property_id}/manager", response_model=PropertyManager)
def get_property_manager(
    property_id: str, session: Session = Depends(get_db)
) -> PropertyManager:
    manager = service.get_manager(property_id, session)
    if manager is None:
        raise HTTPException(status_code=404, detail="Property or manager not found")
    return manager


@router.get("/{property_id}", response_model=Property)
def get_property(
    property_id: str, session: Session = Depends(get_db)
) -> Property:
    property_record = service.get_by_id(property_id, session)
    if property_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property not found",
        )
    return property_record
