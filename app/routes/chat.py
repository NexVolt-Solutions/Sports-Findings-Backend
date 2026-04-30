import uuid
import json
import logging
import time
from collections import defaultdict, deque
import asyncio
from datetime import datetime, timezone
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_active_user, get_ws_user
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.message import ChatMessageResponse, WSMessageOutbound
from app.utils.pagination import PaginationParams
from app.utils.exceptions import UserNotFound
from app.services import chat_service
from app.websockets.connection_manager import ws_manager
from app.background.tasks import persist_chat_message, persist_direct_chat_message

logger = logging.getLogger(__name__)

# ─── WebSocket abuse protection ────────────────────────────────────────────
# In-memory sliding-window rate limit per user.
_chat_rate_lock = asyncio.Lock()
_chat_user_message_times: dict[str, deque[float]] = defaultdict(deque)
_CHAT_MAX_MESSAGES = 10
_CHAT_WINDOW_SECONDS = 5.0


async def _allow_chat_message(user_id: str) -> bool:
    now = time.time()
    cutoff = now - _CHAT_WINDOW_SECONDS

    async with _chat_rate_lock:
        q = _chat_user_message_times[user_id]
        while q and q[0] < cutoff:
            q.popleft()
        if len(q) >= _CHAT_MAX_MESSAGES:
            return False
        q.append(now)
        return True


def _build_chat_broadcast_payload(
    *,
    message_id: uuid.UUID,
    user: User,
    content: str,
    sent_at: datetime,
) -> dict:
    payload = WSMessageOutbound(
        message_id=str(message_id),
        sender_id=str(user.id),
        sender_name=user.full_name,
        sender_avatar=user.avatar_url,
        content=content,
        sent_at=sent_at.isoformat(),
    )
    return payload.model_dump()


