from sqlalchemy import func
from models import (
    db, StockMovement, Delivery, DeliveryItem, Transfer, TransferItem,
    Location, Product, StockQuant, StockMove
)

def get_on_hand(product_id, location_id=None):
    """
    Computes on-hand stock strictly from StockMovement records.
    Stock is NEVER stored directly on the Product model.
    """
    if location_id is not None:
        inflow = db.session.query(
            func.coalesce(func.sum(StockMovement.quantity), 0.0)
        ).filter(
            StockMovement.product_id == product_id,
            StockMovement.to_location_id == location_id
        ).scalar()

        outflow = db.session.query(
            func.coalesce(func.sum(StockMovement.quantity), 0.0)
        ).filter(
            StockMovement.product_id == product_id,
            StockMovement.from_location_id == location_id
        ).scalar()

        return float(inflow - outflow)
    else:
        # Total company stock across all locations
        inflow = db.session.query(
            func.coalesce(func.sum(StockMovement.quantity), 0.0)
        ).filter(
            StockMovement.product_id == product_id,
            StockMovement.from_location_id.is_(None)
        ).scalar()

        outflow = db.session.query(
            func.coalesce(func.sum(StockMovement.quantity), 0.0)
        ).filter(
            StockMovement.product_id == product_id,
            StockMovement.to_location_id.is_(None)
        ).scalar()

        return float(inflow - outflow)


def get_reserved(product_id, location_id=None):
    """
    Reserved stock = quantities on Deliveries that are Ready/Picked/Packed
    plus Transfers that are Ready, at the source location.
    """
    delivery_query = db.session.query(
        func.coalesce(func.sum(DeliveryItem.quantity), 0.0)
    ).join(
        Delivery, Delivery.id == DeliveryItem.delivery_id
    ).filter(
        DeliveryItem.product_id == product_id,
        Delivery.status.in_(['Ready', 'Picked', 'Packed'])
    )
    if location_id is not None:
        delivery_query = delivery_query.filter(Delivery.source_location_id == location_id)

    delivery_reserved = delivery_query.scalar() or 0.0

    transfer_query = db.session.query(
        func.coalesce(func.sum(TransferItem.quantity), 0.0)
    ).join(
        Transfer, Transfer.id == TransferItem.transfer_id
    ).filter(
        TransferItem.product_id == product_id,
        Transfer.status == 'Ready'
    )
    if location_id is not None:
        transfer_query = transfer_query.filter(Transfer.source_location_id == location_id)

    transfer_reserved = transfer_query.scalar() or 0.0

    return float(delivery_reserved + transfer_reserved)


def get_available(product_id, location_id=None):
    """
    Available stock = on_hand - reserved.
    """
    on_hand = get_on_hand(product_id, location_id)
    reserved = get_reserved(product_id, location_id)
    return max(0.0, on_hand - reserved)


def get_status(product, on_hand_qty=None):
    """
    Returns inventory status label:
    0 -> 'Out of Stock'
    <= reorder_level -> 'Low Stock'
    otherwise -> 'In Stock'
    """
    if on_hand_qty is None:
        on_hand_qty = get_on_hand(product.id)

    if on_hand_qty <= 0:
        return 'Out of Stock'
    elif on_hand_qty <= product.reorder_level:
        return 'Low Stock'
    else:
        return 'In Stock'


def get_product_stock_matrix(product_id):
    """
    Returns per-location stock levels and overall total for a product.
    """
    locations = Location.query.filter_by(active=True).order_by(Location.code).all()
    matrix = []
    tot_on_hand = 0.0
    tot_reserved = 0.0
    tot_available = 0.0

    for loc in locations:
        oh = get_on_hand(product_id, loc.id)
        res = get_reserved(product_id, loc.id)
        avail = max(0.0, oh - res)
        tot_on_hand += oh
        tot_reserved += res
        tot_available += avail

        matrix.append({
            'location': loc,
            'on_hand': oh,
            'reserved': res,
            'available': avail
        })

    return {
        'locations': matrix,
        'total_on_hand': tot_on_hand,
        'total_reserved': tot_reserved,
        'total_available': tot_available
    }


def check_delivery_shortages(delivery):
    """
    Evaluates whether all line items on a delivery have sufficient available stock.
    Returns (has_shortages: bool, shortages_list: list).
    """
    shortages = []
    for item in delivery.items:
        avail = get_available(item.product_id, delivery.source_location_id)
        if item.quantity > avail:
            shortages.append({
                'product': item.product,
                'requested': item.quantity,
                'available': avail,
                'shortage': item.quantity - avail
            })
    return (len(shortages) > 0, shortages)


def get_quant(product_id: int, location_id: int) -> float:
    """
    Returns quantity from stock_quants snapshot table.
    """
    quant = StockQuant.query.filter_by(product_id=product_id, location_id=location_id).first()
    return float(quant.quantity) if quant else 0.0


def record_stock_quant_and_move(
    product_id: int,
    quantity: float,
    source_location_id: int = None,
    destination_location_id: int = None,
    reference: str = None,
    user_id: int = None,
    operation_id: int = None
):
    """
    Records an immutable double-entry StockMove and updates StockQuant for source and destination locations.
    """
    move = StockMove(
        operation_id=operation_id,
        reference=reference,
        product_id=product_id,
        quantity=quantity,
        source_location_id=source_location_id,
        destination_location_id=destination_location_id,
        user_id=user_id
    )
    db.session.add(move)

    if source_location_id is not None:
        source_quant = StockQuant.query.filter_by(product_id=product_id, location_id=source_location_id).first()
        if not source_quant:
            source_quant = StockQuant(product_id=product_id, location_id=source_location_id, quantity=0.0)
            db.session.add(source_quant)
        source_quant.quantity = round(source_quant.quantity - quantity, 4)

    if destination_location_id is not None:
        dest_quant = StockQuant.query.filter_by(product_id=product_id, location_id=destination_location_id).first()
        if not dest_quant:
            dest_quant = StockQuant(product_id=product_id, location_id=destination_location_id, quantity=0.0)
            db.session.add(dest_quant)
        dest_quant.quantity = round(dest_quant.quantity + quantity, 4)

    return move


def sync_all_quants():
    """
    Recalculates and synchronizes all StockQuant rows from actual on-hand stock.
    """
    products = Product.query.all()
    locations = Location.query.filter_by(active=True).all()
    for p in products:
        for loc in locations:
            qty = get_on_hand(p.id, loc.id)
            quant = StockQuant.query.filter_by(product_id=p.id, location_id=loc.id).first()
            if not quant:
                quant = StockQuant(product_id=p.id, location_id=loc.id, quantity=qty)
                db.session.add(quant)
            else:
                quant.quantity = qty
    db.session.commit()

