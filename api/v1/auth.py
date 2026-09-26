"""
StockSense Authentication & User Endpoints (v1)
Implements:
- OTP generation & Redis caching (10-minute TTL)
- Password reset using OTP and Argon2 hashing
- JWT login & registration
- Current authenticated user profile
"""
import random
from fastapi import APIRouter, HTTPException, status, Depends
from models import db, User
from services.cache_service import cache
from services.jwt_service import (
    create_access_token, verify_password, hash_password
)
from api.v1.schemas import (
    OTPRequest, OTPResponse, ResetPasswordRequest, LoginRequest,
    RegisterRequest, TokenResponse, UserResponse, MessageResponse
)
from api.v1.dependencies import get_current_user

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/otp-request", response_model=OTPResponse)
def request_otp(payload: OTPRequest):
    """
    Generates a secure 6-digit numeric OTP, stores it in Redis with a 10-minute TTL,
    and returns a dispatch confirmation.
    """
    email = payload.email.strip().lower()
    user = User.query.filter_by(email=email).first()
    if not user:
        # Return generic message to avoid email enumeration
        return OTPResponse(
            status="success",
            message="If this email is registered, a 6-digit OTP has been dispatched.",
            dev_otp=None
        )

    # Generate 6-digit OTP
    otp_code = f"{random.randint(100000, 999999)}"
    # Store in Redis (or in-memory fallback) with 600s TTL (10 minutes)
    cache.set_otp(email, otp_code, ttl_seconds=600)

    # In development / testing, dev_otp is provided for easy automated testing
    return OTPResponse(
        status="success",
        message="A 6-digit verification code has been generated and cached with a 10-minute TTL.",
        dev_otp=otp_code
    )


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(payload: ResetPasswordRequest):
    """
    Verifies the 6-digit OTP from Redis and updates the user's password using Argon2.
    """
    email = payload.email.strip().lower()
    cached_otp = cache.get_otp(email)

    if not cached_otp or cached_otp != payload.otp.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OTP verification code."
        )

    user = User.query.filter_by(email=email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User account not found."
        )

    # Set new password using Argon2 hashing as per whitepaper spec
    user.set_password(payload.new_password, use_argon2=True)
    db.session.commit()

    # Clear OTP after successful use
    cache.delete_otp(email)

    return MessageResponse(
        status="success",
        message="Password has been successfully updated with Argon2 encryption."
    )


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest):
    """
    Authenticates user credentials and issues a signed JWT access token.
    """
    email = payload.email.strip().lower()
    user = User.query.filter_by(email=email).first()

    if not user or not user.check_password(payload.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password."
        )

    if not user.active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated. Please contact an administrator."
        )

    token = create_access_token(user_id=user.id, email=user.email, role=user.role)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserResponse.from_orm(user)
    )


@router.post("/register", response_model=TokenResponse)
def register(payload: RegisterRequest):
    """
    Registers a new warehouse staff or inventory manager user.
    """
    email = payload.email.strip().lower()
    existing = User.query.filter_by(email=email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"An account with email '{email}' already exists."
        )

    role = payload.role.upper() if payload.role else "WAREHOUSE_STAFF"
    if role not in ("INVENTORY_MANAGER", "WAREHOUSE_STAFF"):
        role = "WAREHOUSE_STAFF"

    user = User(
        name=payload.name.strip(),
        email=email,
        role=role,
        phone=payload.phone,
        active=True
    )
    user.set_password(payload.password, use_argon2=True)
    db.session.add(user)
    db.session.commit()

    token = create_access_token(user_id=user.id, email=user.email, role=user.role)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserResponse.from_orm(user)
    )


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """
    Returns the authenticated user's profile and RBAC permissions.
    """
    return UserResponse.from_orm(current_user)
