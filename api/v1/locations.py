"""
StockSense Locations & Warehouses Endpoints (v1)
Supports physical warehouses, internal racks, supplier/vendor locations,
customer locations, and inventory loss locations (Section 3).
"""
from typing import List, Optional
from fastapi import APIRouter, HTTPException, status, Depends, Query
from models import db, Location, Warehouse, User
from api.v1.schemas import LocationCreate, LocationResponse
from api.v1.dependencies import get_current_user, require_manager

router = APIRouter(prefix="/locations", tags=["Locations & Warehouses"])


@router.get("", response_model=List[LocationResponse])
def list_locations(
    type: Optional[str] = Query(None, description="INTERNAL, VENDOR, CUSTOMER, INVENTORY_LOSS"),
    warehouse_id: Optional[int] = None,
    current_user: User = Depends(get_current_user)
):
    """
    Returns list of warehouse and virtual locations.
    """
    query = Location.query.filter_by(active=True)
    if type:
        query = query.filter_by(type=type.upper())
    if warehouse_id:
        query = query.filter_by(warehouse_id=warehouse_id)

    locations = query.order_by(Location.code.asc()).all()
    results = []
    for loc in locations:
        results.append(LocationResponse(
            id=loc.id,
            name=loc.name,
            code=loc.code,
            type=loc.type,
            warehouse_id=loc.warehouse_id,
            warehouse_name=loc.warehouse.name if loc.warehouse else None,
            parent_location_id=loc.parent_location_id,
            active=loc.active
        ))
    return results


@router.post("", response_model=LocationResponse, status_code=status.HTTP_201_CREATED)
def create_location(
    payload: LocationCreate,
    current_user: User = Depends(require_manager)
):
    """
    Creates a new location (Manager role required).
    """
    loc_type = payload.type.upper()
    if loc_type not in ("INTERNAL", "VENDOR", "CUSTOMER", "INVENTORY_LOSS"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Type must be one of: 'INTERNAL', 'VENDOR', 'CUSTOMER', 'INVENTORY_LOSS'."
        )

    code = payload.code.strip().upper()
    existing = Location.query.filter_by(code=code).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Location with code '{code}' already exists."
        )

    location = Location(
        name=payload.name.strip(),
        code=code,
        type=loc_type,
        warehouse_id=payload.warehouse_id,
        parent_location_id=payload.parent_location_id,
        active=True
    )
    db.session.add(location)
    db.session.commit()

    return LocationResponse(
        id=location.id,
        name=location.name,
        code=location.code,
        type=location.type,
        warehouse_id=location.warehouse_id,
        warehouse_name=location.warehouse.name if location.warehouse else None,
        parent_location_id=location.parent_location_id,
        active=location.active
    )
