from fastapi import APIRouter, HTTPException, status

from app.properties import service
from app.properties.schemas import Property

router = APIRouter(prefix="/properties", tags=["properties"])


@router.get("/{property_id}", response_model=Property)
def get_property(property_id: str) -> Property:
    property_record = service.get_by_id(property_id)
    if property_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property not found",
        )
    return property_record
