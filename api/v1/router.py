"""
StockSense Main API v1 Router
Aggregates all domain routers under /api/v1.
"""
from fastapi import APIRouter
from api.v1.auth import router as auth_router
from api.v1.dashboard import router as dashboard_router
from api.v1.operations import router as operations_router
from api.v1.ledger import router as ledger_router
from api.v1.products import router as products_router
from api.v1.locations import router as locations_router
from api.v1.alerts import router as alerts_router

api_v1_router = APIRouter()

api_v1_router.include_router(auth_router)
api_v1_router.include_router(dashboard_router)
api_v1_router.include_router(operations_router)
api_v1_router.include_router(ledger_router)
api_v1_router.include_router(products_router)
api_v1_router.include_router(locations_router)
api_v1_router.include_router(alerts_router)
