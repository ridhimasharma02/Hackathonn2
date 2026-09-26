from datetime import datetime
from flask import Blueprint, request, jsonify, url_for
from flask_login import login_required, current_user
from models import db, Product, Location, Receipt, Delivery, Transfer, Adjustment
from services.stock_engine import get_on_hand, get_available, get_reserved, get_status

api_bp = Blueprint('api', __name__)

@api_bp.route('/api/stock')
@login_required
def get_stock_info():
    product_id = request.args.get('product', type=int)
    location_id = request.args.get('location', type=int)

    if not product_id:
        return jsonify({'error': 'Product ID is required'}), 400

    product = Product.query.get(product_id)
    if not product:
        return jsonify({'error': 'Product not found'}), 404

    on_hand = get_on_hand(product_id, location_id)
    reserved = get_reserved(product_id, location_id)
    available = max(0.0, on_hand - reserved)
    status = get_status(product, on_hand)

    return jsonify({
        'product_id': product.id,
        'product_name': product.name,
        'sku': product.sku,
        'uom': product.uom,
        'location_id': location_id,
        'on_hand': on_hand,
        'reserved': reserved,
        'available': available,
        'status': status
    })


@api_bp.route('/search')
@login_required
def global_search():
    q = request.args.get('q', '').strip()
    if not q or len(q) < 2:
        return jsonify({'results': []})

    results = []

    # 1. Products
    products = Product.query.filter(
        db.or_(
            Product.name.ilike(f"%{q}%"),
            Product.sku.ilike(f"%{q}%")
        )
    ).limit(5).all()
    for p in products:
        results.append({
            'category': 'Product',
            'title': f"{p.name} ({p.sku})",
            'subtitle': f"Reorder: {p.reorder_level} {p.uom} · Total On-Hand: {get_on_hand(p.id)} {p.uom}",
            'url': url_for('products.detail', id=p.id)
        })

    # 2. Receipts (REC, PO)
    receipts = Receipt.query.filter(
        db.or_(
            Receipt.reference.ilike(f"%{q}%"),
            Receipt.source_document.ilike(f"%{q}%")
        )
    ).limit(4).all()
    for r in receipts:
        results.append({
            'category': 'Receipt',
            'title': r.reference,
            'subtitle': f"{r.supplier.name} · {r.status} · PO: {r.source_document or 'N/A'}",
            'url': url_for('receipts.detail', id=r.id)
        })

    # 3. Deliveries (DO, SO)
    deliveries = Delivery.query.filter(
        db.or_(
            Delivery.reference.ilike(f"%{q}%"),
            Delivery.source_document.ilike(f"%{q}%")
        )
    ).limit(4).all()
    for d in deliveries:
        results.append({
            'category': 'Delivery Order',
            'title': d.reference,
            'subtitle': f"{d.customer.name} · {d.status} ({d.priority})",
            'url': url_for('deliveries.detail', id=d.id)
        })

    # 4. Transfers (INT)
    transfers = Transfer.query.filter(Transfer.reference.ilike(f"%{q}%")).limit(3).all()
    for t in transfers:
        results.append({
            'category': 'Internal Transfer',
            'title': t.reference,
            'subtitle': f"{t.source_location.code} → {t.destination_location.code} ({t.status})",
            'url': url_for('transfers.detail', id=t.id)
        })

    # 5. Adjustments (ADJ)
    adjustments = Adjustment.query.filter(
        db.or_(
            Adjustment.reference.ilike(f"%{q}%"),
            Adjustment.title.ilike(f"%{q}%")
        )
    ).limit(3).all()
    for a in adjustments:
        results.append({
            'category': 'Inventory Adjustment',
            'title': f"{a.reference} - {a.title}",
            'subtitle': f"Status: {a.status}",
            'url': url_for('adjustments.detail', id=a.id)
        })

    return jsonify({'results': results})


@api_bp.route('/notifications')
@login_required
def notifications():
    items = []

    if current_user.is_manager:
        # Awaiting validation
        ready_recs = Receipt.query.filter_by(status='Ready').all()
        for r in ready_recs:
            items.append({
                'title': f"Receipt {r.reference} Awaiting Validation",
                'desc': f"Received from {r.supplier.name}",
                'url': url_for('receipts.detail', id=r.id),
                'type': 'warning'
            })

        packed_dels = Delivery.query.filter_by(status='Packed').all()
        for d in packed_dels:
            items.append({
                'title': f"Delivery {d.reference} Ready for Dispatch Signoff",
                'desc': f"Packed for {d.customer.name}",
                'url': url_for('deliveries.detail', id=d.id),
                'type': 'info'
            })

        counted_adjs = Adjustment.query.filter_by(status='Counted').all()
        for a in counted_adjs:
            items.append({
                'title': f"Adjustment {a.reference} Discrepancy Approval",
                'desc': a.title,
                'url': url_for('adjustments.detail', id=a.id),
                'type': 'error'
            })

        # Out of stock alerts
        products = Product.query.filter_by(archived=False).all()
        for p in products:
            if get_on_hand(p.id) == 0:
                items.append({
                    'title': f"Out of Stock: {p.name} ({p.sku})",
                    'desc': "Immediate reorder required",
                    'url': url_for('products.detail', id=p.id),
                    'type': 'error'
                })
    else:
        # Staff notifications: urgent & due today tasks
        now = datetime.utcnow()
        urgent_dels = Delivery.query.filter(
            Delivery.status.in_(['Ready', 'Picked']),
            Delivery.priority == 'Urgent'
        ).all()
        for d in urgent_dels:
            items.append({
                'title': f"Urgent Order: {d.reference}",
                'desc': f"Customer: {d.customer.name} ({d.status})",
                'url': url_for('deliveries.detail', id=d.id),
                'type': 'error'
            })

        waiting_recs = Receipt.query.filter_by(status='Waiting').all()
        for r in waiting_recs:
            items.append({
                'title': f"Intake Pending: {r.reference}",
                'desc': f"Supplier: {r.supplier.name}",
                'url': url_for('receipts.detail', id=r.id),
                'type': 'info'
            })

        ready_transfers = Transfer.query.filter_by(status='Ready').all()
        for t in ready_transfers:
            items.append({
                'title': f"Relocation Ready: {t.reference}",
                'desc': f"{t.source_location.code} → {t.destination_location.code}",
                'url': url_for('transfers.detail', id=t.id),
                'type': 'warning'
            })

    return jsonify({
        'count': len(items),
        'notifications': items[:10]
    })
