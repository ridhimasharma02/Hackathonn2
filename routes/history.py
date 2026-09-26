import csv
import io
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, Response
from flask_login import login_required, current_user
from models import db, StockMovement, Product, Location, User
from services.permissions import require_permission, can

history_bp = Blueprint('history', __name__)

def build_history_query():
    now = datetime.utcnow()
    query = StockMovement.query

    # Staff is strictly restricted to the last 30 days
    if not current_user.is_manager:
        thirty_days_ago = now - timedelta(days=30)
        query = query.filter(StockMovement.at >= thirty_days_ago)

    search = request.args.get('q', '').strip()
    operation = request.args.get('operation', '').strip()
    product_id = request.args.get('product', '').strip()
    location_id = request.args.get('location', '').strip()
    user_id = request.args.get('user', '').strip()
    date_range = request.args.get('range', '').strip()
    from_date_str = request.args.get('from', '').strip()
    to_date_str = request.args.get('to', '').strip()
    only_mine = request.args.get('only_mine')

    if search:
        query = query.join(Product, StockMovement.product_id == Product.id).filter(
            db.or_(
                StockMovement.reference.ilike(f"%{search}%"),
                StockMovement.counterparty.ilike(f"%{search}%"),
                Product.name.ilike(f"%{search}%"),
                Product.sku.ilike(f"%{search}%")
            )
        )

    if operation:
        query = query.filter(StockMovement.operation.ilike(f"%{operation}%"))

    if product_id and product_id.isdigit():
        query = query.filter(StockMovement.product_id == int(product_id))

    if location_id and location_id.isdigit():
        loc_id = int(location_id)
        query = query.filter(
            db.or_(
                StockMovement.from_location_id == loc_id,
                StockMovement.to_location_id == loc_id
            )
        )

    if user_id and user_id.isdigit():
        query = query.filter(StockMovement.user_id == int(user_id))

    if only_mine:
        query = query.filter(StockMovement.user_id == current_user.id)

    if date_range == 'today':
        start_today = datetime(now.year, now.month, now.day)
        query = query.filter(StockMovement.at >= start_today)
    elif date_range == '7d':
        query = query.filter(StockMovement.at >= (now - timedelta(days=7)))
    elif date_range == '30d':
        query = query.filter(StockMovement.at >= (now - timedelta(days=30)))
    elif from_date_str or to_date_str:
        if from_date_str:
            try:
                fd = datetime.strptime(from_date_str, '%Y-%m-%d')
                query = query.filter(StockMovement.at >= fd)
            except ValueError:
                pass
        if to_date_str:
            try:
                td = datetime.strptime(to_date_str, '%Y-%m-%d') + timedelta(days=1)
                query = query.filter(StockMovement.at < td)
            except ValueError:
                pass

    return query


@history_bp.route('/move-history', methods=['GET'])
@login_required
def index():
    query = build_history_query()
    page = request.args.get('page', 1, type=int)
    per_page = 25

    pagination = query.order_by(StockMovement.at.desc()).paginate(page=page, per_page=per_page, error_out=False)

    # Compute summary metrics for today
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_moves = StockMovement.query.filter(StockMovement.at >= today_start).all()

    moves_today_count = len(today_moves)
    inward_units = sum(m.quantity for m in today_moves if m.operation == 'Receipt')
    outward_units = sum(m.quantity for m in today_moves if m.operation == 'Delivery')
    internal_transfers = sum(1 for m in today_moves if m.operation == 'Internal Transfer')
    discrepancies = sum(1 for m in today_moves if m.operation == 'Adjustment')

    products = Product.query.order_by(Product.name).all()
    locations = Location.query.filter_by(active=True).order_by(Location.code).all()
    operators = User.query.filter_by(active=True).order_by(User.name).all()

    return render_template(
        'history/list.html',
        movements=pagination.items,
        pagination=pagination,
        moves_today_count=moves_today_count,
        inward_units=inward_units,
        outward_units=outward_units,
        internal_transfers=internal_transfers,
        discrepancies=discrepancies,
        products=products,
        locations=locations,
        operators=operators,
        selected_q=request.args.get('q', ''),
        selected_op=request.args.get('operation', ''),
        selected_product=request.args.get('product', ''),
        selected_location=request.args.get('location', ''),
        selected_user=request.args.get('user', ''),
        selected_range=request.args.get('range', ''),
        selected_from=request.args.get('from', ''),
        selected_to=request.args.get('to', ''),
        only_mine=bool(request.args.get('only_mine'))
    )


@history_bp.route('/history/export.csv', methods=['GET'])
@login_required
@require_permission('history:export')
def export_csv():
    query = build_history_query()
    movements = query.order_by(StockMovement.at.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        'Date & Time',
        'Reference',
        'Document Type',
        'Product',
        'SKU',
        'Operation',
        'Source Location',
        'Target Location',
        'Quantity',
        'UOM',
        'Counterparty',
        'Operator'
    ])

    for m in movements:
        writer.writerow([
            m.at.strftime('%Y-%m-%d %H:%M:%S'),
            m.reference,
            m.doc_type,
            m.product.name if m.product else 'N/A',
            m.product.sku if m.product else 'N/A',
            m.operation,
            m.from_location.code if m.from_location else 'External',
            m.to_location.code if m.to_location else 'External',
            m.quantity,
            m.product.uom if m.product else 'unit',
            m.counterparty or '',
            m.user.name if m.user else 'System'
        ])

    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={
            'Content-Disposition': f'attachment; filename=stocksense_stock_ledger_{datetime.utcnow().strftime("%Y%m%d")}.csv'
        }
    )
