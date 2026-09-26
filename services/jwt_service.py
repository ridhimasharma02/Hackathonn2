"""
StockSense JWT & Security Service
Handles JWT authentication tokens, claims verification, and password hashing (Argon2 / Werkzeug).
"""
import os
import jwt
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from werkzeug.security import generate_password_hash, check_password_hash

try:
    from argon2 import PasswordHasher
    argon2_hasher = PasswordHasher()
except ImportError:
    argon2_hasher = None

JWT_SECRET = os.getenv("JWT_SECRET", "env_app_secret_production_key_2026_stocksense")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24


def hash_password(password: str, use_argon2: bool = True) -> str:
    """Hashes a password using Argon2id or Werkzeug scrypt."""
    if use_argon2 and argon2_hasher is not None:
        try:
            return argon2_hasher.hash(password)
        except Exception:
            pass
    return generate_password_hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies plain password against Argon2 or Werkzeug hash."""
    if not hashed_password or not plain_password:
        return False
    if hashed_password.startswith("$argon2"):
        if argon2_hasher is not None:
            try:
                return argon2_hasher.verify(hashed_password, plain_password)
            except Exception:
                return False
    return check_password_hash(hashed_password, plain_password)


def create_access_token(user_id: int, email: str, role: str, expires_delta: Optional[timedelta] = None) -> str:
    """Creates a signed JWT access token with role and identity claims."""
    now = datetime.utcnow()
    expire = now + (expires_delta or timedelta(hours=JWT_EXPIRATION_HOURS))
    payload = {
        "sub": str(user_id),
        "user_id": user_id,
        "email": email,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp())
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Decodes and validates JWT access token."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.PyJWTError:
        return None
