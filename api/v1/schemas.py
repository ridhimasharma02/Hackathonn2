"""
StockSense Pydantic Schemas (v1)
Strongly typed models for requests, responses, and validation.
"""
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field


# -----------------------------------------------------------------------------
# Common
# -----------------------------------------------------------------------------
class MessageResponse(BaseModel):
    status: str = "success"
    message: str
    detail: Optional[Any] = None


# -----------------------------------------------------------------------------
# Authentication & User Schemas
# -----------------------------------------------------------------------------
class OTPRequest(BaseModel):
    email: str = Field(..., description="User email for password reset OTP")


class OTPResponse(BaseModel):
    status: str = "success"
    message: str
    dev_otp: Optional[str] = Field(None, description="Included for easy development and evaluation testing")


class ResetPasswordRequest(BaseModel):
    email: str = Field(..., description="User registered email")
    otp: str = Field(..., min_length=6, max_length=6, description="6-digit verification code")
    new_password: str = Field(..., min_length=6, description="New secure password")


class LoginRequest(BaseModel):
    email: str = Field(..., description="Registered email address")
    password: str = Field(..., description="Account password")


class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: str = Field(..., description="Unique email address")
    password: str = Field(..., min_length=6)
    role: Optional[str] = Field("WAREHOUSE_STAFF", description="INVENTORY_MANAGER or WAREHOUSE_STAFF")
    phone: Optional[str] = None


class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    role: str
    phone: Optional[str] = None
    active: bool

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


# -----------------------------------------------------------------------------
# Dashboard KPI Schemas
# -----------------------------------------------------------------------------
class KPISummary(BaseModel):
    total_products: int
    in_stock_items: int
    low_stock_items: int
    out_of_stock_items: int
    pending_receipts: int
    pending_deliveries: int
    internal_transfers_scheduled: int
    pending_adjustments: int
    cached: bool = False
    timestamp: str


# -----------------------------------------------------------------------------
# Products & Catalog Schemas
# -----------------------------------------------------------------------------
class ProductCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=150)
    sku: str = Field(..., min_length=2, max_length=50)
    category_id: Optional[int] = None
    uom: str = Field("unit", max_length=30)
    min_stock_level: float = Field(0.0, ge=0.0)
    description: Optional[str] = None
    initial_stock: Optional[float] = Field(0.0, ge=0.0)
    initial_location_id: Optional[int] = None


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    category_id: Optional[int] = None
    uom: Optional[str] = None
    min_stock_level: Optional[float] = Field(None, ge=0.0)
    description: Optional[str] = None


class LocationStockMatrixItem(BaseModel):
    location_id: int
    location_code: str
    location_name: str
    warehouse_code: Optional[str] = None
    on_hand: float
    reserved: float
    available: float


class ProductResponse(BaseModel):
    id: int
    name: str
    sku: str
    category: Optional[str] = None
    category_id: Optional[int] = None
    uom: str
    min_stock_level: float
    reorder_level: int
    on_hand: float
    available: float
    reserved: float
    status: str
    description: Optional[str] = None
    archived: bool


class ProductDetailResponse(ProductResponse):
    location_matrix: List[LocationStockMatrixItem] = []


# -----------------------------------------------------------------------------
# Locations & Warehouses
# -----------------------------------------------------------------------------
class LocationCreate(BaseModel):
    name: str
    code: str
    type: str = Field("INTERNAL", description="INTERNAL, VENDOR, CUSTOMER, or INVENTORY_LOSS")
    warehouse_id: Optional[int] = None
    parent_location_id: Optional[int] = None


class LocationResponse(BaseModel):
    id: int
    name: str
    code: str
    type: str
    warehouse_id: Optional[int] = None
    warehouse_name: Optional[str] = None
    parent_location_id: Optional[int] = None
    active: bool

    class Config:
        from_attributes = True


# -----------------------------------------------------------------------------
# Stock Operations Schemas
# -----------------------------------------------------------------------------
class OperationItemCreate(BaseModel):
    product_id: int
    quantity: float = Field(..., gt=0.0)


class OperationCreate(BaseModel):
    operation_type: str = Field(..., description="RECEIPT, DELIVERY, INTERNAL, or ADJUSTMENT")
    source_location_id: Optional[int] = None
    destination_location_id: Optional[int] = None
    partner_id: Optional[int] = Field(None, description="Supplier ID (for receipts) or Customer ID (for deliveries)")
    priority: Optional[str] = "Normal"
    source_document: Optional[str] = None
    notes: Optional[str] = None
    items: List[OperationItemCreate] = Field(..., min_length=1)


class OperationItemResponse(BaseModel):
    id: int
    product_id: int
    product_sku: str
    product_name: str
    quantity: float
    received_quantity: Optional[float] = None
    uom: str


class OperationResponse(BaseModel):
    id: int
    reference: str
    operation_type: str
    status: str
    source_location: Optional[str] = None
    source_location_id: Optional[int] = None
    destination_location: Optional[str] = None
    destination_location_id: Optional[int] = None
    partner_name: Optional[str] = None
    created_at: str
    done_at: Optional[str] = None
    items: List[OperationItemResponse] = []
    notes: Optional[str] = None


class OperationActionRequest(BaseModel):
    action: str = Field(..., description="confirm, pick, pack, cancel")


# -----------------------------------------------------------------------------
# Ledger Moves
# -----------------------------------------------------------------------------
class LedgerMoveResponse(BaseModel):
    id: int
    reference: str
    operation: str
    product_id: int
    product_sku: str
    product_name: str
    quantity: float
    uom: str
    source_location: Optional[str] = None
    destination_location: Optional[str] = None
    counterparty: Optional[str] = None
    user_name: Optional[str] = None
    at: str


class LedgerPageResponse(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int
    moves: List[LedgerMoveResponse]


# -----------------------------------------------------------------------------
# Low Stock Alerts
# -----------------------------------------------------------------------------
class AlertItem(BaseModel):
    product_id: int
    name: str
    sku: str
    category: str
    uom: str
    on_hand: float
    available: float
    min_stock_level: float
    deficit: float
    severity: str


class AlertDigestResponse(BaseModel):
    timestamp: str
    summary: Dict[str, Any]
    critical_out_of_stock: List[AlertItem]
    low_stock_warnings: List[AlertItem]
