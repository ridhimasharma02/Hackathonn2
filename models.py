from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    role = db.Column(db.String(30), nullable=False, default='WAREHOUSE_STAFF')  # INVENTORY_MANAGER, WAREHOUSE_STAFF
    phone = db.Column(db.String(30), nullable=True)
    password_hash = db.Column(db.String(256), nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def set_password(self, password, use_argon2=False):
        if use_argon2:
            try:
                from argon2 import PasswordHasher
                ph = PasswordHasher()
                self.password_hash = ph.hash(password)
                return
            except Exception:
                pass
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        if self.password_hash and self.password_hash.startswith('$argon2'):
            try:
                from argon2 import PasswordHasher
                ph = PasswordHasher()
                return ph.verify(self.password_hash, password)
            except Exception:
                return False
        return check_password_hash(self.password_hash, password)

    @property
    def is_manager(self):
        return self.role == 'INVENTORY_MANAGER'

    @property
    def is_staff(self):
        return self.role == 'WAREHOUSE_STAFF'


class Category(db.Model):
    __tablename__ = 'categories'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    products = db.relationship('Product', backref='category', lazy=True)


class Product(db.Model):
    __tablename__ = 'products'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    sku = db.Column(db.String(50), unique=True, nullable=False, index=True)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=True)
    uom = db.Column(db.String(20), nullable=False, default='unit')  # unit, kg, sheet, ream, pair, etc.
    reorder_level = db.Column(db.Integer, nullable=False, default=0)
    min_stock_level = db.Column(db.Float, nullable=False, default=0.0)
    description = db.Column(db.Text, nullable=True)
    archived = db.Column(db.Boolean, default=False, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    creator = db.relationship('User', backref='created_products', foreign_keys=[created_by])
    movements = db.relationship('StockMovement', backref='product', lazy='dynamic')


class Warehouse(db.Model):
    __tablename__ = 'warehouses'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(20), unique=True, nullable=False)
    address = db.Column(db.String(255), nullable=True)
    active = db.Column(db.Boolean, default=True, nullable=False)
    locations = db.relationship('Location', backref='warehouse', lazy=True)


class Location(db.Model):
    __tablename__ = 'locations'

    id = db.Column(db.Integer, primary_key=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=True)
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(50), unique=True, nullable=False, index=True)  # e.g. MAIN/STOCK, MAIN/PROD
    type = db.Column(db.String(30), nullable=False, default='INTERNAL')  # INTERNAL, VENDOR, CUSTOMER, INVENTORY_LOSS
    parent_location_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=True)
    active = db.Column(db.Boolean, default=True, nullable=False)

    parent_location = db.relationship('Location', remote_side=[id], backref='sub_locations')


class Supplier(db.Model):
    __tablename__ = 'suppliers'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    contact = db.Column(db.String(100), nullable=True)
    city = db.Column(db.String(100), nullable=True)
    receipts = db.relationship('Receipt', backref='supplier', lazy=True)


class Customer(db.Model):
    __tablename__ = 'customers'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    contact = db.Column(db.String(100), nullable=True)
    city = db.Column(db.String(100), nullable=True)
    deliveries = db.relationship('Delivery', backref='customer', lazy=True)


