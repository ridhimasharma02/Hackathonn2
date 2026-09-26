"""
StockSense Background Alerting Worker
Runs periodic scans (every 15 minutes by default or once via --once)
for products where on-hand quantity < min_stock_level, aggregating low-stock items
into an automated alert digest.
"""
import sys
import time
import argparse
import logging
from datetime import datetime
from app import create_app
from services.alert_service import scan_low_stock, dispatch_low_stock_digest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (StockSense Worker) %(message)s"
)
logger = logging.getLogger("stocksense.worker")


def run_worker_cycle(app):
    """Executes a single scan and alert cycle."""
    with app.app_context():
        logger.info("Executing periodic low-stock audit scan...")
        digest = scan_low_stock()
        summary = digest["summary"]
        logger.info(
            f"Scan completed: {summary['total_products_scanned']} products evaluated. "
            f"{summary['out_of_stock_count']} Out-of-Stock, {summary['low_stock_count']} Low-Stock."
        )

        if summary["total_alerts"] > 0:
            logger.warning(f"Generating alert digest for {summary['total_alerts']} items requiring reorder...")
            for crit in digest["critical_out_of_stock"]:
                logger.error(f"[CRITICAL OUT-OF-STOCK] {crit['sku']} - {crit['name']} (On hand: {crit['on_hand']} {crit['uom']})")
            for low in digest["low_stock_warnings"]:
                logger.warning(f"[LOW-STOCK WARNING] {low['sku']} - {low['name']} (On hand: {low['on_hand']} / Reorder: {low['min_stock_level']} {low['uom']})")

            dispatch_res = dispatch_low_stock_digest()
            logger.info("Alert digest dispatched to warehouse managers.")
        else:
            logger.info("All product inventory levels are healthy. Zero alerts.")


def main():
    parser = argparse.ArgumentParser(description="StockSense Background Worker")
    parser.add_argument("--once", action="store_true", help="Run scan once and exit")
    parser.add_argument("--interval", type=int, default=900, help="Interval in seconds between scans (default: 900s / 15m)")
    args = parser.parse_args()

    app = create_app()
    logger.info("StockSense Background Worker initialized.")

    if args.once:
        run_worker_cycle(app)
        return

    logger.info(f"Starting worker loop with interval: {args.interval}s...")
    while True:
        try:
            run_worker_cycle(app)
        except Exception as e:
            logger.exception(f"Worker cycle failed with error: {e}")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
