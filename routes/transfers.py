from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, Transfer, TransferItem, Location, Product, ActivityLog
from services import inventory_service as inv
from services.inventory_service import BusinessRuleError
from services.permissions import require_permission, can
from services.stock_engine import get_on_hand

transfers_bp = Blueprint('transfers', __name__)

@transfers_bp.route('/', methods=['GET'])
@login_required
def index():
    tab = request.args.get('tab', 'all')
    search = request.args.get('search', '').strip()
    source_id = request.args.get('source', '').strip()
    dest_id = request.args.get('dest', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 25

    query = Transfer.query

    if tab != 'all':
        query = query.filter(Transfer.status == tab.capitalize())

    if search:
        query = query.filter(
            db.or_(
                Transfer.reference.ilike(f"%{search}%"),
                Transfer.reason.ilike(f"%{search}%")
            )
        )

    if source_id and source_id.isdigit():
        query = query.filter(Transfer.source_location_id == int(source_id))

    if dest_id and dest_id.isdigit():
        query = query.filter(Transfer.destination_location_id == int(dest_id))

    pagination = query.order_by(Transfer.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    locations = Location.query.filter_by(active=True).order_by(Location.code).all()

    tab_counts = {
        'all': Transfer.query.count(),
        'draft': Transfer.query.filter_by(status='Draft').count(),
        'waiting': Transfer.query.filter_by(status='Waiting').count(),
        'ready': Transfer.query.filter_by(status='Ready').count(),
        'done': Transfer.query.filter_by(status='Done').count(),
        'canceled': Transfer.query.filter_by(status='Canceled').count()
    }

    return render_template(
        'transfers/list.html',
        transfers=pagination.items,
        pagination=pagination,
        tab=tab,
        tab_counts=tab_counts,
        search=search,
        selected_source=source_id,
        selected_dest=dest_id,
        locations=locations
    )


@transfers_bp.route('/new', methods=['GET', 'POST'])
@login_required
@require_permission('transfers:create')
def create():
    if request.method == 'POST':
        source_location_id = request.form.get('source_location_id')
        destination_location_id = request.form.get('destination_location_id')
        scheduled_date_str = request.form.get('scheduled_date')
        reason = request.form.get('reason')
        priority = request.form.get('priority', 'Normal')

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
            transfer = inv.create_transfer(
                source_location_id=source_location_id,
                destination_location_id=destination_location_id,
                scheduled_date=scheduled_date,
                reason=reason,
                priority=priority,
                items=items,
                user=current_user
            )
            flash(f"Internal Transfer '{transfer.reference}' created.", "success")
            return redirect(url_for('transfers.detail', id=transfer.id))
        except BusinessRuleError as e:
            flash(str(e), "error")

    locations = Location.query.filter_by(active=True).order_by(Location.code).all()
    products = Product.query.filter_by(archived=False).order_by(Product.name).all()

    return render_template(
        'transfers/form.html',
        locations=locations,
        products=products
    )


@transfers_bp.route('/<int:id>', methods=['GET'])
@login_required
def detail(id):
    transfer = Transfer.query.get_or_404(id)
    logs = ActivityLog.query.filter_by(doc_type='Internal Transfer', doc_id=transfer.id).order_by(ActivityLog.at.desc()).all()

    # Route delta info
    items_info = []
    for item in transfer.items:
        src_oh = get_on_hand(item.product_id, transfer.source_location_id)
        dest_oh = get_on_hand(item.product_id, transfer.destination_location_id)
        items_info.append({
            'item': item,
            'src_on_hand': src_oh,
            'dest_on_hand': dest_oh,
            'src_after': src_oh - item.quantity,
            'dest_after': dest_oh + item.quantity
        })

    return render_template(
        'transfers/detail.html',
        transfer=transfer,
        items_info=items_info,
        logs=logs
    )


@transfers_bp.route('/<int:id>/confirm', methods=['POST'])
@login_required
@require_permission('transfers:confirm')
def confirm(id):
    try:
        inv.confirm_transfer(id, user=current_user)
        flash("Transfer confirmed and ready to move.", "success")
    except BusinessRuleError as e:
        flash(str(e), "error")
    return redirect(url_for('transfers.detail', id=id))


@transfers_bp.route('/<int:id>/complete', methods=['POST'])
@login_required
@require_permission('transfers:complete')
def complete(id):
    try:
        inv.complete_transfer(id, user=current_user)
        flash("Internal relocation completed. Stock moved successfully between locations.", "success")
    except BusinessRuleError as e:
        flash(str(e), "error")
    return redirect(url_for('transfers.detail', id=id))


@transfers_bp.route('/<int:id>/cancel', methods=['POST'])
@login_required
@require_permission('transfers:cancel')
def cancel(id):
    try:
        inv.cancel_transfer(id, user=current_user)
        flash("Transfer canceled.", "info")
    except BusinessRuleError as e:
        flash(str(e), "error")
    return redirect(url_for('transfers.detail', id=id))
