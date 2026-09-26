from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from services import auth_service as auth_svc
from services.auth_service import BusinessRuleError

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        remember = bool(request.form.get('remember'))

        try:
            user = auth_svc.authenticate_user(email, password)
            login_user(user, remember=remember)
            flash(f"Welcome back, {user.name}!", "success")
            next_url = request.args.get('next')
            return redirect(next_url or url_for('dashboard.index'))
        except BusinessRuleError as e:
            flash(str(e), "error")

    return render_template('auth/login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash("You have been signed out successfully.", "info")
    return redirect(url_for('auth.login'))


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role', 'WAREHOUSE_STAFF')
        phone = request.form.get('phone')

        try:
            user = auth_svc.register_user(name, email, password, role, phone)
            login_user(user)
            flash(f"Account created successfully. Welcome, {user.name}!", "success")
            return redirect(url_for('dashboard.index'))
        except BusinessRuleError as e:
            flash(str(e), "error")

    return render_template('auth/register.html')


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        try:
            otp_code, user = auth_svc.generate_reset_otp(email)
            session['reset_email'] = email
            # Demo mode notice as requested in specification
            flash(f"[DEMO MODE] Password reset OTP generated for {email}: {otp_code} (Valid for 15 minutes)", "warning")
            return redirect(url_for('auth.reset_password'))
        except BusinessRuleError as e:
            flash(str(e), "error")

    return render_template('auth/forgot_password.html')


@auth_bp.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    email = session.get('reset_email', '')

    if request.method == 'POST':
        email = request.form.get('email', email)
        otp = request.form.get('otp')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        if new_password != confirm_password:
            flash("Passwords do not match.", "error")
            return render_template('auth/reset_password.html', email=email)

        try:
            auth_svc.verify_otp_and_reset_password(email, otp, new_password)
            session.pop('reset_email', None)
            flash("Your password has been reset successfully. Please sign in.", "success")
            return redirect(url_for('auth.login'))
        except BusinessRuleError as e:
            flash(str(e), "error")

    return render_template('auth/reset_password.html', email=email)
