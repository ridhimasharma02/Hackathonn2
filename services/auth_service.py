import random
from datetime import datetime, timedelta
from models import db, User, PasswordResetOTP

class BusinessRuleError(Exception):
    pass


def authenticate_user(email, password):
    email = (email or '').strip().lower()
    user = User.query.filter(db.func.lower(User.email) == email).first()

    if not user or not user.check_password(password):
        raise BusinessRuleError("Invalid email or password.")

    if not user.active:
        raise BusinessRuleError("Your account has been deactivated. Please contact an administrator.")

    return user


def register_user(name, email, password, role='WAREHOUSE_STAFF', phone=None):
    name = (name or '').strip()
    email = (email or '').strip().lower()

    if not name:
        raise BusinessRuleError("Name is required.")
    if not email:
        raise BusinessRuleError("Email is required.")
    if not password or len(password) < 6:
        raise BusinessRuleError("Password must be at least 6 characters.")

    existing = User.query.filter(db.func.lower(User.email) == email).first()
    if existing:
        raise BusinessRuleError("An account with this email address already exists.")

    if role not in ('INVENTORY_MANAGER', 'WAREHOUSE_STAFF'):
        role = 'WAREHOUSE_STAFF'

    user = User(
        name=name,
        email=email,
        role=role,
        phone=phone.strip() if phone else None,
        active=True
    )
    user.set_password(password)

    db.session.add(user)
    db.session.commit()
    return user


def generate_reset_otp(email):
    email = (email or '').strip().lower()
    user = User.query.filter(db.func.lower(User.email) == email).first()
    if not user:
        raise BusinessRuleError("No account found with this email address.")

    # Invalidate previous unused OTPs for this email
    PasswordResetOTP.query.filter_by(email=email, used=False).update({'used': True})

    # Generate 6-digit OTP
    otp_code = f"{random.randint(100000, 999999):06d}"
    expires_at = datetime.utcnow() + timedelta(minutes=15)

    otp_record = PasswordResetOTP(
        email=email,
        otp=otp_code,
        expires_at=expires_at,
        used=False
    )
    db.session.add(otp_record)
    db.session.commit()

    return otp_code, user


def verify_otp_and_reset_password(email, otp_code, new_password):
    email = (email or '').strip().lower()
    otp_code = (otp_code or '').strip()

    if not new_password or len(new_password) < 6:
        raise BusinessRuleError("New password must be at least 6 characters.")

    record = PasswordResetOTP.query.filter_by(
        email=email,
        otp=otp_code,
        used=False
    ).first()

    if not record or record.expires_at < datetime.utcnow():
        raise BusinessRuleError("Invalid or expired OTP code.")

    user = User.query.filter(db.func.lower(User.email) == email).first()
    if not user:
        raise BusinessRuleError("User account not found.")

    record.used = True
    user.set_password(new_password)
    db.session.commit()

    return user


def change_user_password(user, current_password, new_password):
    if not user.check_password(current_password):
        raise BusinessRuleError("Current password is incorrect.")
    if not new_password or len(new_password) < 6:
        raise BusinessRuleError("New password must be at least 6 characters.")

    user.set_password(new_password)
    db.session.commit()
