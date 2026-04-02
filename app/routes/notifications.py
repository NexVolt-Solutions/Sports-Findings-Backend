import uuid
import json
import logging
import time
from collections import defaultdict, deque

import asyncio
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_active_user, get_ws_user
from app.models.user import User
from app.schemas.notification import NotificationResponse
from app.schemas.common import PaginatedResponse, MessageResponse
from app.utils.pagination import PaginationParams
from app.services import notification_service
from app.websockets.connection_manager import ws_manager

logger = logging.getLogger(__name__)

# ─── WebSocket abuse protection ────────────────────────────────────────────
# In-memory sliding-window rate limit per user.
_notif_rate_lock = asyncio.Lock()
_notif_user_message_times: dict[str, deque[float]] = defaultdict(deque)
_NOTIF_MAX_MESSAGES = 10
_NOTIF_WINDOW_SECONDS = 5.0


async def _allow_notification_message(user_id: str) -> bool:
    now = time.time()
    cutoff = now - _NOTIF_WINDOW_SECONDS

    async with _notif_rate_lock:
        q = _notif_user_message_times[user_id]
        while q and q[0] < cutoff:
            q.popleft()
        if len(q) >= _NOTIF_MAX_MESSAGES:
            return False
        q.append(now)
        return True


def _extract_ws_token(websocket: WebSocket, token_query_param: str) -> str:
    """Extract JWT token from Authorization header or fallback query param."""
    auth_header = websocket.headers.get("Authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        return auth_header.split(" ", 1)[1].strip()
    return token_query_param

# REST router — registered under /api/v1 in main.py
router = APIRouter(prefix="/notifications", tags=["Notifications"])

# WebSocket router — registered WITHOUT /api/v1 prefix in main.py
ws_router = APIRouter(tags=["Notifications"])


# ─── GET: List Notifications ──────────────────────────────────────────────────

@router.get("", response_model=PaginatedResponse[NotificationResponse])
async def get_notifications(
    pagination: PaginationParams = Depends(),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get paginated notifications for the current user.
    Sort: unread first, then newest first within each group.
    Default limit: 20 per page.
    """
    return await notification_service.get_notifications(current_user, pagination, db)


# ─── PATCH: Mark One as Read ──────────────────────────────────────────────────

@router.patch("/{notification_id}/read", response_model=MessageResponse)
async def mark_notification_read(
    notification_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a single notification as read. Only the owner can mark it."""
    return await notification_service.mark_notification_read(
        notification_id, current_user, db
    )


# ─── PATCH: Mark All as Read ─────────────────────────────────────────────────

@router.patch("/read-all", response_model=MessageResponse)
async def mark_all_notifications_read(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark all of the current user's unread notifications as read."""
    return await notification_service.mark_all_notifications_read(current_user, db)


# ─── WebSocket: Notification Stream ──────────────────────────────────────────

@ws_router.websocket("/ws/notifications")
async def notification_websocket(
    websocket: WebSocket,
    token: str = Query(..., description="JWT access token (fallback; prefer Authorization header)"),
    db: AsyncSession = Depends(get_db),
):
    """
    WebSocket endpoint for real-time notification delivery.

    Connection:
        wss://api.sportsplatform.com/ws/notifications?token=<JWT>

    On connect: server sends pending unread count.
    Notifications are pushed server-side — client just keeps the connection alive.

    Authentication:
        Preferred: `Authorization: Bearer <JWT>` header.
        Fallback: `?token=<JWT>` query param (legacy/compat).

    Inbound (client → server):
        { "type": "ping" }   — keepalive ping

    Outbound (server → client):
        {
            "type":              "notification",
            "notification_type": "match_joined",
            "payload":           { ... event-specific data ... }
        }

        On connect:
        {
            "type":         "connected",
            "unread_count": 3
        }

    Close codes:
        4001 — Unauthorized (invalid/expired token)
    """
    # ── Authenticate ──────────────────────────────────────────────────────────
    try:
        token_value = _extract_ws_token(websocket, token)
        user = await get_ws_user(token_value, db)
    except Exception:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    user_id = str(user.id)
    await ws_manager.connect_user(user_id, websocket)
    logger.info(f"User {user.id} connected to notification stream")

    # ── Send unread count on connect ──────────────────────────────────────────
    try:
        unread_count = await notification_service.get_unread_count(user, db)
        await websocket.send_text(json.dumps({
            "type":         "connected",
            "unread_count": unread_count,
        }))
    except Exception as e:
        logger.warning(f"Could not send unread count to user {user.id}: {e}")

    # ── Message loop ──────────────────────────────────────────────────────────
    try:
        while True:
            raw = await websocket.receive_text()

            # Handle ping — respond with pong to keep alive
            try:
                data = json.loads(raw)
                if data.get("type") == "ping":
                    if not await _allow_notification_message(user_id):
                        await websocket.send_text(json.dumps({
                            "type": "error",
                            "detail": "Rate limit exceeded. Please slow down.",
                        }))
                        continue
                    await websocket.send_text(json.dumps({"type": "pong"}))
            except (json.JSONDecodeError, Exception):
                pass  # Ignore malformed keepalive messages

    except WebSocketDisconnect:
        await ws_manager.disconnect_user(user_id, websocket)
        logger.info(f"User {user.id} disconnected from notification stream")
        _notif_user_message_times.pop(user_id, None)
    except Exception as e:
        logger.error(f"Notification WebSocket error for user {user.id}: {e}")
        await ws_manager.disconnect_user(user_id, websocket)
        _notif_user_message_times.pop(user_id, None)
