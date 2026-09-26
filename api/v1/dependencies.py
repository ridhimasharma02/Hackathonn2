"""
StockSense API Dependencies
Handles authentication, user identity injection, and role-based access control guards.
"""
from fastapi import Header, HTTPException, status, Depends
from typing import Optional
from models import User, db
from services.jwt_service import decode_access_token


def get_current_user(authorization: Optional[str] = Header(None)) -> User:
    """
    Extracts and verifies Bearer token from the Authorization header.
    Returns the authenticated User database record.
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing. Bearer token required.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format. Format: 'Bearer <token>'",
            headers={"WWW-Authenticate": "Bearer"}
        )

    token = parts[1]
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
            headers={"WWW-Authenticate": "Bearer"}
        )

    user_id = payload.get("user_id")
    user = User.query.get(user_id)
    if not user or not user.active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found or deactivated",
            headers={"WWW-Authenticate": "Bearer"}
        )

    return user


def require_manager(user: User = Depends(get_current_user)) -> User:
    """Enforces INVENTORY_MANAGER role."""
    if user.role != "INVENTORY_MANAGER":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: Inventory Manager permissions required."
        )
    return user


def require_staff_or_manager(user: User = Depends(get_current_user)) -> User:
    """Allows authenticated staff or manager."""
    if user.role not in ("INVENTORY_MANAGER", "WAREHOUSE_STAFF"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: Invalid user role."
        )
    return user
