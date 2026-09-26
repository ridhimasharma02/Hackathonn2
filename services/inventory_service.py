from datetime import datetime
from models import (
    db, Product, Category, Warehouse, Location, Supplier, Customer,
    Receipt, ReceiptItem, Delivery, DeliveryItem, Transfer, TransferItem,
    Adjustment, AdjustmentItem, StockMovement, ActivityLog, Sequence
)
from services.permissions import check_permission
from services.stock_engine import (
    get_on_hand, get_available, check_delivery_shortages, record_stock_quant_and_move
)

class BusinessRuleError(Exception):
    """Raised when an inventory or operational business rule is violated."""
    pass


def next_reference(prefix):
    """
    Generates the next sequential reference code: e.g. REC-0001, DO-0001, INT-0001, ADJ-0001.
    Uses database row locking to avoid race conditions.
    """
    seq = Sequence.query.filter_by(prefix=prefix).with_for_update().first()
    if not seq:
        seq = Sequence(prefix=prefix, last_number=0)
        db.session.add(seq)

    seq.last_number += 1
    db.session.flush()
    return f"{prefix}-{seq.last_number:04d}"


def log_activity(doc_type, doc_id, user_id, action, note=None):
    """Records an immutable activity log entry."""
    entry = ActivityLog(
        doc_type=doc_type,
        doc_id=doc_id,
        user_id=user_id,
        action=action,
        note=note,
        at=datetime.utcnow()
    )
    db.session.add(entry)
    return entry


# =========================================================================
# PRODUCTS & INVENTORY ALLOCATION
# =========================================================================

def create_product(name, sku, category_id, uom, reorder_level=0, description=None,
                   initial_stock=0, initial_location_id=None, user=None):
    """
    Creates a new product with uppercase unique SKU and reorder level >= 0.
    If initial stock is specified, posts an approved 'Opening stock' adjustment.
    """
    check_permission('products:create', user)

    name = (name or '').strip()
    sku = (sku or '').strip().upper()
    uom = (uom or '').strip() or 'unit'

    if not name:
        raise BusinessRuleError("Product name is required.")
    if not sku:
        raise BusinessRuleError("Product SKU is required.")

    try:
        reorder_level = int(reorder_level)
    except (ValueError, TypeError):
        raise BusinessRuleError("Reorder level must be a valid integer.")

    if reorder_level < 0:
        raise BusinessRuleError("Reorder level must be >= 0.")

    existing = Product.query.filter(db.func.upper(Product.sku) == sku).first()
    if existing:
        raise BusinessRuleError(f"Product with SKU '{sku}' already exists.")

    try:
        initial_stock = float(initial_stock or 0)
    except (ValueError, TypeError):
        raise BusinessRuleError("Initial stock must be a valid number.")

    if initial_stock < 0:
        raise BusinessRuleError("Initial stock cannot be negative.")

    if initial_stock > 0 and not initial_location_id:
        raise BusinessRuleError("Initial stock location is required when initial stock > 0.")

    product = Product(
        name=name,
        sku=sku,
        category_id=category_id if category_id else None,
        uom=uom,
        reorder_level=reorder_level,
        min_stock_level=float(reorder_level),
        description=description.strip() if description else None,
        created_by=user.id if user else None,
        created_at=datetime.utcnow(),
        archived=False
    )
    db.session.add(product)
    db.session.flush()

    log_activity('Product', product.id, user.id if user else 1, 'Product created', f"Created SKU: {product.sku}")

    # If opening stock is provided, post an approved Opening Stock adjustment
    if initial_stock > 0:
        loc = Location.query.get(initial_location_id)
        if not loc or not loc.active:
            raise BusinessRuleError("Selected initial stock location is invalid or inactive.")

        adj_ref = next_reference('ADJ')
        adj = Adjustment(
            reference=adj_ref,
            title=f"Opening Stock - {product.name}",
            status='Approved',
            assigned_to=user.id if user else None,
            counted_by=user.id if user else None,
            counted_at=datetime.utcnow(),
            done_by=user.id if user else None,
            done_at=datetime.utcnow(),
            notes="Initial stock recorded at product creation.",
            created_by=user.id if user else 1,
            created_at=datetime.utcnow()
        )
        db.session.add(adj)
        db.session.flush()

        item = AdjustmentItem(
            adjustment_id=adj.id,
            product_id=product.id,
            location_id=loc.id,
            system_quantity=0.0,
            counted_quantity=initial_stock,
            applied_difference=initial_stock,
            reason="Opening stock"
        )
        db.session.add(item)

        movement = StockMovement(
            reference=adj_ref,
            doc_type='Adjustment',
            doc_id=adj.id,
            operation='Adjustment',
            product_id=product.id,
            from_location_id=None,
            to_location_id=loc.id,
            counterparty='Opening Stock',
            quantity=initial_stock,
            user_id=user.id if user else 1,
            at=datetime.utcnow()
        )
        db.session.add(movement)
        record_stock_quant_and_move(
            product_id=product.id,
            quantity=initial_stock,
            source_location_id=None,
            destination_location_id=loc.id,
            reference=adj_ref,
            user_id=user.id if user else 1,
            operation_id=adj.id
        )
        log_activity('Adjustment', adj.id, user.id if user else 1, 'Opening stock posted',
                     f"+{initial_stock} {product.uom} to {loc.code}")

    db.session.commit()
    return product


