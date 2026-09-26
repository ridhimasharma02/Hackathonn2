from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, Warehouse, Location, User
from services import inventory_service as inv
from services.inventory_service import BusinessRuleError
from services.permissions import require_permission

settings_bp = Blueprint('settings', __name__)

@settings_bp.route('/', methods=['GET'])
@login_required
@require_permission('settings:manage')
def index():
    tab = request.args.get('tab', 'warehouses')
    warehouses = Warehouse.query.order_by(Warehouse.code).all()
    locations = Location.query.order_by(Location.code).all()
    team_members = User.query.order_by(User.name).all()

    return render_template(
        'settings/index.html',
        tab=tab,
        warehouses=warehouses,
        locations=locations,
        team_members=team_members
    )


@settings_bp.route('/warehouses/new', methods=['POST'])
@login_required
@require_permission('settings:manage')
def create_warehouse():
    name = request.form.get('name')
    code = request.form.get('code')
    address = request.form.get('address')

    try:
        wh = inv.create_warehouse(name, code, address, user=current_user)
        flash(f"Warehouse '{wh.name}' ({wh.code}) created.", "success")
    except BusinessRuleError as e:
        flash(str(e), "error")

    return redirect(url_for('settings.index', tab='warehouses'))


@settings_bp.route('/locations/new', methods=['POST'])
@login_required
@require_permission('settings:manage')
def create_location():
    warehouse_id = request.form.get('warehouse_id')
    name = request.form.get('name')
    code = request.form.get('code')

    try:
        loc = inv.create_location(warehouse_id, name, code, user=current_user)
        flash(f"Location '{loc.code}' created.", "success")
    except BusinessRuleError as e:
        flash(str(e), "error")

    return redirect(url_for('settings.index', tab='locations'))


@settings_bp.route('/locations/<int:id>/toggle', methods=['POST'])
@login_required
@require_permission('settings:manage')
def toggle_location(id):
    try:
        loc = inv.toggle_location_active(id, user=current_user)
        state_str = "activated" if loc.active else "deactivated"
        flash(f"Location '{loc.code}' has been {state_str}.", "info")
    except BusinessRuleError as e:
        flash(str(e), "error")

    return redirect(url_for('settings.index', tab='locations'))


@settings_bp.route('/reset-demo', methods=['POST'])
@login_required
@require_permission('settings:manage')
def reset_demo():
    from seed import seed_database
    try:
        seed_database()
        flash("Demo database has been successfully reset and re-seeded with realistic data.", "success")
    except Exception as e:
        flash(f"Error resetting database: {e}", "error")

    return redirect(url_for('dashboard.index'))
