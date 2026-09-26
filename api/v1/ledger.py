"""
StockSense Stock Ledger & Moves Endpoints (v1)
Provides audit trail pagination of immutable double-entry stock moves.
"""
from typing import Optional
from fastapi import APIRouter, Depends, Query
from models import db, StockMovement, User
from api.v1.schemas import LedgerPageResponse, LedgerMoveResponse
from api.v1.dependencies import get_current_user

router = APIRouter(prefix="/ledger", tags=["Stock Ledger"])


@router.get("/moves", response_model=LedgerPageResponse)
def get_ledger_moves(
    product_id: Optional[int] = Query(None, description="Filter by product ID"),
    location_id: Optional[int] = Query(None, description="Filter by location ID (source or destination)"),
    operation: Optional[str] = Query(None, description="Filter by operation type"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    current_user: User = Depends(get_current_user)
):
    """
    Audit trail pagination of historical double-entry ledger move records.
    Every row represents an immutable movement between source and destination locations.
    """
    query = StockMovement.query

    if product_id:
        query = query.filter(StockMovement.product_id == product_id)

    if location_id:
        query = query.filter(
            db.or_(
                StockMovement.from_location_id == location_id,
                StockMovement.to_location_id == location_id
            )
        )

    if operation:
        query = query.filter(StockMovement.operation.ilike(f"%{operation}%"))

    total = query.count()
    total_pages = max(1, (total + page_size - 1) // page_size)

    offset = (page - 1) * page_size
    records = query.order_by(StockMovement.id.desc()).offset(offset).limit(page_size).all()

    moves = []
    for r in records:
        moves.append(LedgerMoveResponse(
            id=r.id,
            reference=r.reference,
            operation=r.operation,
            product_id=r.product_id,
            product_sku=r.product.sku if r.product else "N/A",
            product_name=r.product.name if r.product else "Unknown",
            quantity=r.quantity,
            uom=r.product.uom if r.product else "unit",
            source_location=r.from_location.code if r.from_location else None,
            destination_location=r.to_location.code if r.to_location else None,
            counterparty=r.counterparty,
            user_name=r.user.name if r.user else "System",
            at=r.at.isoformat() if r.at else ""
        ))

    return LedgerPageResponse(
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        moves=moves
    )