def update_product(product_id, name, category_id, uom, reorder_level=0, description=None, user=None):
    """Updates an existing product."""
    check_permission('products:edit', user)

    product = Product.query.get_or_404(product_id)
    name = (name or '').strip()
    uom = (uom or '').strip() or 'unit'

    if not name:
        raise BusinessRuleError("Product name is required.")

    try:
        reorder_level = int(reorder_level)
    except (ValueError, TypeError):
        raise BusinessRuleError("Reorder level must be a valid integer.")

    if reorder_level < 0:
        raise BusinessRuleError("Reorder level must be >= 0.")

    product.name = name
    product.category_id = category_id if category_id else None
    product.uom = uom
    product.reorder_level = reorder_level
    product.description = description.strip() if description else None

    log_activity('Product', product.id, user.id if user else 1, 'Product updated', f"Updated {product.sku}")
    db.session.commit()
    return product


def archive_product(product_id, user=None):
    """Archives a product."""
    check_permission('products:archive', user)
    product = Product.query.get_or_404(product_id)
    product.archived = True
    log_activity('Product', product.id, user.id if user else 1, 'Product archived', f"Archived {product.sku}")
    db.session.commit()
    return product


# =========================================================================
# RECEIPTS (INWARD)
# Draft -> Waiting -> Ready -> Done (Canceled allowed before Done)
# =========================================================================

def create_receipt(supplier_id, destination_location_id, scheduled_date=None,
                   source_document=None, notes=None, items=None, user=None):
    """Creates a new inward receipt in Draft state."""
    check_permission('receipts:create', user)

    supplier = Supplier.query.get(supplier_id)
    if not supplier:
        raise BusinessRuleError("Supplier does not exist.")

    location = Location.query.get(destination_location_id)
    if not location or not location.active:
        raise BusinessRuleError("Destination location is invalid or inactive.")

    if not items:
        raise BusinessRuleError("At least one product line is required.")

    ref = next_reference('REC')
    receipt = Receipt(
        reference=ref,
        supplier_id=supplier.id,
        destination_location_id=location.id,
        scheduled_date=scheduled_date,
        source_document=source_document.strip() if source_document else None,
        notes=notes.strip() if notes else None,
        status='Draft',
        created_by=user.id if user else 1,
        created_at=datetime.utcnow()
    )
    db.session.add(receipt)
    db.session.flush()

    for itm in items:
        prod_id = itm.get('product_id')
        qty = float(itm.get('quantity', 0))
        if qty <= 0:
            raise BusinessRuleError("Line quantity must be greater than zero.")
        prod = Product.query.get(prod_id)
        if not prod or prod.archived:
            raise BusinessRuleError(f"Product ID {prod_id} is invalid or archived.")

        receipt_item = ReceiptItem(
            receipt_id=receipt.id,
            product_id=prod.id,
            quantity=qty,
            received_quantity=0.0
        )
        db.session.add(receipt_item)

    log_activity('Receipt', receipt.id, user.id if user else 1, 'Receipt created', f"Created {receipt.reference}")
    db.session.commit()
    return receipt


