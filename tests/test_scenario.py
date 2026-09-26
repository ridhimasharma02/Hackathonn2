import pytest
from app import create_app
from models import db, User, Product, Location, Warehouse, Supplier, Customer, Receipt, Delivery, Transfer, Adjustment, StockMovement, PasswordResetOTP
from services import inventory_service as inv
from services.inventory_service import BusinessRuleError
from services.stock_engine import get_on_hand, get_available
from services import auth_service as auth_svc
from seed import seed_database


@pytest.fixture(scope='function')
def test_app():
    app = create_app('config.TestConfig')
    with app.app_context():
        seed_database(app)
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture(scope='function')
def client(test_app):
    return test_app.test_client()


def login(client, email, password):
    return client.post('/login', data={'email': email, 'password': password}, follow_redirects=True)


def logout(client):
    return client.get('/logout', follow_redirects=True)


# =========================================================================
# AUXILIARY & AUTHENTICATION TESTS
# =========================================================================

def test_wrong_password_is_rejected(client, test_app):
    """Verify that logging in with incorrect credentials fails."""
    res = login(client, 'manager@stocksense.demo', 'WrongPassword123')
    assert res.status_code == 200
    assert b"Invalid email or password" in res.data


def test_otp_reset_flow(client, test_app):
    """Verify 6-digit OTP password reset workflow."""
    with test_app.app_context():
        # 1. Request OTP
        otp_code, user = auth_svc.generate_reset_otp('staff@stocksense.demo')
        assert len(otp_code) == 6
        assert otp_code.isdigit()

        # 2. Try invalid OTP
        with pytest.raises(auth_svc.BusinessRuleError, match="Invalid or expired OTP"):
            auth_svc.verify_otp_and_reset_password('staff@stocksense.demo', '000000', 'NewStaffPass@2026')

        # 3. Successful reset with valid OTP
        reset_user = auth_svc.verify_otp_and_reset_password('staff@stocksense.demo', otp_code, 'NewStaffPass@2026')
        assert reset_user is not None
        assert reset_user.id == user.id

    # 4. Confirm login with new password
    res = login(client, 'staff@stocksense.demo', 'NewStaffPass@2026')
    assert res.status_code == 200
    assert b"Sign Out" in res.data or b"Aman Kumar" in res.data


def test_duplicate_sku_rejected(test_app):
    """Verify that creating a product with an existing SKU is rejected."""
    with test_app.app_context():
        manager = User.query.filter_by(role='INVENTORY_MANAGER').first()
        with pytest.raises(BusinessRuleError, match="already exists"):
            inv.create_product(
                name="Duplicate Steel",
                sku="SR001",  # Existing SKU
                category_id=1,
                uom="kg",
                reorder_level=10,
                user=manager
            )


def test_transfer_to_same_location_rejected(test_app):
    """Verify that an internal transfer to the same location is rejected."""
    with test_app.app_context():
        manager = User.query.filter_by(role='INVENTORY_MANAGER').first()
        loc = Location.query.first()
        prod = Product.query.first()
        with pytest.raises(BusinessRuleError, match="Source and destination locations must be different"):
            inv.create_transfer(
                source_location_id=loc.id,
                destination_location_id=loc.id,
                items=[{'product_id': prod.id, 'quantity': 5}],
                user=manager
            )


# =========================================================================
# MANAGER ACCEPTANCE FLOW
# =========================================================================

