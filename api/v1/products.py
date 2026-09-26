"""
StockSense Products & Inventory Matrix Endpoints (v1)
Handles:
- Product catalog queries with dynamically computed stock & status
- Location stock matrix (snapshot of stock per rack/warehouse)
- Product creation with optional initial opening stock
- Product modifications (reorder levels, UOM, category)
"""
from typing import List, Optional
from fastapi import APIRouter, HTTPException, status, Depends, Query
from models import db, Product, Category, Location, User
from services import inventory_service as inv
from services.inventory_service import BusinessRuleError
from services.stock_engine import (
    get_on_hand, get_available, get_reserved, get_status, get_product_stock_matrix
)
from services.cache_service import cache
from api.v1.schemas import (
    ProductCreate, ProductUpdate, ProductResponse,
    ProductDetailResponse, LocationStockMatrixItem
)
from api.v1.dependencies import get_current_user, require_manager

router = APIRouter(prefix="/products", tags=["Products"])


def _format_product(p: Product) -> ProductResponse:
    on_hand = get_on_hand(p.id)
    reserved = get_reserved(p.id)
    available = max(0.0, on_hand - reserved)
    st = get_status(p, on_hand)
    min_level = float(getattr(p, 'min_stock_level', 0.0) or getattr(p, 'reorder_level', 0.0) or 0.0)

    return ProductResponse(
        id=p.id,
        name=p.name,
        sku=p.sku,
        category=p.category.name if p.category else None,
        category_id=p.category_id,
        uom=p.uom,
        min_stock_level=min_level,
        reorder_level=p.reorder_level,
        on_hand=on_hand,
        available=available,
        reserved=reserved,
        status=st,
        description=p.description,
        archived=p.archived
    )


@router.get("", response_model=List[ProductResponse])
def list_products(
    search: Optional[str] = Query(None, description="Search by name or SKU"),
    category_id: Optional[int] = Query(None, description="Filter by category ID"),
    status: Optional[str] = Query(None, description="Filter by status: In Stock, Low Stock, Out of Stock"),
    include_archived: bool = Query(False),
    current_user: User = Depends(get_current_user)
):
    """
    Returns product catalog with dynamically computed on-hand, available, and reserved stock.
    Stock is calculated from the ledger engine and never stored statically.
    """
    query = Product.query
    if not include_archived:
        query = query.filter_by(archived=False)

    if category_id:
        query = query.filter_by(category_id=category_id)

    if search:
        query = query.filter(
            db.or_(
                Product.name.ilike(f"%{search}%"),
                Product.sku.ilike(f"%{search}%")
            )
        )

    products = query.order_by(Product.sku.asc()).all()
    results = [_format_product(p) for p in products]

    if status:
        stat_filter = status.lower()
        results = [r for r in results if r.status.lower() == stat_filter]

    return results


@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
def create_product(
    payload: ProductCreate,
    current_user: User = Depends(require_manager)
):
    """
    Creates a new Product (Manager role required).
    Optionally initializes opening stock via an opening stock adjustment.
    """
    try:
        product = inv.create_product(
            name=payload.name.strip(),
            sku=payload.sku.strip(),
            category_id=payload.category_id,
            uom=payload.uom.strip(),
            reorder_level=int(payload.min_stock_level),
            description=payload.description,
            initial_stock=payload.initial_stock or 0.0,
            initial_location_id=payload.initial_location_id,
            user=current_user
        )
        cache.invalidate_kpis()
        return _format_product(product)
    except BusinessRuleError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{id}", response_model=ProductDetailResponse)
def get_product_detail(id: int, current_user: User = Depends(get_current_user)):
    """
    Returns full product details and breakdown of available/reserved stock across all warehouse locations.
    """
    product = Product.query.get(id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Product with ID {id} not found.")

    base_resp = _format_product(product)
    matrix_data = get_product_stock_matrix(product.id)

    location_items = []
    for loc_item in matrix_data["locations"]:
        loc = loc_item["location"]
        location_items.append(LocationStockMatrixItem(
            location_id=loc.id,
            location_code=loc.code,
            location_name=loc.name,
            warehouse_code=loc.warehouse.code if loc.warehouse else None,
            on_hand=loc_item["on_hand"],
            reserved=loc_item["reserved"],
            available=loc_item["available"]
        ))

    return ProductDetailResponse(
        **base_resp.dict(),
        location_matrix=location_items
    )


@router.put("/{id}", response_model=ProductResponse)
def update_product(
    id: int,
    payload: ProductUpdate,
    current_user: User = Depends(require_manager)
):
    """
    Updates an existing product's reorder rules or catalog attributes.
    """
    product = Product.query.get(id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Product with ID {id} not found.")

    try:
        updated = inv.update_product(
            product_id=id,
            name=payload.name or product.name,
            category_id=payload.category_id if payload.category_id is not None else product.category_id,
            uom=payload.uom or product.uom,
            reorder_level=int(payload.min_stock_level) if payload.min_stock_level is not None else product.reorder_level,
            description=payload.description if payload.description is not None else product.description,
            user=current_user
        )
        cache.invalidate_kpis()
        return _format_product(updated)
    except BusinessRuleError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