def confirm_receipt(receipt_id, user=None):
    """Manager confirms receipt: Draft -> Waiting."""
    check_permission('receipts:confirm', user)
    receipt = Receipt.query.get_or_404(receipt_id)

    if receipt.status != 'Draft':
        raise BusinessRuleError(f"Cannot confirm receipt in '{receipt.status}' status. Only Draft receipts can be confirmed.")

    receipt.status = 'Waiting'
    log_activity('Receipt', receipt.id, user.id if user else 1, 'Receipt confirmed',
                 'Status set to Waiting for arrival')
    db.session.commit()
    return receipt


def receive_goods(receipt_id, received_items_map, user=None):
    """
    Staff or Manager records received quantities per line.
    Status transitions Waiting -> Ready.
    Stock does NOT change yet!
    """
    check_permission('receipts:receive', user)
    receipt = Receipt.query.get_or_404(receipt_id)

    if receipt.status not in ('Waiting', 'Ready'):
        raise BusinessRuleError(f"Cannot record goods receipt in '{receipt.status}' status.")

    for item in receipt.items:
        key = str(item.id)
        if key in received_items_map:
            try:
                rec_qty = float(received_items_map[key])
            except (ValueError, TypeError):
                raise BusinessRuleError("Received quantity must be a valid number.")
            if rec_qty < 0:
                raise BusinessRuleError("Received quantity cannot be negative.")
            item.received_quantity = rec_qty

    receipt.received_by = user.id if user else None
    receipt.status = 'Ready'

    log_activity('Receipt', receipt.id, user.id if user else 1, 'Goods received',
                 'Recorded received quantities; marked Ready for manager validation')
    db.session.commit()
    return receipt


def validate_receipt(receipt_id, user=None):
    """
    Manager validates receipt: Ready -> Done.
    Creates StockMovement per line (supplier -> destination). Stock increases only now!
    """
    check_permission('receipts:validate', user)
    receipt = Receipt.query.get_or_404(receipt_id)

    if receipt.status != 'Ready':
        raise BusinessRuleError(f"Cannot validate receipt in '{receipt.status}' status. Only Ready receipts can be validated.")

    receipt.status = 'Done'
    receipt.done_by = user.id if user else None
    receipt.done_at = datetime.utcnow()

    # Create movements for lines where received_quantity > 0
    for item in receipt.items:
        if item.received_quantity > 0:
            movement = StockMovement(
                reference=receipt.reference,
                doc_type='Receipt',
                doc_id=receipt.id,
                operation='Receipt',
                product_id=item.product_id,
                from_location_id=None,
                to_location_id=receipt.destination_location_id,
                counterparty=receipt.supplier.name,
                quantity=item.received_quantity,
                user_id=user.id if user else 1,
                at=datetime.utcnow()
            )
            db.session.add(movement)
            record_stock_quant_and_move(
                product_id=item.product_id,
                quantity=item.received_quantity,
                source_location_id=None,
                destination_location_id=receipt.destination_location_id,
                reference=receipt.reference,
                user_id=user.id if user else 1,
                operation_id=receipt.id
            )

    log_activity('Receipt', receipt.id, user.id if user else 1, 'Receipt validated',
                 f"Validated receipt and posted stock into {receipt.destination_location.code}")
    db.session.commit()
    return receipt


def cancel_receipt(receipt_id, user=None):
    """Cancels a receipt before Done."""
    check_permission('receipts:cancel', user)
    receipt = Receipt.query.get_or_404(receipt_id)

    if receipt.status == 'Done':
        raise BusinessRuleError("Cannot cancel a completed receipt.")

    receipt.status = 'Canceled'
    log_activity('Receipt', receipt.id, user.id if user else 1, 'Receipt canceled', 'Receipt canceled')
    db.session.commit()
    return receipt


# =========================================================================
# DELIVERIES (OUTWARD)
# Draft -> Waiting -> Ready -> Picked -> Packed -> Done (Canceled allowed before Done)
# =========================================================================

