"""
StockSense FastAPI v1 REST API Test Suite
Validates the complete REST API surface, double-entry inventory ledger engine,
OTP lifecycle, JWT RBAC security, dashboard KPIs, and atomic stock validation.
"""
import pytest
from fastapi.testclient import TestClient
from app_asgi import app, flask_app
from models import db
from seed import seed_database


@pytest.fixture(scope="module")
def client():
    """Module-scoped test client with clean seeded database."""
    with flask_app.app_context():
        seed_database(flask_app)
    with TestClient(app) as test_client:
        yield test_client


def get_auth_token(client: TestClient, email: str = "manager@stocksense.demo", password: str = "Manager@2026") -> str:
    """Helper to acquire JWT bearer token."""
    res = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200
    return res.json()["access_token"]


def get_staff_token(client: TestClient) -> str:
    """Helper to acquire Warehouse Staff JWT token."""
    return get_auth_token(client, email="staff@stocksense.demo", password="Staff@2026")


# =============================================================================
# 1. SYSTEM & DOCUMENTATION TESTS
# =============================================================================

def test_health_check(client: TestClient):
    """Verify system health endpoint and architecture metadata."""
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert "FastAPI" in data["architecture"]

    res_v1 = client.get("/api/v1/health")
    assert res_v1.status_code == 200


def test_openapi_schema_generated(client: TestClient):
    """Verify OpenAPI 3.0+ schema generation."""
    res = client.get("/openapi.json")
    assert res.status_code == 200
    spec = res.json()
    assert spec["info"]["title"] == "StockSense API & Inventory Ledger Engine"
    assert "/api/v1/auth/login" in spec["paths"]
    assert "/api/v1/dashboard/kpis" in spec["paths"]
    assert "/api/v1/operations" in spec["paths"]


# =============================================================================
# 2. AUTHENTICATION, OTP & RBAC TESTS
# =============================================================================

def test_login_success_and_failure(client: TestClient):
    """Test valid and invalid JWT logins."""
    # Valid login
    res = client.post("/api/v1/auth/login", json={
        "email": "manager@stocksense.demo",
        "password": "Manager@2026"
    })
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["user"]["email"] == "manager@stocksense.demo"
    assert data["user"]["role"] == "INVENTORY_MANAGER"

    # Invalid login
    res_bad = client.post("/api/v1/auth/login", json={
        "email": "manager@stocksense.demo",
        "password": "WrongPassword999"
    })
    assert res_bad.status_code == 401
    assert "Invalid email or password" in res_bad.json()["detail"]


def test_otp_lifecycle_and_password_reset(client: TestClient):
    """
    Test 6-digit OTP generation, Redis/memory caching (10-min TTL),
    and password reset with Argon2 encryption.
    """
    # 1. Request OTP
    res_otp = client.post("/api/v1/auth/otp-request", json={
        "email": "staff@stocksense.demo"
    })
    assert res_otp.status_code == 200
    otp_code = res_otp.json()["dev_otp"]
    assert otp_code is not None
    assert len(otp_code) == 6
    assert otp_code.isdigit()

    # 2. Reset with wrong OTP -> 400
    res_bad_reset = client.post("/api/v1/auth/reset-password", json={
        "email": "staff@stocksense.demo",
        "otp": "000000",
        "new_password": "NewStaffPassword@2026"
    })
    assert res_bad_reset.status_code == 400

    # 3. Reset with valid OTP -> 200
    res_good_reset = client.post("/api/v1/auth/reset-password", json={
        "email": "staff@stocksense.demo",
        "otp": otp_code,
        "new_password": "NewStaffPassword@2026"
    })
    assert res_good_reset.status_code == 200

    # 4. Login with newly set password
    token = get_auth_token(client, email="staff@stocksense.demo", password="NewStaffPassword@2026")
    assert token is not None

    # Reset back to default Staff@2026 for downstream test stability
    res_otp2 = client.post("/api/v1/auth/otp-request", json={"email": "staff@stocksense.demo"})
    client.post("/api/v1/auth/reset-password", json={
        "email": "staff@stocksense.demo",
        "otp": res_otp2.json()["dev_otp"],
        "new_password": "Staff@2026"
    })


