import uuid
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.user import User
from app.models.enums import UserStatus
from app.utils.security import decode_token

# ─── Bearer Token Extractor ───────────────────────────────────────────────────
bearer_scheme = HTTPBearer(auto_error=True)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Extracts and validates the Bearer JWT token from the Authorization header.
    Returns the authenticated User object.
    Raises HTTP 401 if token is missing, invalid, or expired.
    Raises HTTP 404 if the user no longer exists.
    """
    token = credentials.credentials
    user_id_str = decode_token(token, token_type="access")

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token subject",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found",
        )

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Extends get_current_user by also verifying:
    - Account is ACTIVE (not pending verification or blocked)
    Raises HTTP 403 if the account is not active.
    """
    if current_user.status == UserStatus.PENDING_VERIFICATION:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email address before continuing",
        )
    if current_user.status == UserStatus.BLOCKED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been blocked. Please contact support.",
        )
    return current_user


async def get_current_admin(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """
    Extends get_current_active_user by also verifying:
    - User has admin privileges (is_admin=True)
    Raises HTTP 403 if the user is not an admin.
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


async def get_ws_user(
    token: str,
    db: AsyncSession,
) -> User:
    """
    WebSocket-specific auth dependency.
    Used in WebSocket endpoints where the token is passed as a query parameter.
    e.g. wss://api.sportsplatform.com/ws/matches/{id}/chat?token=<JWT>

    Usage in WebSocket routes:
        token: str = Query(...)
        user = await get_ws_user(token, db)
    """
    user_id_str = decode_token(token, token_type="access")

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid token")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None or user.status != UserStatus.ACTIVE:
        raise HTTPException(status_code=401, detail="Unauthorized WebSocket connection")

    return user