def create_delivery(customer_id, source_location_id, scheduled_date=None,
                    priority='Normal', source_document=None, notes=None, items=None, user=None):
    """Creates a new outward delivery order in Draft state."""
    check_permission('deliveries:create', user)

    customer = Customer.query.get(customer_id)
    if not customer:
        raise BusinessRuleError("Customer does not exist.")

    location = Location.query.get(source_location_id)
    if not location or not location.active:
        raise BusinessRuleError("Source location is invalid or inactive.")

    if not items:
        raise BusinessRuleError("At least one product line is required.")

    if priority not in ('Normal', 'Urgent'):
        priority = 'Normal'

    ref = next_reference('DO')
    delivery = Delivery(
        reference=ref,
        customer_id=customer.id,
        source_location_id=location.id,
        scheduled_date=scheduled_date,
        priority=priority,
        source_document=source_document.strip() if source_document else None,
        notes=notes.strip() if notes else None,
        status='Draft',
        created_by=user.id if user else 1,
        created_at=datetime.utcnow()
    )
    db.session.add(delivery)
    db.session.flush()

    for itm in items:
        prod_id = itm.get('product_id')
        qty = float(itm.get('quantity', 0))
        if qty <= 0:
            raise BusinessRuleError("Line quantity must be greater than zero.")
        prod = Product.query.get(prod_id)
        if not prod or prod.archived:
            raise BusinessRuleError(f"Product ID {prod_id} is invalid or archived.")

        del_item = DeliveryItem(
            delivery_id=delivery.id,
            product_id=prod.id,
            quantity=qty
        )
        db.session.add(del_item)

    log_activity('Delivery', delivery.id, user.id if user else 1, 'Delivery created', f"Created {delivery.reference}")
    db.session.commit()
    return delivery


def confirm_delivery(delivery_id, user=None):
    """
    Manager confirms delivery order:
    Transitions to 'Ready' if every line has enough available stock at source,
    otherwise transitions to 'Waiting'.
    """
    check_permission('deliveries:confirm', user)
    delivery = Delivery.query.get_or_404(delivery_id)

    if delivery.status != 'Draft':
        raise BusinessRuleError(f"Cannot confirm delivery in '{delivery.status}' status.")

    has_shortage, shortages = check_delivery_shortages(delivery)

    if not has_shortage:
        delivery.status = 'Ready'
        action_note = "Stock available; order marked Ready for picking."
    else:
        delivery.status = 'Waiting'
        shortage_desc = ", ".join([f"{s['product'].sku} short by {s['shortage']}" for s in shortages])
        action_note = f"Insufficient stock; set to Waiting ({shortage_desc})"

    log_activity('Delivery', delivery.id, user.id if user else 1, 'Delivery confirmed', action_note)
    db.session.commit()
    return delivery


def check_delivery_availability(delivery_id, user=None):
    """
    Re-checks stock availability for a Waiting delivery.
    Transitions Waiting -> Ready once stock is available.
    """
    check_permission('deliveries:check', user)
    delivery = Delivery.query.get_or_404(delivery_id)

    if delivery.status != 'Waiting':
        return delivery, False, []

    has_shortage, shortages = check_delivery_shortages(delivery)

    if not has_shortage:
        delivery.status = 'Ready'
        log_activity('Delivery', delivery.id, user.id if user else 1, 'Stock availability checked',
                     'Sufficient stock available now; marked Ready for picking')
        db.session.commit()
        return delivery, True, []
    else:
        log_activity('Delivery', delivery.id, user.id if user else 1, 'Stock check performed',
                     'Still awaiting inventory replenishment')
        db.session.commit()
        return delivery, False, shortages


def pick_delivery(delivery_id, user=None):
    """Staff or Manager picks items: Ready -> Picked."""
    check_permission('deliveries:pick', user)
    delivery = Delivery.query.get_or_404(delivery_id)

    if delivery.status != 'Ready':
        raise BusinessRuleError(f"Cannot pick delivery in '{delivery.status}' status. Only Ready orders can be picked.")

    delivery.status = 'Picked'
    delivery.picked_by = user.id if user else None
    log_activity('Delivery', delivery.id, user.id if user else 1, 'Delivery picked', 'Items picked from bins')
    db.session.commit()
    return delivery


def pack_delivery(delivery_id, user=None):
    """Staff or Manager packs items: Picked -> Packed."""
    check_permission('deliveries:pack', user)
    delivery = Delivery.query.get_or_404(delivery_id)

    if delivery.status != 'Picked':
        raise BusinessRuleError(f"Cannot pack delivery in '{delivery.status}' status. Only Picked orders can be packed.")

    delivery.status = 'Packed'
    delivery.packed_by = user.id if user else None
    log_activity('Delivery', delivery.id, user.id if user else 1, 'Delivery packed', 'Items packed and staged')
    db.session.commit()
    return delivery


