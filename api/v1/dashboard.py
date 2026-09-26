"""
StockSense Dashboard KPI Endpoints (v1)
Provides real-time aggregated metrics with Redis caching as specified in Section 5.
"""
from datetime import datetime
from fastapi import APIRouter, Depends
from models import Product, Receipt, Delivery, Transfer, Adjustment, User
from services.cache_service import cache
from services.stock_engine import get_on_hand
from api.v1.schemas import KPISummary
from api.v1.dependencies import get_current_user

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/kpis", response_model=KPISummary)
def get_dashboard_kpis(current_user: User = Depends(get_current_user)):
    """
    Reads aggregated cached metrics (Total products, Low/Out of Stock, Pending Receipts,
    Pending Deliveries, Internal Transfers Scheduled). Cached in Redis with a 60-second TTL.
    """
    cached = cache.get_kpis()
    if cached:
        cached["cached"] = True
        return KPISummary(**cached)

    products = Product.query.filter_by(archived=False).all()
    in_stock_count = 0
    low_stock_count = 0
    out_of_stock_count = 0

    for p in products:
        qty = get_on_hand(p.id)
        min_level = float(getattr(p, 'min_stock_level', 0.0) or getattr(p, 'reorder_level', 0.0) or 0.0)
        if qty <= 0:
            out_of_stock_count += 1
        elif qty <= min_level:
            low_stock_count += 1
        else:
            in_stock_count += 1

    pending_recs = Receipt.query.filter(Receipt.status.in_(['Draft', 'Waiting', 'Ready'])).count()
    pending_dels = Delivery.query.filter(Delivery.status.in_(['Draft', 'Waiting', 'Ready', 'Picked', 'Packed'])).count()
    scheduled_transfers = Transfer.query.filter(Transfer.status.in_(['Draft', 'Waiting', 'Ready'])).count()
    pending_adjustments = Adjustment.query.filter(Adjustment.status.in_(['Draft', 'Counted'])).count()

    data = {
        "total_products": len(products),
        "in_stock_items": in_stock_count,
        "low_stock_items": low_stock_count,
        "out_of_stock_items": out_of_stock_count,
        "pending_receipts": pending_recs,
        "pending_deliveries": pending_dels,
        "internal_transfers_scheduled": scheduled_transfers,
        "pending_adjustments": pending_adjustments,
        "cached": False,
        "timestamp": datetime.utcnow().isoformat()
    }

    # Store in Redis/memory with 60s TTL
    cache.set_kpis(data, ttl_seconds=60)

    return KPISummary(**data)