def _extract_ws_token(websocket: WebSocket, token_query_param: str | None) -> str | None:
    auth_header = websocket.headers.get("Authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        return auth_header.split(" ", 1)[1].strip()
    return token_query_param


async def _send_chat_error(websocket: WebSocket, detail: str) -> None:
    await websocket.send_text(json.dumps({
        "type": "error",
        "detail": detail,
    }))


def _direct_room_key(user_a_id: uuid.UUID, user_b_id: uuid.UUID) -> str:
    first, second = sorted((str(user_a_id), str(user_b_id)))
    return f"{first}:{second}"


async def _run_chat_message_loop(
    *,
    websocket: WebSocket,
    user: User,
    user_id_key: str,
    broadcast: Callable[[dict], Awaitable[None]],
    persist_message: Callable[[uuid.UUID, str, datetime], Awaitable[None]],
) -> None:
    while True:
        raw = await websocket.receive_text()

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            await _send_chat_error(websocket, "Invalid JSON format.")
            continue

        if data.get("type") != "chat_message":
            await _send_chat_error(
                websocket,
                "Unsupported message type. Use 'chat_message'.",
            )
            continue

        content = str(data.get("content", "")).strip()
        if not content:
            await _send_chat_error(websocket, "Message content cannot be empty.")
            continue

        if len(content) > 1000:
            await _send_chat_error(
                websocket,
                "Message too long. Maximum 1000 characters.",
            )
            continue

        if not await _allow_chat_message(user_id_key):
            await _send_chat_error(websocket, "Rate limit exceeded. Please slow down.")
            continue

        sent_at = datetime.now(timezone.utc)
        message_id = uuid.uuid4()
        outbound = _build_chat_broadcast_payload(
            message_id=message_id,
            user=user,
            content=content,
            sent_at=sent_at,
        )

        await broadcast(outbound)
        await persist_message(message_id, content, sent_at)

# REST router — registered under /api/v1 in main.py
router = APIRouter(tags=["Chat"])

# WebSocket router — registered WITHOUT /api/v1 prefix in main.py
ws_router = APIRouter(tags=["Chat"])


# ─── REST: Chat History ───────────────────────────────────────────────────────

@router.get(
    "/matches/{match_id}/messages",
    response_model=PaginatedResponse[ChatMessageResponse],
    tags=["Matches"],
)
async def get_match_messages(
    match_id: uuid.UUID,
    pagination: PaginationParams = Depends(),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get paginated chat history for a match.
    Only active participants can view chat history.
    Sorted newest first (most recent messages at top).
    """
    return await chat_service.get_chat_history(match_id, current_user, pagination, db)


@router.get(
    "/users/{user_id}/messages",
    response_model=PaginatedResponse[ChatMessageResponse],
    tags=["Users"],
)
async def get_direct_messages(
    user_id: uuid.UUID,
    pagination: PaginationParams = Depends(),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get paginated direct-message history between the current user and another user.
    Sorted newest first (most recent messages at top).
    """
    return await chat_service.get_direct_chat_history(
        user_id,
        current_user,
        pagination,
        db,
    )


# ─── WebSocket: Match Chat Room ───────────────────────────────────────────────

@ws_router.websocket("/ws/matches/{match_id}/chat")
async def match_chat_websocket(
    match_id: uuid.UUID,
    websocket: WebSocket,
    token: str | None = Query(None, description="JWT access token (fallback; prefer Authorization header)"),
    db: AsyncSession = Depends(get_db),
):
    """
    WebSocket endpoint for real-time match chat.

    Connection:
        wss://api.sportsplatform.com/ws/matches/{match_id}/chat?token=<JWT>

    Authentication:
        Preferred: `Authorization: Bearer <JWT>` header.
        Fallback: `?token=<JWT>` query param (legacy/compat).
        Only active match participants can connect.

    Inbound message format (client → server):
        { "type": "chat_message", "content": "Your message here" }

    Outbound broadcast format (server → all clients in room):
        {
            "type":          "chat_message",
            "message_id":    "uuid",
            "sender_id":     "uuid",
            "sender_name":   "Full Name",
            "sender_avatar": "url or null",
            "content":       "Your message here",
            "sent_at":       "2025-06-01T14:00:00+00:00"
        }

    Error message format (server → client only):
        { "type": "error", "detail": "Description of the error" }

    Close codes:
        1000 — Normal disconnect
        4001 — Unauthorized (invalid/expired token)
        4003 — Forbidden (not a match participant)
        4004 — Match not found
    """
    # ── Step 1: Authenticate ──────────────────────────────────────────────────
    try:
        token_value = _extract_ws_token(websocket, token)
        if not token_value:
            await websocket.close(code=4001, reason="Unauthorized")
            return

        user = await get_ws_user(token_value, db)
    except Exception:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    room_id = str(match_id)
    user_id_key = str(user.id)

    # ── Step 2: Verify participant ────────────────────────────────────────────
    try:
        await chat_service.verify_participant(match_id, user, db)
    except Exception as e:
        detail = getattr(e, "detail", str(e))
        code = 4003 if "participant" in str(detail).lower() else 4004
        await websocket.close(code=code, reason=str(detail))
        return

    # ── Step 3: Accept connection ─────────────────────────────────────────────
    await ws_manager.connect_to_match(room_id, websocket)
    logger.info(f"User {user.id} connected to chat room {room_id}")

    # ── Step 4: Send a welcome event to the connecting client ─────────────────
    await websocket.send_text(json.dumps({
        "type": "connected",
        "match_id": str(match_id),
        "user_id": str(user.id),
        "message": "Connected to match chat.",
    }))

    # ── Step 5: Message loop ──────────────────────────────────────────────────
    try:
        await _run_chat_message_loop(
            websocket=websocket,
            user=user,
            user_id_key=user_id_key,
            broadcast=lambda outbound: ws_manager.broadcast_to_match(room_id, outbound),
            persist_message=lambda message_id, content, sent_at: asyncio.create_task(
                persist_chat_message(
                    message_id=message_id,
                    match_id=match_id,
                    sender_id=user.id,
                    content=content,
                    sent_at=sent_at.isoformat(),
                )
            ),
        )

    except WebSocketDisconnect:
        await ws_manager.disconnect_from_match(room_id, websocket)
        logger.info(f"User {user.id} disconnected from chat room {room_id}")
        _chat_user_message_times.pop(user_id_key, None)
    except Exception as e:
        logger.error(f"WebSocket error in match chat {room_id}: {e}")
        await ws_manager.disconnect_from_match(room_id, websocket)
        _chat_user_message_times.pop(user_id_key, None)


@ws_router.websocket("/ws/users/{user_id}/chat")
async def direct_chat_websocket(
    user_id: uuid.UUID,
    websocket: WebSocket,
    token: str | None = Query(
        None,
        description="JWT access token (fallback; prefer Authorization header)",
    ),
    db: AsyncSession = Depends(get_db),
):
    """WebSocket endpoint for direct real-time chat between two users."""
    try:
        token_value = _extract_ws_token(websocket, token)
        if not token_value:
            await websocket.close(code=4001, reason="Unauthorized")
            return

        current_user = await get_ws_user(token_value, db)
    except Exception:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    try:
        target_user = await chat_service.verify_direct_chat_target(
            user_id,
            current_user,
            db,
        )
    except UserNotFound:
        await websocket.close(code=4004, reason="User not found")
        return
    except Exception as e:
        detail = getattr(e, "detail", str(e))
        await websocket.close(code=4003, reason=str(detail))
        return

    room_key = _direct_room_key(current_user.id, target_user.id)
    current_user_key = str(current_user.id)

    await ws_manager.connect_to_direct_room(room_key, websocket)
    logger.info(
        f"User {current_user.id} connected to direct chat room {room_key}"
    )

    await websocket.send_text(json.dumps({
        "type": "connected",
        "chat_type": "direct",
        "user_id": str(current_user.id),
        "target_user_id": str(target_user.id),
        "message": "Connected to direct chat.",
    }))

    try:
        await _run_chat_message_loop(
            websocket=websocket,
            user=current_user,
            user_id_key=current_user_key,
            broadcast=lambda outbound: ws_manager.broadcast_to_direct_room(
                room_key,
                outbound,
            ),
            persist_message=lambda message_id, content, sent_at: asyncio.create_task(
                persist_direct_chat_message(
                    message_id=message_id,
                    sender_id=current_user.id,
                    recipient_id=target_user.id,
                    content=content,
                    sent_at=sent_at.isoformat(),
                )
            ),
        )
    except WebSocketDisconnect:
        await ws_manager.disconnect_from_direct_room(room_key, websocket)
        logger.info(
            f"User {current_user.id} disconnected from direct chat room {room_key}"
        )
        _chat_user_message_times.pop(current_user_key, None)
    except Exception as e:
        logger.error(f"WebSocket error in direct chat {room_key}: {e}")
        await ws_manager.disconnect_from_direct_room(room_key, websocket)
        _chat_user_message_times.pop(current_user_key, None)