def validate_delivery(delivery_id, user=None):
    """
    Manager validates dispatch: Packed -> Done.
    Re-checks on-hand stock: Never deliver more than is on hand, and never let stock go negative.
    Creates StockMovement per line (source -> customer).
    """
    check_permission('deliveries:validate', user)
    delivery = Delivery.query.get_or_404(delivery_id)

    if delivery.status != 'Packed':
        raise BusinessRuleError(f"Cannot validate dispatch in '{delivery.status}' status. Only Packed deliveries can be dispatched.")

    # Re-check on hand stock
    for item in delivery.items:
        on_hand = get_on_hand(item.product_id, delivery.source_location_id)
        if item.quantity > on_hand:
            shortage = item.quantity - on_hand
            raise BusinessRuleError(
                f"Insufficient stock for {item.product.name} (Requested: {item.quantity}, Available: {on_hand}, Short: {shortage}). Dispatch aborted."
            )

    delivery.status = 'Done'
    delivery.done_by = user.id if user else None
    delivery.done_at = datetime.utcnow()

    for item in delivery.items:
        movement = StockMovement(
            reference=delivery.reference,
            doc_type='Delivery',
            doc_id=delivery.id,
            operation='Delivery',
            product_id=item.product_id,
            from_location_id=delivery.source_location_id,
            to_location_id=None,
            counterparty=delivery.customer.name,
            quantity=item.quantity,
            user_id=user.id if user else 1,
            at=datetime.utcnow()
        )
        db.session.add(movement)
        record_stock_quant_and_move(
            product_id=item.product_id,
            quantity=item.quantity,
            source_location_id=delivery.source_location_id,
            destination_location_id=None,
            reference=delivery.reference,
            user_id=user.id if user else 1,
            operation_id=delivery.id
        )

    log_activity('Delivery', delivery.id, user.id if user else 1, 'Delivery dispatched',
                 f"Dispatched order to {delivery.customer.name} from {delivery.source_location.code}")
    db.session.commit()
    return delivery


def cancel_delivery(delivery_id, user=None):
    """Cancels a delivery order before Done."""
    check_permission('deliveries:cancel', user)
    delivery = Delivery.query.get_or_404(delivery_id)

    if delivery.status == 'Done':
        raise BusinessRuleError("Cannot cancel a completed delivery order.")

    delivery.status = 'Canceled'
    log_activity('Delivery', delivery.id, user.id if user else 1, 'Delivery canceled', 'Delivery canceled')
    db.session.commit()
    return delivery


# =========================================================================
# INTERNAL TRANSFERS
# Draft -> Waiting -> Ready -> Done
# =========================================================================

def create_transfer(source_location_id, destination_location_id, scheduled_date=None,
                    reason=None, priority='Normal', items=None, user=None):
    """
    Creates an internal transfer.
    Rule: Source and destination must be different!
    """
    check_permission('transfers:create', user)

    if not source_location_id or not destination_location_id:
        raise BusinessRuleError("Source and destination locations are required.")

    if int(source_location_id) == int(destination_location_id):
        raise BusinessRuleError("Source and destination locations must be different.")

    src_loc = Location.query.get(source_location_id)
    dest_loc = Location.query.get(destination_location_id)

    if not src_loc or not src_loc.active:
        raise BusinessRuleError("Source location is invalid or inactive.")
    if not dest_loc or not dest_loc.active:
        raise BusinessRuleError("Destination location is invalid or inactive.")

    if not items:
        raise BusinessRuleError("At least one product line is required.")

    ref = next_reference('INT')
    transfer = Transfer(
        reference=ref,
        source_location_id=src_loc.id,
        destination_location_id=dest_loc.id,
        scheduled_date=scheduled_date,
        reason=reason.strip() if reason else None,
        priority=priority or 'Normal',
        status='Ready',  # Can go directly to Ready or Draft
        created_by=user.id if user else 1,
        created_at=datetime.utcnow()
    )
    db.session.add(transfer)
    db.session.flush()

    for itm in items:
        prod_id = itm.get('product_id')
        qty = float(itm.get('quantity', 0))
        if qty <= 0:
            raise BusinessRuleError("Transfer line quantity must be greater than zero.")
        prod = Product.query.get(prod_id)
        if not prod or prod.archived:
            raise BusinessRuleError(f"Product ID {prod_id} is invalid or archived.")

        # Check stock at source location
        on_hand = get_on_hand(prod.id, src_loc.id)
        if qty > on_hand:
            raise BusinessRuleError(f"Cannot transfer {qty} of {prod.name}; only {on_hand} available at {src_loc.code}.")

        tr_item = TransferItem(
            transfer_id=transfer.id,
            product_id=prod.id,
            quantity=qty
        )
        db.session.add(tr_item)

    log_activity('Internal Transfer', transfer.id, user.id if user else 1, 'Transfer created',
                 f"Created {transfer.reference}: {src_loc.code} -> {dest_loc.code}")
    db.session.commit()
    return transfer


