from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for
from flask_login import login_required, current_user
from models import db, Product, Category, Warehouse, Location, Receipt, Delivery, Transfer, Adjustment, StockMovement, ActivityLog
from services.stock_engine import get_on_hand, get_available, get_status

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/')
@login_required
def index():
    if current_user.is_manager:
        return manager_dashboard()
    else:
        return staff_dashboard()


def manager_dashboard():
    products = Product.query.filter_by(archived=False).all()

    in_stock_count = 0
    low_stock_count = 0
    out_of_stock_count = 0
    low_stock_items = []

    for p in products:
        oh = get_on_hand(p.id)
        st = get_status(p, oh)
        if st == 'In Stock':
            in_stock_count += 1
        elif st == 'Low Stock':
            low_stock_count += 1
            low_stock_items.append({'product': p, 'on_hand': oh, 'status': st})
        else:
            out_of_stock_count += 1
            low_stock_items.append({'product': p, 'on_hand': oh, 'status': st})

    pending_receipts_count = Receipt.query.filter(Receipt.status.in_(['Draft', 'Waiting', 'Ready'])).count()
    pending_deliveries_count = Delivery.query.filter(Delivery.status.in_(['Draft', 'Waiting', 'Ready', 'Picked', 'Packed'])).count()
    pending_transfers_count = Transfer.query.filter(Transfer.status.in_(['Draft', 'Waiting', 'Ready'])).count()

    # Items awaiting manager validation
    awaiting_receipts = Receipt.query.filter_by(status='Ready').order_by(Receipt.created_at.desc()).all()
    awaiting_deliveries = Delivery.query.filter_by(status='Packed').order_by(Delivery.created_at.desc()).all()
    awaiting_adjustments = Adjustment.query.filter_by(status='Counted').order_by(Adjustment.created_at.desc()).all()

    # Operations queue filters
    filter_type = request.args.get('type', 'all')
    filter_status = request.args.get('status', 'all')
    filter_location = request.args.get('location', 'all')

    operations = []

    if filter_type in ('all', 'receipt'):
        rq = Receipt.query.filter(Receipt.status.in_(['Draft', 'Waiting', 'Ready']))
        if filter_status != 'all':
            rq = rq.filter(Receipt.status == filter_status)
        if filter_location != 'all':
            rq = rq.filter(Receipt.destination_location_id == filter_location)
        for r in rq.limit(10).all():
            total_qty = sum(i.quantity for i in r.items)
            operations.append({
                'id': r.id,
                'reference': r.reference,
                'doc_type': 'Receipt',
                'partner': r.supplier.name if r.supplier else 'N/A',
                'items_count': len(r.items),
                'total_qty': total_qty,
                'flow': f"Vendor → {r.destination_location.code if r.destination_location else 'N/A'}",
                'scheduled': r.scheduled_date,
                'status': r.status,
                'url': url_for('receipts.detail', id=r.id)
            })

    if filter_type in ('all', 'delivery'):
        dq = Delivery.query.filter(Delivery.status.in_(['Draft', 'Waiting', 'Ready', 'Picked', 'Packed']))
        if filter_status != 'all':
            dq = dq.filter(Delivery.status == filter_status)
        if filter_location != 'all':
            dq = dq.filter(Delivery.source_location_id == filter_location)
        for d in dq.limit(10).all():
            total_qty = sum(i.quantity for i in d.items)
            operations.append({
                'id': d.id,
                'reference': d.reference,
                'doc_type': 'Delivery',
                'partner': d.customer.name if d.customer else 'N/A',
                'items_count': len(d.items),
                'total_qty': total_qty,
                'flow': f"{d.source_location.code if d.source_location else 'N/A'} → Customer",
                'scheduled': d.scheduled_date,
                'status': d.status,
                'priority': d.priority,
                'url': url_for('deliveries.detail', id=d.id)
            })

    if filter_type in ('all', 'transfer'):
        tq = Transfer.query.filter(Transfer.status.in_(['Draft', 'Waiting', 'Ready']))
        if filter_status != 'all':
            tq = tq.filter(Transfer.status == filter_status)
        if filter_location != 'all':
            tq = tq.filter(db.or_(Transfer.source_location_id == filter_location, Transfer.destination_location_id == filter_location))
        for t in tq.limit(10).all():
            total_qty = sum(i.quantity for i in t.items)
            operations.append({
                'id': t.id,
                'reference': t.reference,
                'doc_type': 'Internal Transfer',
                'partner': 'Internal Floor',
                'items_count': len(t.items),
                'total_qty': total_qty,
                'flow': f"{t.source_location.code} → {t.destination_location.code}",
                'scheduled': t.scheduled_date,
                'status': t.status,
                'priority': t.priority,
                'url': url_for('transfers.detail', id=t.id)
            })

    # Sort operations by scheduled date or reference
    operations.sort(key=lambda x: str(x.get('scheduled') or '9999'))

    # Location activity & stock-by-location matrix
    locations = Location.query.filter_by(active=True).all()
    location_matrix = []
    for loc in locations:
        loc_oh = 0.0
        for p in products:
            loc_oh += get_on_hand(p.id, loc.id)
        location_matrix.append({'location': loc, 'total_stock': loc_oh})

    recent_movements = StockMovement.query.order_by(StockMovement.at.desc()).limit(8).all()

    return render_template(
        'dashboard/manager.html',
        in_stock_count=in_stock_count,
        low_stock_count=low_stock_count,
        out_of_stock_count=out_of_stock_count,
        pending_receipts_count=pending_receipts_count,
        pending_deliveries_count=pending_deliveries_count,
        pending_transfers_count=pending_transfers_count,
        awaiting_receipts=awaiting_receipts,
        awaiting_deliveries=awaiting_deliveries,
        awaiting_adjustments=awaiting_adjustments,
        low_stock_items=low_stock_items[:5],
        operations=operations,
        location_matrix=location_matrix,
        recent_movements=recent_movements,
        filter_type=filter_type,
        filter_status=filter_status,
        filter_location=filter_location
    )