def test_manager_lifecycle_flow(client, test_app):
    """
    Manager acceptance test:
    - Log in -> create a product with 35 initial stock
    - Create a receipt for 50 -> stock is still 35 after receiving -> 85 after validation
    - Transfer 20 from Main to Production -> Main 65, Production 20, total still 85
    - Delivery of 10 -> Ready -> pick -> pack -> validate -> total 75
    - A delivery of 500 goes to Waiting and cannot be picked
    - The ledger shows Adjustment, Receipt, Internal Transfer and Delivery for that product
    """
    # 1. Log in as manager
    res = login(client, 'manager@stocksense.demo', 'Manager@2026')
    assert res.status_code == 200

    with test_app.app_context():
        manager = User.query.filter_by(email='manager@stocksense.demo').first()
        loc_main = Location.query.filter_by(code='MAIN/STOCK').first()
        loc_prod = Location.query.filter_by(code='MAIN/PROD').first()
        cust = Customer.query.first()
        sup = Supplier.query.first()

        # 2. Create product with 35 initial stock
        prod = inv.create_product(
            name="Test Precision Bearings",
            sku="TPB01",
            category_id=1,
            uom="unit",
            reorder_level=15,
            description="High precision roller bearings",
            initial_stock=35,
            initial_location_id=loc_main.id,
            user=manager
        )
        assert get_on_hand(prod.id, loc_main.id) == 35.0
        assert get_on_hand(prod.id) == 35.0

        # 3. Create receipt for 50
        rec = inv.create_receipt(
            supplier_id=sup.id,
            destination_location_id=loc_main.id,
            items=[{'product_id': prod.id, 'quantity': 50}],
            user=manager
        )
        inv.confirm_receipt(rec.id, user=manager)

        # Receive goods for 50 -> stock must still be 35
        inv.receive_goods(rec.id, {str(rec.items[0].id): 50}, user=manager)
        assert get_on_hand(prod.id, loc_main.id) == 35.0

        # Validate receipt -> stock becomes 85
        inv.validate_receipt(rec.id, user=manager)
        assert get_on_hand(prod.id, loc_main.id) == 85.0
        assert get_on_hand(prod.id) == 85.0

        # 4. Transfer 20 from Main to Production -> Main 65, Prod 20, total still 85
        tr = inv.create_transfer(
            source_location_id=loc_main.id,
            destination_location_id=loc_prod.id,
            items=[{'product_id': prod.id, 'quantity': 20}],
            user=manager
        )
        inv.complete_transfer(tr.id, user=manager)
        assert get_on_hand(prod.id, loc_main.id) == 65.0
        assert get_on_hand(prod.id, loc_prod.id) == 20.0
        assert get_on_hand(prod.id) == 85.0

        # 5. Delivery of 10 -> Ready -> pick -> pack -> validate -> total 75
        deliv10 = inv.create_delivery(
            customer_id=cust.id,
            source_location_id=loc_main.id,
            items=[{'product_id': prod.id, 'quantity': 10}],
            user=manager
        )
        inv.confirm_delivery(deliv10.id, user=manager)
        assert deliv10.status == 'Ready'

        inv.pick_delivery(deliv10.id, user=manager)
        assert deliv10.status == 'Picked'

        inv.pack_delivery(deliv10.id, user=manager)
        assert deliv10.status == 'Packed'

        inv.validate_delivery(deliv10.id, user=manager)
        assert deliv10.status == 'Done'

        assert get_on_hand(prod.id, loc_main.id) == 55.0
        assert get_on_hand(prod.id) == 75.0

        # 6. Delivery of 500 goes to Waiting and cannot be picked
        deliv500 = inv.create_delivery(
            customer_id=cust.id,
            source_location_id=loc_main.id,
            items=[{'product_id': prod.id, 'quantity': 500}],
            user=manager
        )
        inv.confirm_delivery(deliv500.id, user=manager)
        assert deliv500.status == 'Waiting'

        with pytest.raises(BusinessRuleError, match="Only Ready orders can be picked"):
            inv.pick_delivery(deliv500.id, user=manager)

        # 7. Check ledger shows Adjustment, Receipt, Internal Transfer, and Delivery
        movements = StockMovement.query.filter_by(product_id=prod.id).all()
        operations = {m.operation for m in movements}
        assert 'Adjustment' in operations
        assert 'Receipt' in operations
        assert 'Internal Transfer' in operations
        assert 'Delivery' in operations


# =========================================================================
# WAREHOUSE STAFF ACCEPTANCE FLOW
# =========================================================================

