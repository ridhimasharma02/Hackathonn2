from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db
from services import auth_service as auth_svc
from services.auth_service import BusinessRuleError
from services.permissions import ROLE_PERMISSIONS

profile_bp = Blueprint('profile', __name__)

@profile_bp.route('/', methods=['GET'])
@login_required
def index():
    user_permissions = sorted(list(ROLE_PERMISSIONS.get(current_user.role, [])))
    return render_template('profile/index.html', permissions=user_permissions)


@profile_bp.route('/update', methods=['POST'])
@login_required
def update():
    name = (request.form.get('name') or '').strip()
    phone = (request.form.get('phone') or '').strip()

    if not name:
        flash("Name is required.", "error")
        return redirect(url_for('profile.index'))

    current_user.name = name
    current_user.phone = phone or None
    db.session.commit()

    flash("Profile updated successfully.", "success")
    return redirect(url_for('profile.index'))


@profile_bp.route('/password', methods=['POST'])
@login_required
def update_password():
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')

    if new_password != confirm_password:
        flash("New passwords do not match.", "error")
        return redirect(url_for('profile.index'))

    try:
        auth_svc.change_user_password(current_user, current_password, new_password)
        flash("Password updated successfully.", "success")
    except BusinessRuleError as e:
        flash(str(e), "error")

    return redirect(url_for('profile.index'))
