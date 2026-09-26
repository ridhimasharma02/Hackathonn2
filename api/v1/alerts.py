"""
StockSense Alert Automation Endpoints (v1)
Scans for products where quantity is less than min_stock_level
and aggregates low-stock items into an automated alert digest.
"""
from fastapi import APIRouter, Depends
from models import User
from services.alert_service import scan_low_stock, dispatch_low_stock_digest
from api.v1.schemas import AlertDigestResponse, MessageResponse
from api.v1.dependencies import get_current_user

router = APIRouter(prefix="/alerts", tags=["Alerts & Notifications"])


@router.get("/low-stock", response_model=AlertDigestResponse)
def get_low_stock_digest(current_user: User = Depends(get_current_user)):
    """
    Automated scan for products where current physical quantity is less than min_stock_level.
    Aggregates low-stock items into an automated alert digest.
    """
    data = scan_low_stock()
    return AlertDigestResponse(**data)


@router.post("/dispatch-digest", response_model=MessageResponse)
def trigger_alert_dispatch(current_user: User = Depends(get_current_user)):
    """
    Triggers simulated/configured transactional alert digest dispatch to inventory managers.
    """
    res = dispatch_low_stock_digest()
    return MessageResponse(
        status="success",
        message=f"Alert digest with {res['alerts_count']} item(s) dispatched successfully.",
        detail=res
    )
