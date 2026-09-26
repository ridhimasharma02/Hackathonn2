"""
StockSense Operations & Atomic Validation Engine (v1)
Handles:
- Receipt, Delivery, Internal Transfer, and Adjustment operations
- Filtering by operation type, status, and warehouse
- Atomic state transitions: DRAFT -> WAITING -> READY -> DONE
- Strict row-level lock & negative stock prevention during validation
"""
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException, status, Depends, Query
from models import (
    db, User, Receipt, ReceiptItem, Delivery, DeliveryItem,
    Transfer, TransferItem, Adjustment, AdjustmentItem,
    Location, Product, Supplier, Customer
)
from services import inventory_service as inv
from services.inventory_service import BusinessRuleError
from services.stock_engine import get_on_hand, get_available
from services.cache_service import cache
from api.v1.schemas import (
    OperationCreate, OperationResponse, OperationItemResponse,
    OperationActionRequest, MessageResponse
)
from api.v1.dependencies import get_current_user, require_manager, require_staff_or_manager

router = APIRouter(prefix="/operations", tags=["Stock Operations"])


def _format_operation(doc_type: str, doc) -> OperationResponse:
    items = []
    source_loc_str = None
    source_loc_id = None
    dest_loc_str = None
    dest_loc_id = None
    partner_name = None

    if doc_type == "RECEIPT":
        source_loc_str = "Vendor / Supplier"
        dest_loc_str = doc.destination_location.code if doc.destination_location else None
        dest_loc_id = doc.destination_location_id
        partner_name = doc.supplier.name if doc.supplier else None
        for item in doc.items:
            items.append(OperationItemResponse(
                id=item.id,
                product_id=item.product_id,
                product_sku=item.product.sku,
                product_name=item.product.name,
                quantity=item.quantity,
                received_quantity=item.received_quantity,
                uom=item.product.uom
            ))

    elif doc_type == "DELIVERY":
        source_loc_str = doc.source_location.code if doc.source_location else None
        source_loc_id = doc.source_location_id
        dest_loc_str = "Customer"
        partner_name = doc.customer.name if doc.customer else None
        for item in doc.items:
            items.append(OperationItemResponse(
                id=item.id,
                product_id=item.product_id,
                product_sku=item.product.sku,
                product_name=item.product.name,
                quantity=item.quantity,
                received_quantity=None,
                uom=item.product.uom
            ))

    elif doc_type == "INTERNAL":
        source_loc_str = doc.source_location.code if doc.source_location else None
        source_loc_id = doc.source_location_id
        dest_loc_str = doc.destination_location.code if doc.destination_location else None
        dest_loc_id = doc.destination_location_id
        partner_name = "Internal Relocation"
        for item in doc.items:
            items.append(OperationItemResponse(
                id=item.id,
                product_id=item.product_id,
                product_sku=item.product.sku,
                product_name=item.product.name,
                quantity=item.quantity,
                received_quantity=None,
                uom=item.product.uom
            ))

    elif doc_type == "ADJUSTMENT":
        source_loc_str = "Physical Count"
        dest_loc_str = "Stock Reconciliation"
        for item in doc.items:
            items.append(OperationItemResponse(
                id=item.id,
                product_id=item.product_id,
                product_sku=item.product.sku,
                product_name=item.product.name,
                quantity=item.counted_quantity if item.counted_quantity is not None else item.system_quantity,
                received_quantity=item.applied_difference,
                uom=item.product.uom
            ))

    return OperationResponse(
        id=doc.id,
        reference=doc.reference,
        operation_type=doc_type,
        status=doc.status.upper(),
        source_location=source_loc_str,
        source_location_id=source_loc_id,
        destination_location=dest_loc_str,
        destination_location_id=dest_loc_id,
        partner_name=partner_name,
        created_at=doc.created_at.isoformat() if hasattr(doc, 'created_at') and doc.created_at else "",
        done_at=doc.done_at.isoformat() if hasattr(doc, 'done_at') and doc.done_at else None,
        items=items,
        notes=getattr(doc, 'notes', None)
    )


