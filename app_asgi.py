"""
StockSense Unified ASGI Application Server
Combines:
- FastAPI for high-performance REST API (/api/v1) and OpenAPI Swagger (/docs)
- Double-entry stock quants & immutable ledger validation
- Flask WSGI application for full interactive dashboard, forms, and Google Stitch UI (/)
"""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from a2wsgi import WSGIMiddleware

from app import create_app
from models import db, User
from api.v1.router import api_v1_router
from services.stock_engine import sync_all_quants
from seed import seed_database

# Initialize base Flask application
flask_app = create_app()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure database schema is created and seeded if empty
    with flask_app.app_context():
        db.create_all()
        if not User.query.first():
            print("Database empty. Seeding benchmark warehouse records...")
            seed_database(flask_app)
        else:
            sync_all_quants()
    yield


app = FastAPI(
    title="StockSense API & Inventory Ledger Engine",
    description="High-Concurrence, Zero-License-Cost Inventory & Ledger Engine",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan
)

# Cross-Origin Resource Sharing for Web/Mobile SPA clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def flask_context_middleware(request, call_next):
    """Ensures database connection context is active during REST API request processing."""
    with flask_app.app_context():
        response = await call_next(request)
        return response


@app.get("/health", tags=["System"])
@app.get("/api/v1/health", tags=["System"])
def health_check():
    """System health check and architectural capability reporting."""
    return {
        "status": "healthy",
        "service": "StockSense Inventory & Ledger Engine",
        "version": "1.0.0",
        "architecture": "FastAPI + Double-Entry Quants Ledger",
        "docs_url": "/docs"
    }


# Mount REST API under /api/v1
app.include_router(api_v1_router, prefix="/api/v1")

# Mount Flask Web Application for web UI and forms at root
app.mount("/", WSGIMiddleware(flask_app))
