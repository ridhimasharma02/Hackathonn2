from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, Receipt, ReceiptItem, Supplier, Location, Product, ActivityLog
from services import inventory_service as inv
from services.inventory_service import BusinessRuleError
from services.permissions import require_permission, can
from services.stock_engine import get_on_hand

receipts_bp = Blueprint('receipts', __name__)

@receipts_bp.route('/', methods=['GET'])
@login_required
def index():
    tab = request.args.get('tab', 'all')
    search = request.args.get('search', '').strip()
    supplier_id = request.args.get('supplier', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 25

    query = Receipt.query

    if tab != 'all':
        query = query.filter(Receipt.status == tab.capitalize())

    if search:
        query = query.filter(
            db.or_(
                Receipt.reference.ilike(f"%{search}%"),
                Receipt.source_document.ilike(f"%{search}%")
            )
        )

    if supplier_id and supplier_id.isdigit():
        query = query.filter(Receipt.supplier_id == int(supplier_id))

    pagination = query.order_by(Receipt.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    suppliers = Supplier.query.order_by(Supplier.name).all()

    # Calculate status counts for tabs
    tab_counts = {
        'all': Receipt.query.count(),
        'draft': Receipt.query.filter_by(status='Draft').count(),
        'waiting': Receipt.query.filter_by(status='Waiting').count(),
        'ready': Receipt.query.filter_by(status='Ready').count(),
        'done': Receipt.query.filter_by(status='Done').count(),
        'canceled': Receipt.query.filter_by(status='Canceled').count()
    }

    return render_template(
        'receipts/list.html',
        receipts=pagination.items,
        pagination=pagination,
        tab=tab,
        tab_counts=tab_counts,
        search=search,
        selected_supplier=supplier_id,
        suppliers=suppliers
    )


@receipts_bp.route('/new', methods=['GET', 'POST'])
@login_required
@require_permission('receipts:create')
def create():
    if request.method == 'POST':
        supplier_id = request.form.get('supplier_id')
        destination_location_id = request.form.get('destination_location_id')
        scheduled_date_str = request.form.get('scheduled_date')
        source_document = request.form.get('source_document')
        notes = request.form.get('notes')

        scheduled_date = None
        if scheduled_date_str:
            try:
                scheduled_date = datetime.strptime(scheduled_date_str, '%Y-%m-%d')
            except ValueError:
                pass

        # Parse dynamic line items: product_id[], quantity[]
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
            receipt = inv.create_receipt(
                supplier_id=supplier_id,
                destination_location_id=destination_location_id,
                scheduled_date=scheduled_date,
                source_document=source_document,
                notes=notes,
                items=items,
                user=current_user
            )
            flash(f"Receipt '{receipt.reference}' created in Draft state.", "success")
            return redirect(url_for('receipts.detail', id=receipt.id))
        except BusinessRuleError as e:
            flash(str(e), "error")

    suppliers = Supplier.query.order_by(Supplier.name).all()
    locations = Location.query.filter_by(active=True).order_by(Location.code).all()
    products = Product.query.filter_by(archived=False).order_by(Product.name).all()

    return render_template(
        'receipts/form.html',
        suppliers=suppliers,
        locations=locations,
        products=products
    )


@receipts_bp.route('/<int:id>', methods=['GET'])
@login_required
def detail(id):
    receipt = Receipt.query.get_or_404(id)
    logs = ActivityLog.query.filter_by(doc_type='Receipt', doc_id=receipt.id).order_by(ActivityLog.at.desc()).all()

    return render_template(
        'receipts/detail.html',
        receipt=receipt,
        logs=logs
    )


@receipts_bp.route('/<int:id>/confirm', methods=['POST'])
@login_required
@require_permission('receipts:confirm')
def confirm(id):
    try:
        inv.confirm_receipt(id, user=current_user)
        flash("Receipt confirmed and set to Waiting for arrival.", "success")
    except BusinessRuleError as e:
        flash(str(e), "error")
    return redirect(url_for('receipts.detail', id=id))


@receipts_bp.route('/<int:id>/receive', methods=['POST'])
@login_required
@require_permission('receipts:receive')
def receive(id):
    receipt = Receipt.query.get_or_404(id)
    received_map = {}
    for item in receipt.items:
        key = f"received_qty_{item.id}"
        if key in request.form:
            received_map[str(item.id)] = request.form.get(key)

    try:
        inv.receive_goods(id, received_map, user=current_user)
        flash("Received quantities recorded. Receipt is Ready for manager validation.", "success")
    except BusinessRuleError as e:
        flash(str(e), "error")
    return redirect(url_for('receipts.detail', id=id))


@receipts_bp.route('/<int:id>/validate', methods=['POST'])
@login_required
@require_permission('receipts:validate')
def validate(id):
    try:
        inv.validate_receipt(id, user=current_user)
        flash("Receipt validated. Stock ledger updated with incoming inventory.", "success")
    except BusinessRuleError as e:
        flash(str(e), "error")
    return redirect(url_for('receipts.detail', id=id))


@receipts_bp.route('/<int:id>/cancel', methods=['POST'])
@login_required
@require_permission('receipts:cancel')
def cancel(id):
    try:
        inv.cancel_receipt(id, user=current_user)
        flash("Receipt canceled.", "info")
    except BusinessRuleError as e:
        flash(str(e), "error")
    return redirect(url_for('receipts.detail', id=id))
