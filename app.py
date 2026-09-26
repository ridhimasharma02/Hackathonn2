import os
from flask import Flask, render_template, redirect, url_for, flash, request
from flask_login import LoginManager, current_user
from flask_wtf.csrf import CSRFProtect

from config import Config
from models import db, User, Location, Warehouse, Receipt, Delivery, Transfer, Adjustment, Product
from services.permissions import can, ROLE_PERMISSIONS
from services.stock_engine import get_on_hand, get_available, get_reserved, get_status

login_manager = LoginManager()
csrf = CSRFProtect()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Ensure instance directory exists
    instance_path = os.path.join(app.root_path, 'instance')
    os.makedirs(instance_path, exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    login_manager.login_view = 'auth.login'
    login_manager.login_message = "Please sign in to access your warehouse terminal."
    login_manager.login_message_category = "info"

    # Context processors
    @app.context_processor
    def inject_globals():
        def format_qty(val):
            if val is None:
                return "0"
            if isinstance(val, float) and val.is_integer():
                return str(int(val))
            return f"{val:.2f}".rstrip('0').rstrip('.')

        sidebar_counts = {}
        if current_user.is_authenticated:
            if current_user.is_manager:
                sidebar_counts['receipts'] = Receipt.query.filter(Receipt.status.in_(['Draft', 'Waiting', 'Ready'])).count()
                sidebar_counts['deliveries'] = Delivery.query.filter(Delivery.status.in_(['Draft', 'Waiting', 'Ready', 'Picked', 'Packed'])).count()
                sidebar_counts['transfers'] = Transfer.query.filter(Transfer.status.in_(['Draft', 'Waiting', 'Ready'])).count()
                sidebar_counts['adjustments'] = Adjustment.query.filter(Adjustment.status.in_(['Draft', 'Counted'])).count()
            else:
                # Staff tasks
                sidebar_counts['receipts'] = Receipt.query.filter_by(status='Waiting').count()
                sidebar_counts['deliveries'] = Delivery.query.filter(Delivery.status.in_(['Ready', 'Picked'])).count()
                sidebar_counts['transfers'] = Transfer.query.filter_by(status='Ready').count()
                sidebar_counts['adjustments'] = Adjustment.query.filter_by(status='Draft').count()

        active_warehouses = Warehouse.query.filter_by(active=True).all() if current_user.is_authenticated else []
        active_locations = Location.query.filter_by(active=True).all() if current_user.is_authenticated else []

        return {
            'can': can,
            'format_qty': format_qty,
            'get_on_hand': get_on_hand,
            'get_available': get_available,
            'get_reserved': get_reserved,
            'get_status': get_status,
            'sidebar_counts': sidebar_counts,
            'active_warehouses': active_warehouses,
            'active_locations': active_locations,
            'current_user': current_user
        }

    # Error Handlers
    @app.errorhandler(403)
    def forbidden_error(error):
        return render_template('partials/access_denied.html'), 403

    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('partials/404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return render_template('partials/500.html'), 500

    # Register Blueprints
    from routes.auth import auth_bp
    from routes.dashboard import dashboard_bp
    from routes.products import products_bp
    from routes.receipts import receipts_bp
    from routes.deliveries import deliveries_bp
    from routes.transfers import transfers_bp
    from routes.adjustments import adjustments_bp
    from routes.history import history_bp
    from routes.settings import settings_bp
    from routes.profile import profile_bp
    from routes.api import api_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(products_bp, url_prefix='/products')
    app.register_blueprint(receipts_bp, url_prefix='/receipts')
    app.register_blueprint(deliveries_bp, url_prefix='/delivery-orders')
    app.register_blueprint(transfers_bp, url_prefix='/internal-transfers')
    app.register_blueprint(adjustments_bp, url_prefix='/inventory-adjustments')
    app.register_blueprint(history_bp)
    app.register_blueprint(settings_bp, url_prefix='/settings')
    app.register_blueprint(profile_bp, url_prefix='/profile')
    app.register_blueprint(api_bp)

    # CLI commands
    @app.cli.command('seed')
    def seed_command():
        """Drops existing database and runs seed data script."""
        from seed import seed_database
        seed_database()

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, host='0.0.0.0', port=5001)
