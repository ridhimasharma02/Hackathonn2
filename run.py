#!/usr/bin/env python3
"""
StockSense Inventory Management System - Unified Server Launcher
Launches the full unified ASGI backend:
- High-Performance FastAPI REST API at /api/v1
- Interactive OpenAPI Swagger Documentation at /docs
- ReDoc Interactive Documentation at /redoc
- Interactive Web Dashboard & Workflow UI at /
"""
import os
import sys
import threading
import time
import webbrowser
import uvicorn

from app import create_app
from seed import seed_database
from models import db, User


def open_browser(url, delay=1.2):
    time.sleep(delay)
    try:
        webbrowser.open(url)
    except Exception:
        pass


def main():
    flask_app = create_app()
    with flask_app.app_context():
        db.create_all()
        if not User.query.first():
            print("🌱 Initializing and seeding database...")
            seed_database(flask_app)
            print("✅ Database seeded successfully.")

    port = int(os.environ.get('PORT', 5001))
    host = os.environ.get('HOST', '0.0.0.0')
    browse_url = f"http://localhost:{port}"

    print("=" * 65)
    print("  🚀 StockSense Enterprise Warehouse & Ledger Engine")
    print(f"  👉 Web Dashboard:     {browse_url}")
    print(f"  👉 REST API Swagger:  {browse_url}/docs")
    print(f"  👉 ReDoc Reference:   {browse_url}/redoc")
    print(f"  👉 OpenAPI JSON:      {browse_url}/openapi.json")
    print(f"  👉 Health Check:      {browse_url}/health")
    print("  🔑 Demo Manager:      manager@stocksense.demo / Manager@2026")
    print("  🔑 Demo Staff:        staff@stocksense.demo   / Staff@2026")
    print("=" * 65)

    if os.environ.get('NO_BROWSER') != '1':
        threading.Thread(target=open_browser, args=(browse_url,), daemon=True).start()

    uvicorn.run("app_asgi:app", host=host, port=port, reload=False)


if __name__ == '__main__':
    main()