@router.get("", response_model=List[OperationResponse])
def list_operations(
    operation_type: Optional[str] = Query(None, description="RECEIPT, DELIVERY, INTERNAL, ADJUSTMENT"),
    status: Optional[str] = Query(None, description="DRAFT, WAITING, READY, DONE, CANCELED"),
    search: Optional[str] = Query(None, description="Search reference or partner"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user)
):
    """
    Filtered query of stock operations by status, type (Receipt, Delivery, Internal, Adjustment),
    and search parameters.
    """
    results: List[OperationResponse] = []
    op_filter = operation_type.upper() if operation_type else None
    stat_filter = status.capitalize() if status else None

    # 1. Receipts
    if not op_filter or op_filter == "RECEIPT":
        q = Receipt.query
        if stat_filter:
            q = q.filter(Receipt.status.ilike(stat_filter))
        if search:
            q = q.filter(Receipt.reference.ilike(f"%{search}%"))
        recs = q.order_by(Receipt.id.desc()).limit(limit).all()
        results.extend([_format_operation("RECEIPT", r) for r in recs])

    # 2. Deliveries
    if not op_filter or op_filter == "DELIVERY":
        q = Delivery.query
        if stat_filter:
            q = q.filter(Delivery.status.ilike(stat_filter))
        if search:
            q = q.filter(Delivery.reference.ilike(f"%{search}%"))
        dels = q.order_by(Delivery.id.desc()).limit(limit).all()
        results.extend([_format_operation("DELIVERY", d) for d in dels])

    # 3. Transfers
    if not op_filter or op_filter == "INTERNAL":
        q = Transfer.query
        if stat_filter:
            q = q.filter(Transfer.status.ilike(stat_filter))
        if search:
            q = q.filter(Transfer.reference.ilike(f"%{search}%"))
        trs = q.order_by(Transfer.id.desc()).limit(limit).all()
        results.extend([_format_operation("INTERNAL", t) for t in trs])

    # 4. Adjustments
    if not op_filter or op_filter == "ADJUSTMENT":
        q = Adjustment.query
        if stat_filter:
            q = q.filter(Adjustment.status.ilike(stat_filter))
        if search:
            q = q.filter(Adjustment.reference.ilike(f"%{search}%"))
        adjs = q.order_by(Adjustment.id.desc()).limit(limit).all()
        results.extend([_format_operation("ADJUSTMENT", a) for a in adjs])

    return results[offset:offset + limit]


@router.post("", response_model=OperationResponse, status_code=status.HTTP_201_CREATED)
def create_operation(
    payload: OperationCreate,
    current_user: User = Depends(require_staff_or_manager)
):
    """
    Creates a new Stock Operation header with line items.
    Types supported: RECEIPT, DELIVERY, INTERNAL, ADJUSTMENT.
    """
    op_type = payload.operation_type.upper().strip()
    items_data = [{'product_id': item.product_id, 'quantity': item.quantity} for item in payload.items]

    try:
        if op_type == "RECEIPT":
            supplier_id = payload.partner_id or 1
            dest_id = payload.destination_location_id
            if not dest_id:
                loc = Location.query.filter_by(type="INTERNAL").first()
                dest_id = loc.id if loc else 1

            receipt = inv.create_receipt(
                supplier_id=supplier_id,
                destination_location_id=dest_id,
                items=items_data,
                source_document=payload.source_document,
                notes=payload.notes,
                user=current_user
            )
            cache.invalidate_kpis()
            return _format_operation("RECEIPT", receipt)

        elif op_type == "DELIVERY":
            customer_id = payload.partner_id or 1
            src_id = payload.source_location_id
            if not src_id:
                loc = Location.query.filter_by(type="INTERNAL").first()
                src_id = loc.id if loc else 1

            delivery = inv.create_delivery(
                customer_id=customer_id,
                source_location_id=src_id,
                items=items_data,
                priority=payload.priority or "Normal",
                source_document=payload.source_document,
                notes=payload.notes,
                user=current_user
            )
            cache.invalidate_kpis()
            return _format_operation("DELIVERY", delivery)

        elif op_type == "INTERNAL":
            if not payload.source_location_id or not payload.destination_location_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Source and destination locations are mandatory for internal transfers."
                )

            transfer = inv.create_transfer(
                source_location_id=payload.source_location_id,
                destination_location_id=payload.destination_location_id,
                items=items_data,
                priority=payload.priority or "Normal",
                reason=payload.notes,
                user=current_user
            )
            cache.invalidate_kpis()
            return _format_operation("INTERNAL", transfer)

        elif op_type == "ADJUSTMENT":
            loc_id = payload.source_location_id
            if not loc_id:
                loc = Location.query.filter_by(type="INTERNAL").first()
                loc_id = loc.id if loc else 1

            adj = inv.create_adjustment(
                title=payload.notes or "Inventory Cycle Count",
                location_id=loc_id,
                items=[{'product_id': it.product_id} for it in payload.items],
                user=current_user
            )
            cache.invalidate_kpis()
            return _format_operation("ADJUSTMENT", adj)

        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported operation type '{payload.operation_type}'"
            )

    except BusinessRuleError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.get("/{id}", response_model=OperationResponse)