def staff_dashboard():
    # 5 task queues
    receipts_waiting = Receipt.query.filter_by(status='Waiting').all()
    deliveries_ready = Delivery.query.filter_by(status='Ready').all()
    deliveries_picked = Delivery.query.filter_by(status='Picked').all()
    transfers_ready = Transfer.query.filter_by(status='Ready').all()
    adjustments_draft = Adjustment.query.filter_by(status='Draft').all()

    # Aggregated "My Pending Tasks" table:
    # Sorted: urgent -> overdue -> due date
    tasks = []
    now = datetime.utcnow()

    for r in receipts_waiting:
        is_overdue = bool(r.scheduled_date and r.scheduled_date < now)
        tasks.append({
            'reference': r.reference,
            'type': 'Receive',
            'doc_type': 'Receipt',
            'partner': r.supplier.name,
            'items_desc': f"{len(r.items)} line(s)",
            'location': r.destination_location.code,
            'due_date': r.scheduled_date,
            'is_urgent': False,
            'is_overdue': is_overdue,
            'action_label': 'Record Intake',
            'url': url_for('receipts.detail', id=r.id)
        })

    for d in deliveries_ready:
        is_urgent = (d.priority == 'Urgent')
        is_overdue = bool(d.scheduled_date and d.scheduled_date < now)
        tasks.append({
            'reference': d.reference,
            'type': 'Pick',
            'doc_type': 'Delivery',
            'partner': d.customer.name,
            'items_desc': f"{len(d.items)} line(s)",
            'location': d.source_location.code,
            'due_date': d.scheduled_date,
            'is_urgent': is_urgent,
            'is_overdue': is_overdue,
            'action_label': 'Pick Items',
            'url': url_for('deliveries.detail', id=d.id)
        })

    for d in deliveries_picked:
        is_urgent = (d.priority == 'Urgent')
        is_overdue = bool(d.scheduled_date and d.scheduled_date < now)
        tasks.append({
            'reference': d.reference,
            'type': 'Pack',
            'doc_type': 'Delivery',
            'partner': d.customer.name,
            'items_desc': f"{len(d.items)} line(s)",
            'location': d.source_location.code,
            'due_date': d.scheduled_date,
            'is_urgent': is_urgent,
            'is_overdue': is_overdue,
            'action_label': 'Pack Order',
            'url': url_for('deliveries.detail', id=d.id)
        })

    for t in transfers_ready:
        is_urgent = (t.priority == 'Urgent')
        is_overdue = bool(t.scheduled_date and t.scheduled_date < now)
        tasks.append({
            'reference': t.reference,
            'type': 'Move',
            'doc_type': 'Internal Transfer',
            'partner': 'Internal Transit',
            'items_desc': f"{len(t.items)} line(s)",
            'location': f"{t.source_location.code} → {t.destination_location.code}",
            'due_date': t.scheduled_date,
            'is_urgent': is_urgent,
            'is_overdue': is_overdue,
            'action_label': 'Complete Relocation',
            'url': url_for('transfers.detail', id=t.id)
        })

    for a in adjustments_draft:
        tasks.append({
            'reference': a.reference,
            'type': 'Count',
            'doc_type': 'Adjustment',
            'partner': a.title,
            'items_desc': f"{len(a.items)} line(s)",
            'location': a.items[0].location.code if a.items else 'MAIN/STOCK',
            'due_date': a.created_at,
            'is_urgent': False,
            'is_overdue': False,
            'action_label': 'Enter Counts',
            'url': url_for('adjustments.detail', id=a.id)
        })

    # Sort tasks: urgent (True first) -> overdue (True first) -> due date
    tasks.sort(key=lambda x: (not x['is_urgent'], not x['is_overdue'], str(x['due_date'] or '9999')))

    # Handed-over items awaiting manager validation
    handed_over = []
    ready_recs = Receipt.query.filter_by(status='Ready').all()
    packed_dels = Delivery.query.filter_by(status='Packed').all()
    counted_adjs = Adjustment.query.filter_by(status='Counted').all()

    for r in ready_recs:
        handed_over.append({
            'reference': r.reference,
            'desc': f"Received goods awaiting manager validation ({r.supplier.name})",
            'url': url_for('receipts.detail', id=r.id)
        })
    for d in packed_dels:
        handed_over.append({
            'reference': d.reference,
            'desc': f"Packed order awaiting manager dispatch signoff ({d.customer.name})",
            'url': url_for('deliveries.detail', id=d.id)
        })
    for a in counted_adjs:
        handed_over.append({
            'reference': a.reference,
            'desc': f"Physical count submitted awaiting manager approval ({a.title})",
            'url': url_for('adjustments.detail', id=a.id)
        })

    # Recent movements (Staff sees last 30 days)
    thirty_days_ago = now - timedelta(days=30)
    recent_movements = StockMovement.query.filter(
        StockMovement.at >= thirty_days_ago
    ).order_by(StockMovement.at.desc()).limit(8).all()

    return render_template(
        'dashboard/staff.html',
        receipts_count=len(receipts_waiting),
        pick_count=len(deliveries_ready),
        pack_count=len(deliveries_picked),
        transfers_count=len(transfers_ready),
        counting_count=len(adjustments_draft),
        tasks=tasks,
        handed_over=handed_over,
        recent_movements=recent_movements
    )