def complete_transfer(transfer_id, user=None):
    """
    Staff or Manager completes transfer: Ready -> Done.
    Creates StockMovement from source to destination. Total company stock remains unchanged!
    """
    check_permission('transfers:complete', user)
    transfer = Transfer.query.get_or_404(transfer_id)

    if transfer.status not in ('Ready', 'Waiting', 'Draft'):
        raise BusinessRuleError(f"Cannot complete transfer in '{transfer.status}' status.")

    # Validate stock at source location
    for item in transfer.items:
        on_hand = get_on_hand(item.product_id, transfer.source_location_id)
        if item.quantity > on_hand:
            raise BusinessRuleError(
                f"Insufficient stock at source for {item.product.name} (Requested: {item.quantity}, On hand: {on_hand})."
            )

    transfer.status = 'Done'
    transfer.done_by = user.id if user else None
    transfer.done_at = datetime.utcnow()

    for item in transfer.items:
        movement = StockMovement(
            reference=transfer.reference,
            doc_type='Internal Transfer',
            doc_id=transfer.id,
            operation='Internal Transfer',
            product_id=item.product_id,
            from_location_id=transfer.source_location_id,
            to_location_id=transfer.destination_location_id,
            counterparty=f"Internal Relocation: {transfer.source_location.code} -> {transfer.destination_location.code}",
            quantity=item.quantity,
            user_id=user.id if user else 1,
            at=datetime.utcnow()
        )
        db.session.add(movement)
        record_stock_quant_and_move(
            product_id=item.product_id,
            quantity=item.quantity,
            source_location_id=transfer.source_location_id,
            destination_location_id=transfer.destination_location_id,
            reference=transfer.reference,
            user_id=user.id if user else 1,
            operation_id=transfer.id
        )

    log_activity('Internal Transfer', transfer.id, user.id if user else 1, 'Transfer completed',
                 f"Transferred stock from {transfer.source_location.code} to {transfer.destination_location.code}")
    db.session.commit()
    return transfer


def cancel_transfer(transfer_id, user=None):
    """Cancels a transfer before Done."""
    check_permission('transfers:cancel', user)
    transfer = Transfer.query.get_or_404(transfer_id)

    if transfer.status == 'Done':
        raise BusinessRuleError("Cannot cancel a completed transfer.")

    transfer.status = 'Canceled'
    log_activity('Internal Transfer', transfer.id, user.id if user else 1, 'Transfer canceled', 'Transfer canceled')
    db.session.commit()
    return transfer


# =========================================================================
# INVENTORY ADJUSTMENTS
# Draft (count sheet) -> Counted ("Count Submitted") -> Approved, or Canceled/Rejected
# Blind count: staff enter counted quantities without seeing system quantity.
# Discrepancy requires a reason.
# Approving posts diff to StockMovement and updates stock.
# =========================================================================

