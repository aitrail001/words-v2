import uuid
from time import perf_counter

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, field_validator
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logging import get_logger
from app.core.redis import get_redis
from app.core.security import (
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.services.auth_tokens import AuthTokenService
from app.api.request_db_metrics import finalize_request_db_metrics

logger = get_logger(__name__)
router = APIRouter()
security = HTTPBearer()


# Request/Response schemas
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    email: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: str
    email: str
    role: str
    tier: str
    is_active: bool


class RefreshRequest(BaseModel):
    refresh_token: str


# Dependency: get current user from JWT
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> User:
    token = credentials.credentials
    payload = decode_token(token)
    token_service = AuthTokenService(redis)
    if payload is None or payload.get("token_type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )

    user_id = payload.get("sub")
    if not isinstance(user_id, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )
    try:
        user_uuid = uuid.UUID(user_id)
    except (TypeError, ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        ) from None
    if await token_service.is_access_payload_revoked(payload):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )

    result = await db.execute(select(User).where(User.id == user_uuid))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )

    return user


async def get_current_admin_user(
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: RegisterRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> RegisterResponse:
    # Check if user exists
    result = await db.execute(select(User).where(User.email == request.email))
    existing_user = result.scalar_one_or_none()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    # Create user
    user = User(
        email=request.email,
        password_hash=hash_password(request.password),
    )
    db.add(user)
    await db.commit()

    logger.info("User registered", user_id=str(user.id), email=user.email)

    token_service = AuthTokenService(redis)
    tokens = await token_service.issue_token_pair(
        subject=str(user.id), extra={"email": user.email, "role": user.role}
    )

    return RegisterResponse(email=user.email, **tokens)


@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    http_request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> TokenResponse:
    request_start = perf_counter()
    # Find user
    result = await db.execute(select(User).where(User.email == request.email))
    user = result.scalar_one_or_none()

    # Verify credentials
    if user is None or not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is inactive",
        )

    logger.info("User logged in", user_id=str(user.id), email=user.email)

    token_service = AuthTokenService(redis)
    tokens = await token_service.issue_token_pair(
        subject=str(user.id), extra={"email": user.email, "role": user.role}
    )
    metrics = finalize_request_db_metrics(
        response,
        http_request,
        header_prefix="X-Auth",
        request_start=request_start,
    )
    logger.info("auth_request", route_name="login", **metrics)

    return TokenResponse(**tokens)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_tokens(
    request: RefreshRequest,
    http_request: Request,
    response: Response,
    redis: Redis = Depends(get_redis),
) -> TokenResponse:
    request_start = perf_counter()
    token_service = AuthTokenService(redis)
    tokens = await token_service.rotate_refresh_token(request.refresh_token)
    if tokens is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )
    metrics = finalize_request_db_metrics(
        response,
        http_request,
        header_prefix="X-Auth",
        request_start=request_start,
    )
    logger.info("auth_request", route_name="refresh", **metrics)
    return TokenResponse(**tokens)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    redis: Redis = Depends(get_redis),
) -> Response:
    payload = decode_token(credentials.credentials)
    if payload is None or payload.get("token_type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )

    user_id = payload.get("sub")
    if not isinstance(user_id, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )
    try:
        uuid.UUID(user_id)
    except (TypeError, ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        ) from None

    token_service = AuthTokenService(redis)
    await token_service.revoke_access_payload(payload)
    await token_service.revoke_refresh_tokens_for_subject(user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserResponse)
async def get_me(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    request_start = perf_counter()
    metrics = finalize_request_db_metrics(
        response,
        request,
        header_prefix="X-Auth",
        request_start=request_start,
    )
    logger.info("auth_request", route_name="me", **metrics)
    return UserResponse(
        id=str(current_user.id),
        email=current_user.email,
        role=current_user.role,
        tier=current_user.tier,
        is_active=current_user.is_active,
    )
