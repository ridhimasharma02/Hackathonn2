from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from models import db, Product, Category, Location, Warehouse, ReceiptItem, DeliveryItem, StockMovement
from services import inventory_service as inv
from services.inventory_service import BusinessRuleError
from services.permissions import require_permission, can
from services.stock_engine import get_on_hand, get_available, get_reserved, get_status, get_product_stock_matrix

products_bp = Blueprint('products', __name__)

@products_bp.route('/', methods=['GET'])
@login_required
def index():
    search = request.args.get('search', '').strip()
    category_id = request.args.get('category', '').strip()
    status_filter = request.args.get('status', '').strip()
    location_id = request.args.get('location', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 25

    query = Product.query.filter_by(archived=False)

    if search:
        query = query.filter(
            db.or_(
                Product.name.ilike(f"%{search}%"),
                Product.sku.ilike(f"%{search}%"),
                Product.description.ilike(f"%{search}%")
            )
        )

    if category_id and category_id.isdigit():
        query = query.filter(Product.category_id == int(category_id))

    all_products = query.order_by(Product.name.asc()).all()

    # Calculate stock data for each product and filter by status/location if requested
    filtered_items = []
    loc_id = int(location_id) if location_id and location_id.isdigit() else None

    for p in all_products:
        oh = get_on_hand(p.id, loc_id)
        res = get_reserved(p.id, loc_id)
        avail = max(0.0, oh - res)
        st = get_status(p, oh)

        if status_filter:
            if status_filter == 'in_stock' and st != 'In Stock':
                continue
            elif status_filter == 'low_stock' and st != 'Low Stock':
                continue
            elif status_filter == 'out_of_stock' and st != 'Out of Stock':
                continue

        filtered_items.append({
            'product': p,
            'on_hand': oh,
            'reserved': res,
            'available': avail,
            'status': st
        })

    # Manual pagination on computed stock items
    total_items = len(filtered_items)
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paginated_items = filtered_items[start_idx:end_idx]
    total_pages = max(1, (total_items + per_page - 1) // per_page)

    categories = Category.query.order_by(Category.name).all()
    locations = Location.query.filter_by(active=True).order_by(Location.code).all()

    return render_template(
        'products/list.html',
        items=paginated_items,
        page=page,
        total_pages=total_pages,
        total_items=total_items,
        search=search,
        selected_category=category_id,
        selected_status=status_filter,
        selected_location=location_id,
        categories=categories,
        locations=locations
    )


@products_bp.route('/new', methods=['POST'])
@login_required
@require_permission('products:create')
def create():
    name = request.form.get('name')
    sku = request.form.get('sku')
    category_id = request.form.get('category_id')
    uom = request.form.get('uom', 'unit')
    reorder_level = request.form.get('reorder_level', 0)
    description = request.form.get('description')
    initial_stock = request.form.get('initial_stock', 0)
    initial_location_id = request.form.get('initial_location_id')

    try:
        product = inv.create_product(
            name=name,
            sku=sku,
            category_id=category_id,
            uom=uom,
            reorder_level=reorder_level,
            description=description,
            initial_stock=initial_stock,
            initial_location_id=initial_location_id,
            user=current_user
        )
        flash(f"Product '{product.name}' ({product.sku}) created successfully.", "success")
    except BusinessRuleError as e:
        flash(str(e), "error")

    return redirect(url_for('products.index'))


@products_bp.route('/<int:id>', methods=['GET'])
@login_required
def detail(id):
    product = Product.query.get_or_404(id)
    matrix = get_product_stock_matrix(product.id)
    total_on_hand = matrix['total_on_hand']
    overall_status = get_status(product, total_on_hand)

    # Incoming receipts
    incoming = ReceiptItem.query.filter_by(product_id=product.id).all()

    # Outgoing deliveries
    outgoing = DeliveryItem.query.filter_by(product_id=product.id).all()

    # Recent movements
    movements = StockMovement.query.filter_by(product_id=product.id).order_by(StockMovement.at.desc()).limit(15).all()

    categories = Category.query.order_by(Category.name).all()

    return render_template(
        'products/detail.html',
        product=product,
        matrix=matrix,
        total_on_hand=total_on_hand,
        overall_status=overall_status,
        incoming=incoming,
        outgoing=outgoing,
        movements=movements,
        categories=categories
    )


@products_bp.route('/<int:id>/edit', methods=['POST'])
@login_required
@require_permission('products:edit')
def edit(id):
    name = request.form.get('name')
    category_id = request.form.get('category_id')
    uom = request.form.get('uom')
    reorder_level = request.form.get('reorder_level')
    description = request.form.get('description')

    try:
        product = inv.update_product(
            product_id=id,
            name=name,
            category_id=category_id,
            uom=uom,
            reorder_level=reorder_level,
            description=description,
            user=current_user
        )
        flash(f"Product '{product.name}' updated successfully.", "success")
    except BusinessRuleError as e:
        flash(str(e), "error")

    return redirect(url_for('products.detail', id=id))


@products_bp.route('/<int:id>/archive', methods=['POST'])
@login_required
@require_permission('products:archive')
def archive(id):
    try:
        product = inv.archive_product(id, user=current_user)
        flash(f"Product '{product.name}' ({product.sku}) archived.", "info")
    except BusinessRuleError as e:
        flash(str(e), "error")

    return redirect(url_for('products.index'))