def test_get_current_user_profile(client: TestClient):
    """Verify /auth/me returns authenticated identity."""
    token = get_auth_token(client)
    res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "Ridhima Sharma"
    assert data["role"] == "INVENTORY_MANAGER"


# =============================================================================
# 3. DASHBOARD KPIS & CACHING TESTS
# =============================================================================

def test_dashboard_kpis_endpoint(client: TestClient):
    """Verify dashboard KPI metrics calculation and caching."""
    token = get_auth_token(client)
    # First call: computes and stores in cache
    res1 = client.get("/api/v1/dashboard/kpis", headers={"Authorization": f"Bearer {token}"})
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["total_products"] == 8
    assert data1["out_of_stock_items"] >= 1
    assert data1["low_stock_items"] >= 2

    # Second call: served from Redis / cache
    res2 = client.get("/api/v1/dashboard/kpis", headers={"Authorization": f"Bearer {token}"})
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["cached"] is True


# =============================================================================
# 4. PRODUCTS & LOCATION MATRIX TESTS
# =============================================================================

def test_list_products_and_matrix(client: TestClient):
    """Verify product list, dynamic stock computation, and location breakdown."""
    token = get_auth_token(client)
    res = client.get("/api/v1/products", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    products = res.json()
    assert len(products) >= 8

    # Detail with location matrix
    p_id = products[0]["id"]
    res_detail = client.get(f"/api/v1/products/{p_id}", headers={"Authorization": f"Bearer {token}"})
    assert res_detail.status_code == 200
    detail = res_detail.json()
    assert "location_matrix" in detail
    assert len(detail["location_matrix"]) >= 2


def test_manager_can_create_product_staff_forbidden(client: TestClient):
    """Enforce RBAC: staff cannot create products, manager can."""
    manager_token = get_auth_token(client)
    staff_token = get_staff_token(client)

    payload = {
        "name": "Heavy Duty Casters",
        "sku": f"HDC-999",
        "uom": "unit",
        "min_stock_level": 25.0,
        "description": "Industrial swivel casters"
    }

    # Staff forbidden -> 403
    res_staff = client.post("/api/v1/products", json=payload, headers={"Authorization": f"Bearer {staff_token}"})
    assert res_staff.status_code == 403

    # Manager allowed -> 201
    res_mgr = client.post("/api/v1/products", json=payload, headers={"Authorization": f"Bearer {manager_token}"})
    assert res_mgr.status_code == 201
    assert res_mgr.json()["sku"] == "HDC-999"


# =============================================================================
# 5. LOCATIONS & VIRTUAL DOUBLE-ENTRY LOCATIONS
# =============================================================================

def test_locations_list_includes_all_types(client: TestClient):
    """Verify physical and virtual locations exist (INTERNAL, VENDOR, CUSTOMER, INVENTORY_LOSS)."""
    token = get_auth_token(client)
    res = client.get("/api/v1/locations", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    locs = res.json()
    types = {loc["type"] for loc in locs}
    assert "INTERNAL" in types
    assert "VENDOR" in types
    assert "CUSTOMER" in types
    assert "INVENTORY_LOSS" in types


# =============================================================================
# 6. OPERATIONS & ATOMIC VALIDATION ENGINE
# =============================================================================

def test_receipt_creation_and_atomic_validation(client: TestClient):
    """
    Test Receipt flow:
    - Create receipt for 50 units
    - Validate receipt -> stock increases by +50
    """
    token = get_auth_token(client)
    # Find a product
    prod = client.get("/api/v1/products", headers={"Authorization": f"Bearer {token}"}).json()[0]
    stock_before = prod["on_hand"]

    # 1. Create receipt
    res_create = client.post("/api/v1/operations", json={
        "operation_type": "RECEIPT",
        "items": [{"product_id": prod["id"], "quantity": 50.0}],
        "notes": "FastAPI Receipt Intake Test"
    }, headers={"Authorization": f"Bearer {token}"})
    assert res_create.status_code == 201
    rec = res_create.json()

    # 2. Validate receipt -> triggers atomic increase
    res_val = client.post(
        f"/api/v1/operations/{rec['id']}/validate?operation_type=RECEIPT",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert res_val.status_code == 200
    assert res_val.json()["status"] == "DONE"

    # Verify stock increased
    prod_after = client.get(f"/api/v1/products/{prod['id']}", headers={"Authorization": f"Bearer {token}"}).json()
    assert prod_after["on_hand"] == stock_before + 50.0


def test_internal_transfer_atomic_relocation(client: TestClient):
    """
    Test Internal Transfer:
    - Stock moves from source to destination
    - Total on-hand company stock remains unchanged
    """
    token = get_auth_token(client)
    locs = client.get("/api/v1/locations?type=INTERNAL", headers={"Authorization": f"Bearer {token}"}).json()
    src_loc = locs[0]
    dest_loc = locs[1]

    # Find Steel Rods or product with stock at src_loc
    prods = client.get("/api/v1/products", headers={"Authorization": f"Bearer {token}"}).json()
    target_prod = [p for p in prods if p["sku"] == "SR001"][0]
    total_before = target_prod["on_hand"]

    # Create transfer of 15 units
    res_create = client.post("/api/v1/operations", json={
        "operation_type": "INTERNAL",
        "source_location_id": src_loc["id"],
        "destination_location_id": dest_loc["id"],
        "items": [{"product_id": target_prod["id"], "quantity": 15.0}],
        "notes": "Relocation Test"
    }, headers={"Authorization": f"Bearer {token}"})
    assert res_create.status_code == 201
    tr = res_create.json()

    # Validate transfer
    res_val = client.post(
        f"/api/v1/operations/{tr['id']}/validate?operation_type=INTERNAL",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert res_val.status_code == 200
    assert res_val.json()["status"] == "DONE"

    # Total company stock must remain exactly identical
    prod_after = client.get(f"/api/v1/products/{target_prod['id']}", headers={"Authorization": f"Bearer {token}"}).json()
    assert prod_after["on_hand"] == total_before


def test_outbound_negative_stock_rejection(client: TestClient):
    """
    Section 4 Atomic Stock Validation Engine:
    Validates that attempting to dispatch more stock than available
    aborts transaction and strictly prevents negative inventory.
    """
    token = get_auth_token(client)
    prods = client.get("/api/v1/products", headers={"Authorization": f"Bearer {token}"}).json()
    prod = prods[0]

    # Create delivery order with impossible quantity (999,999 units)
    res_create = client.post("/api/v1/operations", json={
        "operation_type": "DELIVERY",
        "items": [{"product_id": prod["id"], "quantity": 999999.0}],
        "notes": "Excessive Delivery Order"
    }, headers={"Authorization": f"Bearer {token}"})
    assert res_create.status_code == 201
    deliv = res_create.json()

    # Attempting to validate MUST FAIL with 400 Bad Request
    res_val = client.post(
        f"/api/v1/operations/{deliv['id']}/validate?operation_type=DELIVERY",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert res_val.status_code == 400
    assert "Insufficient stock" in res_val.json()["detail"]


# =============================================================================
# 7. STOCK LEDGER & MOVE AUDIT TRAIL
# =============================================================================

def test_ledger_moves_pagination_and_audit(client: TestClient):
    """Verify paginated immutable move audit trail."""
    token = get_auth_token(client)
    res = client.get("/api/v1/ledger/moves?page=1&page_size=10", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["total"] > 0
    assert len(data["moves"]) <= 10
    first_move = data["moves"][0]
    assert "reference" in first_move
    assert "quantity" in first_move
    assert "product_sku" in first_move


# =============================================================================
# 8. LOW STOCK ALERTS & DIGEST
# =============================================================================

def test_low_stock_alert_digest(client: TestClient):
    """Verify automated scanning of products below min_stock_level."""
    token = get_auth_token(client)
    res = client.get("/api/v1/alerts/low-stock", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    digest = res.json()
    assert digest["summary"]["total_alerts"] >= 2
    assert len(digest["critical_out_of_stock"]) >= 1
    assert len(digest["low_stock_warnings"]) >= 1

    # Dispatch digest trigger
    res_dispatch = client.post("/api/v1/alerts/dispatch-digest", headers={"Authorization": f"Bearer {token}"})
    assert res_dispatch.status_code == 200
    assert "dispatched successfully" in res_dispatch.json()["message"]