def create_adjustment(title, location_id, assigned_to_id=None, items=None, notes=None, user=None):
    """
    Manager issues count sheet: Status 'Draft'.
    System quantity is recorded for audit, but not shown to staff during blind count.
    """
    check_permission('adjustments:create', user)

    title = (title or '').strip()
    if not title:
        raise BusinessRuleError("Adjustment sheet title is required.")

    loc = Location.query.get(location_id)
    if not loc or not loc.active:
        raise BusinessRuleError("Selected location is invalid or inactive.")

    if not items:
        raise BusinessRuleError("At least one product line is required.")

    ref = next_reference('ADJ')
    adj = Adjustment(
        reference=ref,
        title=title,
        status='Draft',
        assigned_to=assigned_to_id if assigned_to_id else None,
        notes=notes.strip() if notes else None,
        created_by=user.id if user else 1,
        created_at=datetime.utcnow()
    )
    db.session.add(adj)
    db.session.flush()

    for itm in items:
        prod_id = itm.get('product_id')
        prod = Product.query.get(prod_id)
        if not prod or prod.archived:
            raise BusinessRuleError(f"Product ID {prod_id} is invalid or archived.")

        system_qty = get_on_hand(prod.id, loc.id)
        adj_item = AdjustmentItem(
            adjustment_id=adj.id,
            product_id=prod.id,
            location_id=loc.id,
            system_quantity=system_qty,
            counted_quantity=None,
            applied_difference=0.0,
            reason=None
        )
        db.session.add(adj_item)

    log_activity('Adjustment', adj.id, user.id if user else 1, 'Count sheet issued',
                 f"Issued count sheet {adj.reference} for {loc.code}")
    db.session.commit()
    return adj


def submit_count(adjustment_id, count_data_map, user=None):
    """
    Staff or Manager submits physical count: Draft -> Counted ('Count Submitted').
    Rule: A reason (Damaged, Missing, Counting Error, Found Stock, Other) is REQUIRED
    for every line that has a discrepancy!
    Stock does NOT change upon submission.
    """
    check_permission('adjustments:count', user)
    adj = Adjustment.query.get_or_404(adjustment_id)

    if adj.status != 'Draft':
        raise BusinessRuleError(f"Cannot submit counts for adjustment in '{adj.status}' status. Only Draft count sheets can be submitted.")

    for item in adj.items:
        key = str(item.id)
        line_data = count_data_map.get(key, {})

        counted_raw = line_data.get('counted_quantity')
        if counted_raw is None or counted_raw == '':
            raise BusinessRuleError(f"Physical count quantity is required for {item.product.name}.")

        try:
            counted = float(counted_raw)
        except (ValueError, TypeError):
            raise BusinessRuleError(f"Count for {item.product.name} must be a valid number.")

        if counted < 0:
            raise BusinessRuleError(f"Count for {item.product.name} cannot be negative.")

        reason = (line_data.get('reason') or '').strip()
        diff = counted - item.system_quantity

        # If discrepancy exists, reason is mandatory
        if diff != 0 and not reason:
            raise BusinessRuleError(
                f"Discrepancy detected for {item.product.name} (Diff: {diff:+g} {item.product.uom}). A reason is mandatory."
            )

        item.counted_quantity = counted
        item.applied_difference = diff
        item.reason = reason if diff != 0 else (reason or 'Accurate Count')

    adj.status = 'Counted'
    adj.counted_by = user.id if user else None
    adj.counted_at = datetime.utcnow()

    log_activity('Adjustment', adj.id, user.id if user else 1, 'Physical count submitted',
                 'Physical counts entered and submitted for manager review')
    db.session.commit()
    return adj


