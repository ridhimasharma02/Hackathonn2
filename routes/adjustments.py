from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, Adjustment, AdjustmentItem, Location, Product, User, ActivityLog
from services import inventory_service as inv
from services.inventory_service import BusinessRuleError
from services.permissions import require_permission, can
from services.stock_engine import get_on_hand

adjustments_bp = Blueprint('adjustments', __name__)

@adjustments_bp.route('/', methods=['GET'])
@login_required
def index():
    tab = request.args.get('tab', 'all')
    search = request.args.get('search', '').strip()
    location_id = request.args.get('location', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 25

    query = Adjustment.query

    if tab != 'all':
        query = query.filter(Adjustment.status == tab.capitalize())

    if search:
        query = query.filter(
            db.or_(
                Adjustment.reference.ilike(f"%{search}%"),
                Adjustment.title.ilike(f"%{search}%")
            )
        )

    pagination = query.order_by(Adjustment.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    locations = Location.query.filter_by(active=True).order_by(Location.code).all()

    tab_counts = {
        'all': Adjustment.query.count(),
        'draft': Adjustment.query.filter_by(status='Draft').count(),
        'counted': Adjustment.query.filter_by(status='Counted').count(),
        'approved': Adjustment.query.filter_by(status='Approved').count(),
        'rejected': Adjustment.query.filter_by(status='Rejected').count(),
        'canceled': Adjustment.query.filter_by(status='Canceled').count()
    }

    return render_template(
        'adjustments/list.html',
        adjustments=pagination.items,
        pagination=pagination,
        tab=tab,
        tab_counts=tab_counts,
        search=search,
        selected_location=location_id,
        locations=locations
    )


@adjustments_bp.route('/new', methods=['GET', 'POST'])
@login_required
@require_permission('adjustments:create')
def create():
    if request.method == 'POST':
        title = request.form.get('title')
        location_id = request.form.get('location_id')
        assigned_to_id = request.form.get('assigned_to_id')
        notes = request.form.get('notes')
        product_ids = request.form.getlist('product_ids[]')

        items = [{'product_id': int(pid)} for pid in product_ids if pid]

        try:
            adj = inv.create_adjustment(
                title=title,
                location_id=location_id,
                assigned_to_id=assigned_to_id,
                items=items,
                notes=notes,
                user=current_user
            )
            flash(f"Count Sheet '{adj.reference}' issued successfully.", "success")
            return redirect(url_for('adjustments.detail', id=adj.id))
        except BusinessRuleError as e:
            flash(str(e), "error")

    locations = Location.query.filter_by(active=True).order_by(Location.code).all()
    products = Product.query.filter_by(archived=False).order_by(Product.name).all()
    staff_members = User.query.filter_by(active=True).order_by(User.name).all()

    return render_template(
        'adjustments/form.html',
        locations=locations,
        products=products,
        staff_members=staff_members
    )


@adjustments_bp.route('/<int:id>', methods=['GET'])
@login_required
def detail(id):
    adj = Adjustment.query.get_or_404(id)
    logs = ActivityLog.query.filter_by(doc_type='Adjustment', doc_id=adj.id).order_by(ActivityLog.at.desc()).all()

    # Detailed line items with current live stock
    lines_info = []
    discrepancy_count = 0
    for item in adj.items:
        current_oh = get_on_hand(item.product_id, item.location_id)
        is_discrepant = False
        if item.counted_quantity is not None:
            is_discrepant = (item.counted_quantity != item.system_quantity)
            if is_discrepant:
                discrepancy_count += 1

        lines_info.append({
            'item': item,
            'current_on_hand': current_oh,
            'is_discrepant': is_discrepant
        })

    return render_template(
        'adjustments/detail.html',
        adj=adj,
        lines_info=lines_info,
        discrepancy_count=discrepancy_count,
        logs=logs
    )


@adjustments_bp.route('/<int:id>/submit-count', methods=['POST'])
@login_required
@require_permission('adjustments:count')
def submit_count(id):
    adj = Adjustment.query.get_or_404(id)
    count_map = {}

    for item in adj.items:
        counted_key = f"counted_qty_{item.id}"
        reason_key = f"reason_{item.id}"

        count_map[str(item.id)] = {
            'counted_quantity': request.form.get(counted_key),
            'reason': request.form.get(reason_key)
        }

    try:
        inv.submit_count(id, count_map, user=current_user)
        flash("Physical counts submitted successfully. Awaiting manager approval.", "success")
    except BusinessRuleError as e:
        flash(str(e), "error")

    return redirect(url_for('adjustments.detail', id=id))


@adjustments_bp.route('/<int:id>/approve', methods=['POST'])
@login_required
@require_permission('adjustments:approve')
def approve(id):
    try:
        inv.approve_adjustment(id, user=current_user)
        flash("Adjustment approved! Physical counts have reconciled system stock balances.", "success")
    except BusinessRuleError as e:
        flash(str(e), "error")
    return redirect(url_for('adjustments.detail', id=id))


@adjustments_bp.route('/<int:id>/reject', methods=['POST'])
@login_required
@require_permission('adjustments:reject')
def reject(id):
    try:
        inv.reject_adjustment(id, user=current_user)
        flash("Adjustment count rejected.", "warning")
    except BusinessRuleError as e:
        flash(str(e), "error")
    return redirect(url_for('adjustments.detail', id=id))


@adjustments_bp.route('/<int:id>/cancel', methods=['POST'])
@login_required
@require_permission('adjustments:cancel')
def cancel(id):
    try:
        inv.cancel_adjustment(id, user=current_user)
        flash("Adjustment canceled.", "info")
    except BusinessRuleError as e:
        flash(str(e), "error")
    return redirect(url_for('adjustments.detail', id=id))