def get_operation_detail(
    id: int,
    operation_type: str = Query(..., description="RECEIPT, DELIVERY, INTERNAL, ADJUSTMENT"),
    current_user: User = Depends(get_current_user)
):
    """
    Returns full details, status, line items, and locations for an operation.
    """
    op_type = operation_type.upper().strip()
    if op_type == "RECEIPT":
        doc = Receipt.query.get(id)
    elif op_type == "DELIVERY":
        doc = Delivery.query.get(id)
    elif op_type == "INTERNAL":
        doc = Transfer.query.get(id)
    elif op_type == "ADJUSTMENT":
        doc = Adjustment.query.get(id)
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid operation type '{operation_type}'")

    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{op_type} with ID {id} not found.")

    return _format_operation(op_type, doc)


@router.post("/{id}/validate", response_model=OperationResponse)
def validate_operation(
    id: int,
    operation_type: str = Query(..., description="RECEIPT, DELIVERY, INTERNAL, ADJUSTMENT"),
    current_user: User = Depends(require_staff_or_manager)
):
    """
    Section 4 Atomic Stock Validation Engine:
    Executes atomic state shift from READY to DONE and mutates the double-entry stock ledger.
    Negative stock is strictly prevented via isolated row-level validation.
    """
    op_type = operation_type.upper().strip()

    try:
        if op_type == "RECEIPT":
            # For receipts, if in Waiting status, record receiving to ready it first if not done
            rec = Receipt.query.get_or_404(id)
            if rec.status == "Draft":
                inv.confirm_receipt(rec.id, user=current_user)
            if rec.status == "Waiting":
                recv_dict = {str(it.id): it.quantity for it in rec.items}
                inv.receive_goods(rec.id, recv_dict, user=current_user)
            doc = inv.validate_receipt(id, user=current_user)

        elif op_type == "DELIVERY":
            deliv = Delivery.query.get_or_404(id)
            if deliv.status == "Draft":
                inv.confirm_delivery(deliv.id, user=current_user)
            if deliv.status == "Waiting":
                raise BusinessRuleError(f"Insufficient stock for {deliv.reference}. Available quantity is insufficient for dispatch.")
            if deliv.status == "Ready":
                inv.pick_delivery(deliv.id, user=current_user)
            if deliv.status == "Picked":
                inv.pack_delivery(deliv.id, user=current_user)
            doc = inv.validate_delivery(id, user=current_user)

        elif op_type == "INTERNAL":
            doc = inv.complete_transfer(id, user=current_user)

        elif op_type == "ADJUSTMENT":
            adj = Adjustment.query.get_or_404(id)
            if adj.status == "Draft":
                # Submit count with current on-hand if not already counted
                counts = {}
                for item in adj.items:
                    counts[str(item.id)] = {
                        'counted_quantity': item.counted_quantity or item.system_quantity,
                        'reason': 'Routine cycle check'
                    }
                inv.submit_count(adj.id, counts, user=current_user)
            doc = inv.approve_adjustment(id, user=current_user)

        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid operation type '{operation_type}'")

        # Invalidate KPI cache
        cache.invalidate_kpis()
        return _format_operation(op_type, doc)

    except BusinessRuleError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.post("/{id}/action", response_model=OperationResponse)
def execute_operation_action(
    id: int,
    operation_type: str = Query(..., description="RECEIPT, DELIVERY, INTERNAL, ADJUSTMENT"),
    payload: OperationActionRequest = ...,
    current_user: User = Depends(require_staff_or_manager)
):
    """
    Executes intermediate state transitions (confirm, pick, pack, cancel).
    """
    op_type = operation_type.upper().strip()
    action = payload.action.lower().strip()

    try:
        if op_type == "RECEIPT":
            if action == "confirm":
                doc = inv.confirm_receipt(id, user=current_user)
            elif action == "cancel":
                doc = inv.cancel_receipt(id, user=current_user)
            else:
                raise HTTPException(status_code=400, detail=f"Unsupported action '{action}' for receipt.")

        elif op_type == "DELIVERY":
            if action == "confirm":
                doc = inv.confirm_delivery(id, user=current_user)
            elif action == "pick":
                doc = inv.pick_delivery(id, user=current_user)
            elif action == "pack":
                doc = inv.pack_delivery(id, user=current_user)
            elif action == "cancel":
                doc = inv.cancel_delivery(id, user=current_user)
            else:
                raise HTTPException(status_code=400, detail=f"Unsupported action '{action}' for delivery.")

        elif op_type == "INTERNAL":
            if action == "cancel":
                doc = inv.cancel_transfer(id, user=current_user)
            else:
                raise HTTPException(status_code=400, detail=f"Unsupported action '{action}' for internal transfer.")

        elif op_type == "ADJUSTMENT":
            if action == "cancel":
                doc = inv.cancel_adjustment(id, user=current_user)
            else:
                raise HTTPException(status_code=400, detail=f"Unsupported action '{action}' for adjustment.")

        cache.invalidate_kpis()
        return _format_operation(op_type, doc)

    except BusinessRuleError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
