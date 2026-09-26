import sys
from datetime import datetime, timedelta
from app import create_app
from models import (
    db, User, Category, Product, Warehouse, Location, Supplier, Customer,
    Receipt, Delivery, Transfer, Adjustment, StockMovement, ActivityLog, Sequence, PasswordResetOTP
)
from services import inventory_service as inv
from services.stock_engine import get_on_hand, get_available, get_status, sync_all_quants

from flask import current_app, has_app_context

def seed_database(app=None):
    if app is None:
        if has_app_context():
            app = current_app._get_current_object()
        else:
            app = create_app()

    with app.app_context():
        print("Dropping existing tables and rebuilding schema...")
        db.drop_all()
        db.create_all()

        print("Initializing sequences...")
        for pfx in ['REC', 'DO', 'INT', 'ADJ']:
            db.session.add(Sequence(prefix=pfx, last_number=0))
        db.session.commit()

        print("Seeding Users...")
        manager = User(
            name="Ridhima Sharma",
            email="manager@stocksense.demo",
            role="INVENTORY_MANAGER",
            phone="+91 98201 44521",
            active=True
        )
        manager.set_password("Manager@2026")

        staff = User(
            name="Aman Kumar",
            email="staff@stocksense.demo",
            role="WAREHOUSE_STAFF",
            phone="+91 98220 18492",
            active=True
        )
        staff.set_password("Staff@2026")

        staff2 = User(
            name="Neha Joshi",
            email="neha.joshi@stocksense.demo",
            role="WAREHOUSE_STAFF",
            phone="+91 98225 90123",
            active=True
        )
        staff2.set_password("Staff@2026")

        db.session.add_all([manager, staff, staff2])
        db.session.commit()

        print("Seeding Warehouses and Locations...")
        wh_main = Warehouse(
            name="Main Warehouse",
            code="MAIN",
            address="Plot B-12, Chakan Industrial Area, Pune 410501",
            active=True
        )
        wh_wh2 = Warehouse(
            name="Warehouse 2",
            code="WH2",
            address="Bhosari Logistics Park, Bay 4, Pune 411026",
            active=True
        )
        db.session.add_all([wh_main, wh_wh2])
        db.session.commit()

        loc_main_stock = Location(warehouse_id=wh_main.id, name="Main Storage", code="MAIN/STOCK", type="INTERNAL", active=True)
        loc_main_prod = Location(warehouse_id=wh_main.id, name="Production Floor", code="MAIN/PROD", type="INTERNAL", active=True)
        loc_main_rack_a = Location(warehouse_id=wh_main.id, name="Rack A - Structural", code="MAIN/RACK-A", type="INTERNAL", active=True)
        loc_main_rack_b = Location(warehouse_id=wh_main.id, name="Rack B - Assembly", code="MAIN/RACK-B", type="INTERNAL", active=True)
        loc_wh2_stock = Location(warehouse_id=wh_wh2.id, name="Warehouse 2 Storage", code="WH2/STOCK", type="INTERNAL", active=True)

        # Virtual double-entry partner and loss locations
        loc_vendor = Location(name="Vendors & Suppliers", code="PARTNERS/VENDORS", type="VENDOR", active=True)
        loc_customer = Location(name="Customer Fulfillment", code="PARTNERS/CUSTOMERS", type="CUSTOMER", active=True)
        loc_loss = Location(name="Inventory Loss & Scraps", code="VIRTUAL/LOSS", type="INVENTORY_LOSS", active=True)

        db.session.add_all([
            loc_main_stock, loc_main_prod, loc_main_rack_a, loc_main_rack_b, loc_wh2_stock,
            loc_vendor, loc_customer, loc_loss
        ])
        db.session.commit()

        print("Seeding Categories...")
        cat_raw = Category(name="Raw Materials")
        cat_pkg = Category(name="Packaging & Consumables")
        cat_office = Category(name="Office & Facility")
        cat_elec = Category(name="Electrical & Lighting")
        cat_safety = Category(name="Safety & PPE")
        db.session.add_all([cat_raw, cat_pkg, cat_office, cat_elec, cat_safety])
        db.session.commit()

        print("Seeding Suppliers and Customers...")
        sup_metro = Supplier(name="Metro Industrial Supplies", contact="Rajesh Khanna (+91 98201 44521)", city="Mumbai")
        sup_prime = Supplier(name="Prime Office Solutions", contact="Sunil Mehta (+91 98220 55432)", city="Pune")
        sup_tech = Supplier(name="TechLine Distributors", contact="Pooja Reddy (+91 98450 11223)", city="Bengaluru")
        db.session.add_all([sup_metro, sup_prime, sup_tech])

        cust_abc = Customer(name="ABC Manufacturing", contact="Vikram Deshmukh (+91 98220 18492)", city="Pune")
        cust_horizon = Customer(name="Horizon Interiors", contact="Kavita Rao (+91 98190 77654)", city="Mumbai")
        cust_northstar = Customer(name="NorthStar Retail", contact="Anand Verma (+91 98110 33445)", city="Delhi")
        db.session.add_all([cust_abc, cust_horizon, cust_northstar])
        db.session.commit()

        print("Seeding Products with initial stock via Opening Stock Adjustments...")
        # 1. Steel Rods SR001 kg 150
        p_steel = inv.create_product(
            name="Steel Rods",
            sku="SR001",
            category_id=cat_raw.id,
            uom="kg",
            reorder_level=150,
            description="High tensile structural steel reinforcing rods (12mm).",
            initial_stock=320,
            initial_location_id=loc_main_stock.id,
            user=manager
        )

        # 2. Aluminum Sheets AS002 sheet 40 (Low stock: 38 <= 40)
        p_alum = inv.create_product(
            name="Aluminum Sheets",
            sku="AS002",
            category_id=cat_raw.id,
            uom="sheet",
            reorder_level=40,
            description="Cold-rolled aluminum alloy plates 2mm thickness.",
            initial_stock=38,
            initial_location_id=loc_main_stock.id,
            user=manager
        )

        # 3. Packaging Boxes PB006 unit 200
        p_box = inv.create_product(
            name="Packaging Boxes",
            sku="PB006",
            category_id=cat_pkg.id,
            uom="unit",
            reorder_level=200,
            description="Heavy-duty 3-ply corrugated shipping cartons.",
            initial_stock=450,
            initial_location_id=loc_wh2_stock.id,
            user=manager
        )

        # 4. Office Chairs OC003 unit 45 (Stock seeded via receipts)
        p_chair = inv.create_product(
            name="Office Chairs",
            sku="OC003",
            category_id=cat_office.id,
            uom="unit",
            reorder_level=45,
            description="Ergonomic mesh-back adjustable executive desk chairs.",
            initial_stock=0,
            initial_location_id=None,
            user=manager
        )

        # 5. Printer Paper PP004 ream 60 (Stock seeded via receipts)
        p_paper = inv.create_product(
            name="Printer Paper",
            sku="PP004",
            category_id=cat_office.id,
            uom="ream",
            reorder_level=60,
            description="A4 80 GSM ultra-white multi-purpose laser paper.",
            initial_stock=0,
            initial_location_id=None,
            user=manager
        )

        # 6. LED Panels LP005 unit 30 (Out of stock: 0 <= 0)
        p_led = inv.create_product(
            name="LED Panels",
            sku="LP005",
            category_id=cat_elec.id,
            uom="unit",
            reorder_level=30,
            description="36W 600x600 modular square recessed ceiling panels.",
            initial_stock=0,
            initial_location_id=None,
            user=manager
        )

        # 7. Safety Helmets SH007 unit 30 (Low stock: 24 <= 30, seeded via receipts)
        p_helmet = inv.create_product(
            name="Safety Helmets",
            sku="SH007",
            category_id=cat_safety.id,
            uom="unit",
            reorder_level=30,
            description="Industrial EN397 certified hard hats with ratcheted suspension.",
            initial_stock=0,
            initial_location_id=None,
            user=manager
        )

        # 8. Work Gloves WG008 pair 50 (Stock seeded via receipts)
        p_gloves = inv.create_product(
            name="Work Gloves",
            sku="WG008",
            category_id=cat_safety.id,
            uom="pair",
            reorder_level=50,
            description="Nitrile coated abrasion-resistant heavy duty grip gloves (Size L).",
            initial_stock=0,
            initial_location_id=None,
            user=manager
        )

        print("Seeding 25-day realistic transaction history...")
        now = datetime.utcnow()

        # Day -22: Receipt REC-0001
        rec1 = inv.create_receipt(
            supplier_id=sup_metro.id,
            destination_location_id=loc_main_stock.id,
            scheduled_date=now - timedelta(days=22),
            source_document="PO/2026/0112",
            notes="Initial quarterly bulk stock delivery",
            items=[
                {'product_id': p_steel.id, 'quantity': 180},
                {'product_id': p_chair.id, 'quantity': 140}
            ],
            user=manager
        )
        inv.confirm_receipt(rec1.id, user=manager)
        inv.receive_goods(rec1.id, {str(rec1.items[0].id): 180, str(rec1.items[1].id): 140}, user=staff)
        inv.validate_receipt(rec1.id, user=manager)

        # Day -19: Transfer INT-0001
        tr1 = inv.create_transfer(
            source_location_id=loc_main_stock.id,
            destination_location_id=loc_main_prod.id,
            scheduled_date=now - timedelta(days=19),
            reason="Production line feed - shift batch 1",
            priority="Normal",
            items=[{'product_id': p_steel.id, 'quantity': 75}],
            user=staff
        )
        inv.complete_transfer(tr1.id, user=staff)

        # Day -17: Delivery DO-0001
        do1 = inv.create_delivery(
            customer_id=cust_abc.id,
            source_location_id=loc_main_stock.id,
            scheduled_date=now - timedelta(days=17),
            priority="Normal",
            source_document="SO-2026-081",
            notes="Factory structural allotment",
            items=[{'product_id': p_steel.id, 'quantity': 60}],
            user=manager
        )
        inv.confirm_delivery(do1.id, user=manager)
        inv.pick_delivery(do1.id, user=staff)
        inv.pack_delivery(do1.id, user=staff)
        inv.validate_delivery(do1.id, user=manager)

        # Day -14: Receipt REC-0002
        rec2 = inv.create_receipt(
            supplier_id=sup_prime.id,
            destination_location_id=loc_main_stock.id,
            scheduled_date=now - timedelta(days=14),
            source_document="PO/2026/0204",
            notes="Stationery and facility supplies",
            items=[
                {'product_id': p_paper.id, 'quantity': 305},
                {'product_id': p_gloves.id, 'quantity': 200}
            ],
            user=manager
        )
        inv.confirm_receipt(rec2.id, user=manager)
        inv.receive_goods(rec2.id, {str(rec2.items[0].id): 305, str(rec2.items[1].id): 200}, user=staff)
        inv.validate_receipt(rec2.id, user=manager)

        # Day -11: Delivery DO-0002
        do2 = inv.create_delivery(
            customer_id=cust_horizon.id,
            source_location_id=loc_main_stock.id,
            scheduled_date=now - timedelta(days=11),
            priority="Normal",
            source_document="SO-2026-104",
            notes="Commercial floor setup",
            items=[{'product_id': p_chair.id, 'quantity': 22}],
            user=manager
        )
        inv.confirm_delivery(do2.id, user=manager)
        inv.pick_delivery(do2.id, user=staff)
        inv.pack_delivery(do2.id, user=staff)
        inv.validate_delivery(do2.id, user=manager)

        # Day -9: Receipt REC-0003
        rec3 = inv.create_receipt(
            supplier_id=sup_metro.id,
            destination_location_id=loc_main_stock.id,
            scheduled_date=now - timedelta(days=9),
            source_document="PO/2026/0315",
            notes="Safety equipment procurement",
            items=[{'product_id': p_helmet.id, 'quantity': 24}],
            user=manager
        )
        inv.confirm_receipt(rec3.id, user=manager)
        inv.receive_goods(rec3.id, {str(rec3.items[0].id): 24}, user=staff)
        inv.validate_receipt(rec3.id, user=manager)

        # Day -8: Transfer INT-0002
        tr2 = inv.create_transfer(
            source_location_id=loc_wh2_stock.id,
            destination_location_id=loc_main_stock.id,
            scheduled_date=now - timedelta(days=8),
            reason="Repackaging buffer restock",
            priority="Normal",
            items=[{'product_id': p_box.id, 'quantity': 120}],
            user=manager
        )
        inv.complete_transfer(tr2.id, user=staff)

        # Day -6: Transfer INT-0003
        tr3 = inv.create_transfer(
            source_location_id=loc_main_stock.id,
            destination_location_id=loc_main_prod.id,
            scheduled_date=now - timedelta(days=6),
            reason="Fabrication line top-up batch",
            priority="Normal",
            items=[{'product_id': p_steel.id, 'quantity': 10}],
            user=manager
        )
        inv.complete_transfer(tr3.id, user=staff)

        # Day -4: Delivery DO-0003
        do3 = inv.create_delivery(
            customer_id=cust_northstar.id,
            source_location_id=loc_main_stock.id,
            scheduled_date=now - timedelta(days=4),
            priority="Urgent",
            source_document="SO-2026-149",
            notes="Retail distribution packaging dispatch",
            items=[
                {'product_id': p_paper.id, 'quantity': 35},
                {'product_id': p_box.id, 'quantity': 40}
            ],
            user=manager
        )
        inv.confirm_delivery(do3.id, user=manager)
        inv.pick_delivery(do3.id, user=staff)
        inv.pack_delivery(do3.id, user=staff)
        inv.validate_delivery(do3.id, user=manager)

        print("Seeding target operational states...")

        # 1. ONE RECEIPT WAITING: REC-0004
        rec_waiting = inv.create_receipt(
            supplier_id=sup_prime.id,
            destination_location_id=loc_main_stock.id,
            scheduled_date=now + timedelta(days=1),
            source_document="PO/2026/0488",
            notes="Awaiting truck arrival at Dock 2",
            items=[{'product_id': p_paper.id, 'quantity': 80}],
            user=manager
        )
        inv.confirm_receipt(rec_waiting.id, user=manager)

        # 2. ONE RECEIPT RECEIVED BUT NOT YET VALIDATED: REC-0005
        rec_received = inv.create_receipt(
            supplier_id=sup_metro.id,
            destination_location_id=loc_main_stock.id,
            scheduled_date=now,
            source_document="PO/2026/0493",
            notes="Goods received at Dock 1; inspected with minor vendor packing discrepancy",
            items=[{'product_id': p_steel.id, 'quantity': 200}],
            user=manager
        )
        inv.confirm_receipt(rec_received.id, user=manager)
        inv.receive_goods(rec_received.id, {str(rec_received.items[0].id): 197}, user=staff)

        # Additional receipt for staff validation testing: REC-0006
        rec_staff_test = inv.create_receipt(
            supplier_id=sup_metro.id,
            destination_location_id=loc_main_stock.id,
            scheduled_date=now,
            source_document="PO/2026/0501",
            notes="Scheduled steel rod consignment for afternoon shift",
            items=[{'product_id': p_steel.id, 'quantity': 60}],
            user=manager
        )
        inv.confirm_receipt(rec_staff_test.id, user=manager)

        # 3. DELIVERIES:
        # A. Delivery Ready (DO-0004)
        del_ready = inv.create_delivery(
            customer_id=cust_abc.id,
            source_location_id=loc_main_stock.id,
            scheduled_date=now,
            priority="Normal",
            source_document="SO-2026-201",
            notes="Production plant office expansion",
            items=[{'product_id': p_chair.id, 'quantity': 15}],
            user=manager
        )
        inv.confirm_delivery(del_ready.id, user=manager)

        # B. Delivery Picked (DO-0005)
        del_picked = inv.create_delivery(
            customer_id=cust_horizon.id,
            source_location_id=loc_main_stock.id,
            scheduled_date=now,
            priority="Normal",
            source_document="SO-2026-202",
            notes="Stationery delivery",
            items=[{'product_id': p_paper.id, 'quantity': 20}],
            user=manager
        )
        inv.confirm_delivery(del_picked.id, user=manager)
        inv.pick_delivery(del_picked.id, user=staff)

        # C. Delivery Packed (DO-0006)
        del_packed = inv.create_delivery(
            customer_id=cust_northstar.id,
            source_location_id=loc_wh2_stock.id,
            scheduled_date=now,
            priority="Normal",
            source_document="SO-2026-203",
            notes="Corrugated carton wholesale lot",
            items=[{'product_id': p_box.id, 'quantity': 50}],
            user=manager
        )
        inv.confirm_delivery(del_packed.id, user=manager)
        inv.pick_delivery(del_packed.id, user=staff)
        inv.pack_delivery(del_packed.id, user=staff)

        # D. Delivery Waiting for stock: DO-0007 (LP005 has 0 stock!)
        del_waiting = inv.create_delivery(
            customer_id=cust_abc.id,
            source_location_id=loc_main_stock.id,
            scheduled_date=now,
            priority="Urgent",
            source_document="SO-2026-204",
            notes="Assembly line shutdown pending lighting fixture installation",
            items=[{'product_id': p_led.id, 'quantity': 12}],
            user=manager
        )
        inv.confirm_delivery(del_waiting.id, user=manager)

        # Additional delivery for staff testing DO-0008
        del_staff_test = inv.create_delivery(
            customer_id=cust_abc.id,
            source_location_id=loc_main_stock.id,
            scheduled_date=now,
            priority="Urgent",
            source_document="SO-2026-208",
            notes="Shift test delivery",
            items=[{'product_id': p_paper.id, 'quantity': 10}],
            user=manager
        )
        inv.confirm_delivery(del_staff_test.id, user=manager)

        # 4. ONE TRANSFER READY: INT-0004
        tr_ready = inv.create_transfer(
            source_location_id=loc_main_stock.id,
            destination_location_id=loc_main_prod.id,
            scheduled_date=now,
            reason="Material replenishment for fabrication bay",
            priority="Normal",
            items=[{'product_id': p_steel.id, 'quantity': 45}],
            user=manager
        )

        # Additional transfer for staff completion test INT-0005
        tr_staff_test = inv.create_transfer(
            source_location_id=loc_main_stock.id,
            destination_location_id=loc_main_prod.id,
            scheduled_date=now,
            reason="Fabrication line top-up",
            priority="Normal",
            items=[{'product_id': p_steel.id, 'quantity': 15}],
            user=manager
        )

        # 5. ONE SUBMITTED COUNT WAITING FOR APPROVAL (Counted): ADJ-0004
        adj_counted = inv.create_adjustment(
            title="Zone B Quarterly Routine Review",
            location_id=loc_main_stock.id,
            assigned_to_id=staff.id,
            items=[{'product_id': p_gloves.id}],
            notes="Routine review of PPE storage",
            user=manager
        )
        cur_wg_stock = get_on_hand(p_gloves.id, loc_main_stock.id)
        inv.submit_count(adj_counted.id, {
            str(adj_counted.items[0].id): {
                'counted_quantity': cur_wg_stock - 3,
                'reason': 'Missing'
            }
        }, user=staff)

        # 6. Additional count sheet waiting to be counted (Draft): ADJ-0005
        adj_staff_test = inv.create_adjustment(
            title="Warehouse Staff Audit Sheet ADJ-0005",
            location_id=loc_main_stock.id,
            assigned_to_id=staff.id,
            items=[{'product_id': p_helmet.id}],
            notes="Audit sheet for staff verification testing",
            user=manager
        )

        # Spread timestamps of historical movements for realistic ledger
        movements = StockMovement.query.order_by(StockMovement.id.asc()).all()
        step_days = 24.0 / max(1, len(movements))
        for idx, m in enumerate(movements):
            m.at = now - timedelta(days=24 - (idx * step_days), hours=(idx % 6) + 8, minutes=(idx * 17) % 60)
        db.session.commit()

        # Synchronize double-entry StockQuant table
        sync_all_quants()

        print("\nSeed completed successfully!")
        print("--------------------------------------------------")
        print("Users created:")
        print("  - Ridhima Sharma: manager@stocksense.demo / Manager@2026 (INVENTORY_MANAGER)")
        print("  - Aman Kumar:     staff@stocksense.demo   / Staff@2026   (WAREHOUSE_STAFF)")
        print("  - Neha Joshi:     neha.joshi@stocksense.demo / Staff@2026 (WAREHOUSE_STAFF)")
        print("\nInventory Status Summary:")
        for p in Product.query.order_by(Product.sku).all():
            oh = get_on_hand(p.id)
            res = inv.get_available(p.id)
            status = get_status(p, oh)
            print(f"  [{p.sku}] {p.name:<20}: On Hand={oh:>6.1f} {p.uom:<5} (Reorder={p.reorder_level:>3}) -> Status: {status}")
        print("--------------------------------------------------")

if __name__ == '__main__':
    seed_database()
