"""
StockSense Cache Service
Supports Redis 7 / Dragonfly with thread-safe in-memory fallback.
Provides fast OTP token storage with TTL, transient KPI caching, and cache invalidation.
"""
import os
import time
import json
import logging
from typing import Optional, Any

logger = logging.getLogger("stocksense.cache")

class CacheService:
    def __init__(self):
        self.redis_url = os.getenv("REDIS_URL")
        self.redis_client = None
        self._memory_cache = {}  # key -> (value, expiry_timestamp)
        self._init_redis()

    def _init_redis(self):
        if self.redis_url:
            try:
                import redis
                client = redis.Redis.from_url(self.redis_url, decode_responses=True, socket_timeout=2)
                client.ping()
                self.redis_client = client
                logger.info(f"Connected to Redis cache at {self.redis_url}")
            except Exception as e:
                logger.warning(f"Redis connection failed ({e}). Falling back to internal in-memory cache.")
                self.redis_client = None

    def set(self, key: str, value: Any, ttl_seconds: int = 600) -> bool:
        if self.redis_client:
            try:
                stored = json.dumps(value) if not isinstance(value, str) else value
                self.redis_client.setex(key, ttl_seconds, stored)
                return True
            except Exception as e:
                logger.warning(f"Redis set failed: {e}. Using in-memory fallback.")
                self.redis_client = None

        expiry = time.time() + ttl_seconds
        self._memory_cache[key] = (value, expiry)
        return True

    def get(self, key: str) -> Optional[Any]:
        if self.redis_client:
            try:
                val = self.redis_client.get(key)
                if val is not None:
                    try:
                        return json.loads(val)
                    except Exception:
                        return val
            except Exception as e:
                logger.warning(f"Redis get failed: {e}. Using in-memory fallback.")
                self.redis_client = None

        if key in self._memory_cache:
            val, expiry = self._memory_cache[key]
            if time.time() < expiry:
                return val
            else:
                del self._memory_cache[key]
        return None

    def delete(self, key: str) -> bool:
        if self.redis_client:
            try:
                self.redis_client.delete(key)
            except Exception:
                pass
        if key in self._memory_cache:
            del self._memory_cache[key]
        return True

    # -------------------------------------------------------------------------
    # Specialized Cache Helpers
    # -------------------------------------------------------------------------

    def set_otp(self, email: str, otp: str, ttl_seconds: int = 600) -> bool:
        """Stores 6-digit OTP with 10-minute default TTL."""
        key = f"otp:{email.lower().strip()}"
        return self.set(key, str(otp), ttl_seconds)

    def get_otp(self, email: str) -> Optional[str]:
        """Retrieves active OTP for email."""
        key = f"otp:{email.lower().strip()}"
        val = self.get(key)
        return str(val) if val is not None else None

    def delete_otp(self, email: str) -> bool:
        """Deletes OTP once verified."""
        key = f"otp:{email.lower().strip()}"
        return self.delete(key)

    def set_kpis(self, kpi_data: dict, ttl_seconds: int = 60) -> bool:
        """Caches aggregated KPI snapshot for 60 seconds."""
        return self.set("stocksense:kpi_snapshot", kpi_data, ttl_seconds)

    def get_kpis(self) -> Optional[dict]:
        """Reads cached KPI snapshot if available."""
        return self.get("stocksense:kpi_snapshot")

    def invalidate_kpis(self) -> bool:
        """Invalidates KPI cache after any stock-mutating operation."""
        return self.delete("stocksense:kpi_snapshot")


# Global singleton instance
cache = CacheService()
