from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, Delivery, DeliveryItem, Customer, Location, Product, ActivityLog
from services import inventory_service as inv
from services.inventory_service import BusinessRuleError
from services.permissions import require_permission, can
from services.stock_engine import get_on_hand, get_available, check_delivery_shortages

deliveries_bp = Blueprint('deliveries', __name__)

@deliveries_bp.route('/', methods=['GET'])
@login_required
def index():
    tab = request.args.get('tab', 'all')
    search = request.args.get('search', '').strip()
    customer_id = request.args.get('customer', '').strip()
    priority = request.args.get('priority', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 25

    query = Delivery.query

    if tab != 'all':
        query = query.filter(Delivery.status == tab.capitalize())

    if search:
        query = query.filter(
            db.or_(
                Delivery.reference.ilike(f"%{search}%"),
                Delivery.source_document.ilike(f"%{search}%")
            )
        )

    if customer_id and customer_id.isdigit():
        query = query.filter(Delivery.customer_id == int(customer_id))

    if priority:
        query = query.filter(Delivery.priority == priority)

    pagination = query.order_by(Delivery.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    customers = Customer.query.order_by(Customer.name).all()

    tab_counts = {
        'all': Delivery.query.count(),
        'draft': Delivery.query.filter_by(status='Draft').count(),
        'waiting': Delivery.query.filter_by(status='Waiting').count(),
        'ready': Delivery.query.filter_by(status='Ready').count(),
        'picked': Delivery.query.filter_by(status='Picked').count(),
        'packed': Delivery.query.filter_by(status='Packed').count(),
        'done': Delivery.query.filter_by(status='Done').count(),
        'canceled': Delivery.query.filter_by(status='Canceled').count()
    }

    return render_template(
        'deliveries/list.html',
        deliveries=pagination.items,
        pagination=pagination,
        tab=tab,
        tab_counts=tab_counts,
        search=search,
        selected_customer=customer_id,
        selected_priority=priority,
        customers=customers
    )


@deliveries_bp.route('/new', methods=['GET', 'POST'])
@login_required
@require_permission('deliveries:create')
def create():
    if request.method == 'POST':
        customer_id = request.form.get('customer_id')
        source_location_id = request.form.get('source_location_id')
        scheduled_date_str = request.form.get('scheduled_date')
        priority = request.form.get('priority', 'Normal')
        source_document = request.form.get('source_document')
        notes = request.form.get('notes')

        scheduled_date = None
        if scheduled_date_str:
            try:
                scheduled_date = datetime.strptime(scheduled_date_str, '%Y-%m-%d')
            except ValueError:
                pass

        product_ids = request.form.getlist('product_id[]')
        quantities = request.form.getlist('quantity[]')

        items = []
        for pid, qty in zip(product_ids, quantities):
            if pid and qty:
                try:
                    items.append({'product_id': int(pid), 'quantity': float(qty)})
                except (ValueError, TypeError):
                    pass

        try:
            delivery = inv.create_delivery(
                customer_id=customer_id,
                source_location_id=source_location_id,
                scheduled_date=scheduled_date,
                priority=priority,
                source_document=source_document,
                notes=notes,
                items=items,
                user=current_user
            )
            flash(f"Delivery Order '{delivery.reference}' created in Draft state.", "success")
            return redirect(url_for('deliveries.detail', id=delivery.id))
        except BusinessRuleError as e:
            flash(str(e), "error")

    customers = Customer.query.order_by(Customer.name).all()
    locations = Location.query.filter_by(active=True).order_by(Location.code).all()
    products = Product.query.filter_by(archived=False).order_by(Product.name).all()

    return render_template(
        'deliveries/form.html',
        customers=customers,
        locations=locations,
        products=products
    )


@deliveries_bp.route('/<int:id>', methods=['GET'])
@login_required
def detail(id):
    delivery = Delivery.query.get_or_404(id)
    has_shortage, shortages = check_delivery_shortages(delivery)
    logs = ActivityLog.query.filter_by(doc_type='Delivery', doc_id=delivery.id).order_by(ActivityLog.at.desc()).all()

    # Build line stock information
    items_info = []
    for item in delivery.items:
        on_hand = get_on_hand(item.product_id, delivery.source_location_id)
        avail = get_available(item.product_id, delivery.source_location_id)
        is_item_short = (item.quantity > avail) if delivery.status in ('Draft', 'Waiting') else (item.quantity > on_hand)
        items_info.append({
            'item': item,
            'on_hand': on_hand,
            'available': avail,
            'is_short': is_item_short
        })

    return render_template(
        'deliveries/detail.html',
        delivery=delivery,
        has_shortage=has_shortage,
        shortages=shortages,
        items_info=items_info,
        logs=logs
    )


@deliveries_bp.route('/<int:id>/confirm', methods=['POST'])
@login_required
@require_permission('deliveries:confirm')
def confirm(id):
    try:
        delivery = inv.confirm_delivery(id, user=current_user)
        if delivery.status == 'Ready':
            flash("Delivery confirmed: stock is available. Order marked Ready for picking.", "success")
        else:
            flash("Delivery confirmed: insufficient stock detected. Order set to Waiting.", "warning")
    except BusinessRuleError as e:
        flash(str(e), "error")
    return redirect(url_for('deliveries.detail', id=id))


@deliveries_bp.route('/<int:id>/check-availability', methods=['POST'])
@login_required
@require_permission('deliveries:check')
def check_availability(id):
    try:
        delivery, is_ready, shortages = inv.check_delivery_availability(id, user=current_user)
        if is_ready:
            flash("Stock replenished! Order is now Ready for picking.", "success")
        else:
            shortage_txt = ", ".join([f"{s['product'].name} short by {s['shortage']}" for s in shortages])
            flash(f"Stock still short: {shortage_txt}", "warning")
    except BusinessRuleError as e:
        flash(str(e), "error")
    return redirect(url_for('deliveries.detail', id=id))


@deliveries_bp.route('/<int:id>/pick', methods=['POST'])
@login_required
@require_permission('deliveries:pick')
def pick(id):
    try:
        inv.pick_delivery(id, user=current_user)
        flash("Items picked from warehouse racks. Order marked Picked.", "success")
    except BusinessRuleError as e:
        flash(str(e), "error")
    return redirect(url_for('deliveries.detail', id=id))


@deliveries_bp.route('/<int:id>/pack', methods=['POST'])
@login_required
@require_permission('deliveries:pack')
def pack(id):
    try:
        inv.pack_delivery(id, user=current_user)
        flash("Items packed and staged. Order marked Packed for manager validation.", "success")
    except BusinessRuleError as e:
        flash(str(e), "error")
    return redirect(url_for('deliveries.detail', id=id))


@deliveries_bp.route('/<int:id>/validate', methods=['POST'])
@login_required
@require_permission('deliveries:validate')
def validate(id):
    try:
        inv.validate_delivery(id, user=current_user)
        flash("Dispatch validated! Inventory deducted from stock ledger.", "success")
    except BusinessRuleError as e:
        flash(str(e), "error")
    return redirect(url_for('deliveries.detail', id=id))


@deliveries_bp.route('/<int:id>/cancel', methods=['POST'])
@login_required
@require_permission('deliveries:cancel')
def cancel(id):
    try:
        inv.cancel_delivery(id, user=current_user)
        flash("Delivery order canceled.", "info")
    except BusinessRuleError as e:
        flash(str(e), "error")
    return redirect(url_for('deliveries.detail', id=id))
