"""
StockSense Alert Service
Scans products against reorder levels / min_stock_levels and creates alert digests.
Supports both on-demand execution and background worker execution.
"""
from datetime import datetime
from typing import Dict, Any, List
from models import Product, Location, StockQuant
from services.stock_engine import get_on_hand, get_available


def scan_low_stock() -> Dict[str, Any]:
    """
    Scans for products where on_hand <= min_stock_level.
    Returns structured digest of low-stock and out-of-stock items.
    """
    products = Product.query.filter_by(archived=False).all()
    out_of_stock: List[Dict[str, Any]] = []
    low_stock: List[Dict[str, Any]] = []
    in_stock_count = 0

    for p in products:
        qty = get_on_hand(p.id)
        avail = get_available(p.id)
        min_level = float(getattr(p, 'min_stock_level', 0.0) or getattr(p, 'reorder_level', 0.0) or 0.0)

        if qty <= 0:
            out_of_stock.append({
                "product_id": p.id,
                "name": p.name,
                "sku": p.sku,
                "category": p.category.name if p.category else "Uncategorized",
                "uom": p.uom,
                "on_hand": qty,
                "available": avail,
                "min_stock_level": min_level,
                "deficit": round(min_level - qty, 2),
                "severity": "CRITICAL"
            })
        elif qty <= min_level:
            low_stock.append({
                "product_id": p.id,
                "name": p.name,
                "sku": p.sku,
                "category": p.category.name if p.category else "Uncategorized",
                "uom": p.uom,
                "on_hand": qty,
                "available": avail,
                "min_stock_level": min_level,
                "deficit": round(min_level - qty, 2),
                "severity": "WARNING"
            })
        else:
            in_stock_count += 1

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "summary": {
            "total_products_scanned": len(products),
            "in_stock_count": in_stock_count,
            "low_stock_count": len(low_stock),
            "out_of_stock_count": len(out_of_stock),
            "total_alerts": len(out_of_stock) + len(low_stock)
        },
        "critical_out_of_stock": out_of_stock,
        "low_stock_warnings": low_stock
    }


def dispatch_low_stock_digest() -> Dict[str, Any]:
    """
    Simulates / triggers email alert dispatch (Section 6: Alerting Automation).
    """
    digest = scan_low_stock()
    # In production, dispatch via Resend/Brevo/SMTP transactional email
    return {
        "dispatched": True,
        "recipient_role": "INVENTORY_MANAGER",
        "alerts_count": digest["summary"]["total_alerts"],
        "digest": digest
    }