class Receipt(db.Model):
    __tablename__ = 'receipts'

    id = db.Column(db.Integer, primary_key=True)
    reference = db.Column(db.String(30), unique=True, nullable=False, index=True)  # REC-0001
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=False)
    destination_location_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=False)
    scheduled_date = db.Column(db.DateTime, nullable=True)
    source_document = db.Column(db.String(100), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), nullable=False, default='Draft')  # Draft -> Waiting -> Ready -> Done, Canceled
    received_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    done_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    done_at = db.Column(db.DateTime, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    destination_location = db.relationship('Location', foreign_keys=[destination_location_id])
    receiver = db.relationship('User', foreign_keys=[received_by])
    validator = db.relationship('User', foreign_keys=[done_by])
    creator = db.relationship('User', foreign_keys=[created_by])
    items = db.relationship('ReceiptItem', backref='receipt', cascade='all, delete-orphan', lazy=True)


class ReceiptItem(db.Model):
    __tablename__ = 'receipt_items'

    id = db.Column(db.Integer, primary_key=True)
    receipt_id = db.Column(db.Integer, db.ForeignKey('receipts.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    received_quantity = db.Column(db.Float, nullable=False, default=0.0)

    product = db.relationship('Product')


class Delivery(db.Model):
    __tablename__ = 'deliveries'

    id = db.Column(db.Integer, primary_key=True)
    reference = db.Column(db.String(30), unique=True, nullable=False, index=True)  # DO-0001
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
    source_location_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=False)
    scheduled_date = db.Column(db.DateTime, nullable=True)
    priority = db.Column(db.String(20), nullable=False, default='Normal')  # Normal, Urgent
    source_document = db.Column(db.String(100), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), nullable=False, default='Draft')  # Draft -> Waiting -> Ready -> Picked -> Packed -> Done, Canceled
    picked_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    packed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    done_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    done_at = db.Column(db.DateTime, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    source_location = db.relationship('Location', foreign_keys=[source_location_id])
    picker = db.relationship('User', foreign_keys=[picked_by])
    packer = db.relationship('User', foreign_keys=[packed_by])
    validator = db.relationship('User', foreign_keys=[done_by])
    creator = db.relationship('User', foreign_keys=[created_by])
    items = db.relationship('DeliveryItem', backref='delivery', cascade='all, delete-orphan', lazy=True)


class DeliveryItem(db.Model):
    __tablename__ = 'delivery_items'

    id = db.Column(db.Integer, primary_key=True)
    delivery_id = db.Column(db.Integer, db.ForeignKey('deliveries.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Float, nullable=False)

    product = db.relationship('Product')


class Transfer(db.Model):
    __tablename__ = 'transfers'

    id = db.Column(db.Integer, primary_key=True)
    reference = db.Column(db.String(30), unique=True, nullable=False, index=True)  # INT-0001
    source_location_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=False)
    destination_location_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=False)
    scheduled_date = db.Column(db.DateTime, nullable=True)
    reason = db.Column(db.String(255), nullable=True)
    priority = db.Column(db.String(20), nullable=False, default='Normal')
    status = db.Column(db.String(20), nullable=False, default='Draft')  # Draft -> Waiting -> Ready -> Done, Canceled
    done_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    done_at = db.Column(db.DateTime, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    source_location = db.relationship('Location', foreign_keys=[source_location_id])
    destination_location = db.relationship('Location', foreign_keys=[destination_location_id])
    completer = db.relationship('User', foreign_keys=[done_by])
    creator = db.relationship('User', foreign_keys=[created_by])
    items = db.relationship('TransferItem', backref='transfer', cascade='all, delete-orphan', lazy=True)


class TransferItem(db.Model):
    __tablename__ = 'transfer_items'

    id = db.Column(db.Integer, primary_key=True)
    transfer_id = db.Column(db.Integer, db.ForeignKey('transfers.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Float, nullable=False)

    product = db.relationship('Product')


class Adjustment(db.Model):
    __tablename__ = 'adjustments'

    id = db.Column(db.Integer, primary_key=True)
    reference = db.Column(db.String(30), unique=True, nullable=False, index=True)  # ADJ-0001
    title = db.Column(db.String(150), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='Draft')  # Draft -> Counted -> Approved, Rejected, Canceled
    assigned_to = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    counted_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    counted_at = db.Column(db.DateTime, nullable=True)
    done_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    done_at = db.Column(db.DateTime, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    assignee = db.relationship('User', foreign_keys=[assigned_to])
    counter = db.relationship('User', foreign_keys=[counted_by])
    approver = db.relationship('User', foreign_keys=[done_by])
    creator = db.relationship('User', foreign_keys=[created_by])
    items = db.relationship('AdjustmentItem', backref='adjustment', cascade='all, delete-orphan', lazy=True)


class AdjustmentItem(db.Model):
    __tablename__ = 'adjustment_items'

    id = db.Column(db.Integer, primary_key=True)
    adjustment_id = db.Column(db.Integer, db.ForeignKey('adjustments.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=False)
    system_quantity = db.Column(db.Float, nullable=False, default=0.0)
    counted_quantity = db.Column(db.Float, nullable=True)
    applied_difference = db.Column(db.Float, nullable=False, default=0.0)
    reason = db.Column(db.String(100), nullable=True)  # Damaged, Missing, Counting Error, Found Stock, Other, Opening stock

    product = db.relationship('Product')
    location = db.relationship('Location')


class StockMovement(db.Model):
    __tablename__ = 'stock_movements'

    id = db.Column(db.Integer, primary_key=True)
    at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    reference = db.Column(db.String(50), nullable=False, index=True)
    doc_type = db.Column(db.String(30), nullable=False)  # Receipt, Delivery, Internal Transfer, Adjustment
    doc_id = db.Column(db.Integer, nullable=True)
    operation = db.Column(db.String(50), nullable=False)  # Receipt, Delivery, Internal Transfer, Adjustment
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False, index=True)
    from_location_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=True, index=True)
    to_location_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=True, index=True)
    counterparty = db.Column(db.String(150), nullable=True)
    quantity = db.Column(db.Float, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    from_location = db.relationship('Location', foreign_keys=[from_location_id])
    to_location = db.relationship('Location', foreign_keys=[to_location_id])
    user = db.relationship('User', foreign_keys=[user_id])


class ActivityLog(db.Model):
    __tablename__ = 'activity_logs'

    id = db.Column(db.Integer, primary_key=True)
    doc_type = db.Column(db.String(30), nullable=False, index=True)
    doc_id = db.Column(db.Integer, nullable=True, index=True)
    at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    action = db.Column(db.String(100), nullable=False)
    note = db.Column(db.Text, nullable=True)

    user = db.relationship('User', foreign_keys=[user_id])


class Sequence(db.Model):
    __tablename__ = 'sequences'

    prefix = db.Column(db.String(10), primary_key=True)  # REC, DO, INT, ADJ
    last_number = db.Column(db.Integer, default=0, nullable=False)


class PasswordResetOTP(db.Model):
    __tablename__ = 'password_reset_otps'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), nullable=False, index=True)
    otp = db.Column(db.String(6), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


# =============================================================================
# DOUBLE-ENTRY INVENTORY ENGINE (SPEC SECTION 3)
# =============================================================================

class StockQuant(db.Model):
    """
    Fast location snapshot table.
    Enforces that stock is tracked as quants at specific locations.
    """
    __tablename__ = 'stock_quants'

    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), primary_key=True)
    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'), primary_key=True)
    quantity = db.Column(db.Float, nullable=False, default=0.0)

    product = db.relationship('Product', backref=db.backref('quants', lazy='dynamic'))
    location = db.relationship('Location', backref=db.backref('quants', lazy='dynamic'))


class StockMove(db.Model):
    """
    Immutable ledger of double-entry moves between source and destination locations.
    """
    __tablename__ = 'stock_moves'

    id = db.Column(db.Integer, primary_key=True)
    operation_id = db.Column(db.Integer, nullable=True, index=True)
    reference = db.Column(db.String(64), nullable=True, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False, index=True)
    quantity = db.Column(db.Float, nullable=False)
    source_location_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=True, index=True)
    destination_location_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    product = db.relationship('Product')
    source_location = db.relationship('Location', foreign_keys=[source_location_id])
    destination_location = db.relationship('Location', foreign_keys=[destination_location_id])
    user = db.relationship('User', foreign_keys=[user_id])


class StockOperation(db.Model):
    """
    Operations Header (Receipts, Deliveries, Internal Moves, Adjustments)
    """
    __tablename__ = 'stock_operations'

    id = db.Column(db.Integer, primary_key=True)
    reference_number = db.Column(db.String(64), unique=True, nullable=False, index=True)
    operation_type = db.Column(db.String(30), nullable=False)  # RECEIPT, DELIVERY, INTERNAL, ADJUSTMENT
    status = db.Column(db.String(30), nullable=False, default='DRAFT')  # DRAFT, WAITING, READY, DONE, CANCELED
    source_location_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=True)
    destination_location_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    done_at = db.Column(db.DateTime, nullable=True)

    source_location = db.relationship('Location', foreign_keys=[source_location_id])
    destination_location = db.relationship('Location', foreign_keys=[destination_location_id])
    creator = db.relationship('User', foreign_keys=[created_by])