def approve_adjustment(adjustment_id, user=None):
    """
    Manager approves adjustment: Counted -> Approved ('Adjustment Approved').
    On-hand stock becomes exactly the counted quantity.
    Recalculates the difference against CURRENT stock and posts it as a movement.
    """
    check_permission('adjustments:approve', user)
    adj = Adjustment.query.get_or_404(adjustment_id)

    if adj.status != 'Counted':
        raise BusinessRuleError(f"Cannot approve adjustment in '{adj.status}' status. Only submitted counts can be approved.")

    adj.status = 'Approved'
    adj.done_by = user.id if user else None
    adj.done_at = datetime.utcnow()

    for item in adj.items:
        current_on_hand = get_on_hand(item.product_id, item.location_id)
        target_qty = item.counted_quantity if item.counted_quantity is not None else item.system_quantity
        diff = target_qty - current_on_hand

        item.applied_difference = diff

        if diff > 0:
            # Positive adjustment (stock found / added)
            movement = StockMovement(
                reference=adj.reference,
                doc_type='Adjustment',
                doc_id=adj.id,
                operation='Adjustment',
                product_id=item.product_id,
                from_location_id=None,
                to_location_id=item.location_id,
                counterparty=item.reason or 'Inventory Adjustment',
                quantity=diff,
                user_id=user.id if user else 1,
                at=datetime.utcnow()
            )
            db.session.add(movement)
            record_stock_quant_and_move(
                product_id=item.product_id,
                quantity=diff,
                source_location_id=None,
                destination_location_id=item.location_id,
                reference=adj.reference,
                user_id=user.id if user else 1,
                operation_id=adj.id
            )
        elif diff < 0:
            # Negative adjustment (loss / shrinkage / missing)
            movement = StockMovement(
                reference=adj.reference,
                doc_type='Adjustment',
                doc_id=adj.id,
                operation='Adjustment',
                product_id=item.product_id,
                from_location_id=item.location_id,
                to_location_id=None,
                counterparty=item.reason or 'Inventory Adjustment',
                quantity=abs(diff),
                user_id=user.id if user else 1,
                at=datetime.utcnow()
            )
            db.session.add(movement)
            record_stock_quant_and_move(
                product_id=item.product_id,
                quantity=abs(diff),
                source_location_id=item.location_id,
                destination_location_id=None,
                reference=adj.reference,
                user_id=user.id if user else 1,
                operation_id=adj.id
            )

    log_activity('Adjustment', adj.id, user.id if user else 1, 'Adjustment approved',
                 'Stock balance reconciled to physical count')
    db.session.commit()
    return adj


def reject_adjustment(adjustment_id, user=None):
    """Manager rejects count."""
    check_permission('adjustments:reject', user)
    adj = Adjustment.query.get_or_404(adjustment_id)

    if adj.status != 'Counted':
        raise BusinessRuleError(f"Cannot reject adjustment in '{adj.status}' status.")

    adj.status = 'Rejected'
    log_activity('Adjustment', adj.id, user.id if user else 1, 'Count rejected', 'Manager rejected submitted count')
    db.session.commit()
    return adj


def cancel_adjustment(adjustment_id, user=None):
    """Cancels adjustment before Approved."""
    check_permission('adjustments:cancel', user)
    adj = Adjustment.query.get_or_404(adjustment_id)

    if adj.status == 'Approved':
        raise BusinessRuleError("Cannot cancel an approved adjustment.")

    adj.status = 'Canceled'
    log_activity('Adjustment', adj.id, user.id if user else 1, 'Adjustment canceled', 'Adjustment canceled')
    db.session.commit()
    return adj


# =========================================================================
# WAREHOUSES & LOCATIONS
# =========================================================================

def create_warehouse(name, code, address=None, user=None):
    check_permission('locations:manage', user)
    code = (code or '').strip().upper()
    name = (name or '').strip()

    if not name or not code:
        raise BusinessRuleError("Warehouse name and code are required.")

    existing = Warehouse.query.filter_by(code=code).first()
    if existing:
        raise BusinessRuleError(f"Warehouse with code '{code}' already exists.")

    wh = Warehouse(name=name, code=code, address=address.strip() if address else None, active=True)
    db.session.add(wh)
    db.session.commit()
    return wh


def create_location(warehouse_id, name, code, user=None):
    check_permission('locations:manage', user)
    code = (code or '').strip().upper()
    name = (name or '').strip()

    if not name or not code:
        raise BusinessRuleError("Location name and code are required.")

    wh = Warehouse.query.get(warehouse_id)
    if not wh:
        raise BusinessRuleError("Warehouse not found.")

    existing = Location.query.filter_by(code=code).first()
    if existing:
        raise BusinessRuleError(f"Location with code '{code}' already exists.")

    loc = Location(warehouse_id=wh.id, name=name, code=code, active=True)
    db.session.add(loc)
    db.session.commit()
    return loc


def toggle_location_active(location_id, user=None):
    """
    Toggles location active/inactive.
    Rule: Can't deactivate a location that still holds stock!
    """
    check_permission('locations:manage', user)
    loc = Location.query.get_or_404(location_id)

    if loc.active:
        # Check if there is any on-hand stock at this location
        products = Product.query.all()
        for p in products:
            on_hand = get_on_hand(p.id, loc.id)
            if on_hand > 0:
                raise BusinessRuleError(
                    f"Cannot deactivate location '{loc.code}'. It currently holds stock ({on_hand} {p.uom} of {p.name})."
                )
        loc.active = False
    else:
        loc.active = True

    db.session.commit()
    return loc