def test_staff_permissions_and_workflow(client, test_app):
    """
    Warehouse Staff acceptance test:
    - POST to create a product, create a receipt, or open /settings -> 403
    - Record receiving on REC-0006 -> the staff user cannot validate it; a manager validation adds +60
    - Pick and pack DO-0008 -> the staff user cannot validate the dispatch
    - Complete transfer INT-0005 -> total unchanged
    - Submit a count on ADJ-0005 with a discrepancy but no reason -> rejected;
      with a reason -> Counted and stock unchanged; staff cannot approve;
      manager approval sets stock to the counted quantity
    - No stock is negative anywhere at the end
    """
    # 1. Log in as staff
    res = login(client, 'staff@stocksense.demo', 'Staff@2026')
    assert res.status_code == 200

    # Staff restricted routes return 403
    res_prod = client.post('/products/new', data={'name': 'Illegal Prod', 'sku': 'ILL01', 'uom': 'unit', 'category_id': '1'})
    assert res_prod.status_code == 403

    res_rec = client.post('/receipts/new', data={'supplier_id': '1', 'destination_location_id': '1'})
    assert res_rec.status_code == 403

    res_settings = client.get('/settings/', follow_redirects=True)
    assert res_settings.status_code == 403

    with test_app.app_context():
        staff = User.query.filter_by(email='staff@stocksense.demo').first()
        manager = User.query.filter_by(email='manager@stocksense.demo').first()

        # 2. Record receiving on REC-0006
        rec6 = Receipt.query.filter_by(reference='REC-0006').first()
        assert rec6 is not None
        p_steel = rec6.items[0].product
        stock_before_val = get_on_hand(p_steel.id)

        # Staff records receiving
        inv.receive_goods(rec6.id, {str(rec6.items[0].id): 60}, user=staff)
        assert rec6.status == 'Ready'
        # Stock unchanged yet
        assert get_on_hand(p_steel.id) == stock_before_val

        # Staff cannot validate
        with pytest.raises(PermissionError):
            inv.validate_receipt(rec6.id, user=staff)

        # Manager validates -> adds +60
        inv.validate_receipt(rec6.id, user=manager)
        assert get_on_hand(p_steel.id) == stock_before_val + 60.0

        # 3. Pick and pack DO-0008
        do8 = Delivery.query.filter_by(reference='DO-0008').first()
        assert do8 is not None
        assert do8.status == 'Ready'

        inv.pick_delivery(do8.id, user=staff)
        assert do8.status == 'Picked'

        inv.pack_delivery(do8.id, user=staff)
        assert do8.status == 'Packed'

        # Staff cannot validate dispatch
        with pytest.raises(PermissionError):
            inv.validate_delivery(do8.id, user=staff)

        # 4. Complete transfer INT-0005 -> total unchanged
        tr5 = Transfer.query.filter_by(reference='INT-0005').first()
        assert tr5 is not None
        tr_prod = tr5.items[0].product
        total_before_tr = get_on_hand(tr_prod.id)

        inv.complete_transfer(tr5.id, user=staff)
        assert tr5.status == 'Done'
        assert get_on_hand(tr_prod.id) == total_before_tr

        # 5. Submit count on ADJ-0005
        adj5 = Adjustment.query.filter_by(reference='ADJ-0005').first()
        assert adj5 is not None
        adj_item = adj5.items[0]
        adj_prod = adj_item.product
        stock_before_adj = get_on_hand(adj_prod.id, adj_item.location_id)

        # Discrepancy without reason -> rejected
        with pytest.raises(BusinessRuleError, match="A reason is mandatory"):
            inv.submit_count(adj5.id, {
                str(adj_item.id): {
                    'counted_quantity': stock_before_adj - 4,
                    'reason': ''  # Missing reason
                }
            }, user=staff)

        # Discrepancy with reason -> Counted, stock unchanged
        inv.submit_count(adj5.id, {
            str(adj_item.id): {
                'counted_quantity': stock_before_adj - 4,
                'reason': 'Damaged'
            }
        }, user=staff)
        assert adj5.status == 'Counted'
        assert get_on_hand(adj_prod.id, adj_item.location_id) == stock_before_adj

        # Staff cannot approve
        with pytest.raises(PermissionError):
            inv.approve_adjustment(adj5.id, user=staff)

        # Manager approves -> on-hand becomes exactly the counted quantity
        inv.approve_adjustment(adj5.id, user=manager)
        assert adj5.status == 'Approved'
        assert get_on_hand(adj_prod.id, adj_item.location_id) == (stock_before_adj - 4)

        # 6. Verify NO stock is negative anywhere at the end
        all_products = Product.query.all()
        all_locations = Location.query.all()
        for p in all_products:
            total_oh = get_on_hand(p.id)
            assert total_oh >= 0, f"Negative total stock for {p.name}: {total_oh}"
            for loc in all_locations:
                loc_oh = get_on_hand(p.id, loc.id)
                assert loc_oh >= 0, f"Negative stock for {p.name} at {loc.code}: {loc_oh}"
