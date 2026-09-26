from functools import wraps
from flask import abort, request
from flask_login import current_user

ROLE_PERMISSIONS = {
    'INVENTORY_MANAGER': {
        # Products & Catalog
        'products:view',
        'products:manage',
        'products:create',
        'products:edit',
        'products:archive',
        # Warehouses & Locations
        'locations:view',
        'locations:manage',
        # Receipts
        'receipts:view',
        'receipts:create',
        'receipts:confirm',
        'receipts:receive',
        'receipts:validate',
        'receipts:cancel',
        # Deliveries
        'deliveries:view',
        'deliveries:create',
        'deliveries:confirm',
        'deliveries:check',
        'deliveries:pick',
        'deliveries:pack',
        'deliveries:validate',
        'deliveries:cancel',
        # Transfers
        'transfers:view',
        'transfers:create',
        'transfers:confirm',
        'transfers:complete',
        'transfers:cancel',
        # Adjustments
        'adjustments:view',
        'adjustments:create',
        'adjustments:count',
        'adjustments:approve',
        'adjustments:reject',
        'adjustments:cancel',
        # Stock Ledger & History
        'history:view',
        'history:view_full',
        'history:export',
        # Settings
        'settings:manage',
    },
    'WAREHOUSE_STAFF': {
        # Products & Catalog (view only)
        'products:view',
        # Warehouses & Locations (view only)
        'locations:view',
        # Receipts (view & record received quantities)
        'receipts:view',
        'receipts:receive',
        # Deliveries (view, pick, pack)
        'deliveries:view',
        'deliveries:pick',
        'deliveries:pack',
        # Transfers (create, confirm, complete, cancel)
        'transfers:view',
        'transfers:create',
        'transfers:confirm',
        'transfers:complete',
        'transfers:cancel',
        # Adjustments (view & submit physical counts)
        'adjustments:view',
        'adjustments:count',
        # Stock Ledger (view last 30 days)
        'history:view',
    }
}


def can(permission, user=None):
    """
    Checks if a user has a specific permission.
    If user is None, checks current_user from Flask-Login.
    """
    if user is None:
        user = current_user

    if not user or not getattr(user, 'is_authenticated', False):
        return False

    user_perms = ROLE_PERMISSIONS.get(user.role, set())
    return permission in user_perms


def check_permission(permission, user=None):
    """
    Service-level permission check. Raises PermissionError if not authorized.
    """
    if not can(permission, user):
        user_name = user.name if user and hasattr(user, 'name') else 'Anonymous'
        raise PermissionError(f"User '{user_name}' does not have permission '{permission}'.")


def require_permission(permission):
    """
    Route decorator to enforce server-side role and permission checks.
    Returns HTTP 403 on authorization failure.
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401)
            if not can(permission, current_user):
                abort(403)
            return fn(*args, **kwargs)
        return wrapper
    return decorator
