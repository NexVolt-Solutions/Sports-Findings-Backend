import uuid
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_active_user, get_ws_user
from app.models.user import User
from app.schemas.message import ChatMessageResponse as MessageResponse
from app.schemas.common import PaginatedResponse, MessageResponse as MsgResp
from app.schemas.message import ChatMessageResponse
from app.utils.pagination import PaginationParams
from app.services import chat_service
from app.websockets.connection_manager import ws_manager
from app.background.tasks import persist_chat_message

logger = logging.getLogger(__name__)

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


# ─── WebSocket: Match Chat Room ───────────────────────────────────────────────

@ws_router.websocket("/ws/matches/{match_id}/chat")
async def match_chat_websocket(
    match_id: uuid.UUID,
    websocket: WebSocket,
    token: str = Query(..., description="JWT access token"),
    db: AsyncSession = Depends(get_db),
):
    """
    WebSocket endpoint for real-time match chat.

    Connection:
        wss://api.sportsplatform.com/ws/matches/{match_id}/chat?token=<JWT>

    Authentication:
        JWT access token passed as query param ?token=<JWT>
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
        user = await get_ws_user(token, db)
    except Exception:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    room_id = str(match_id)

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
        while True:
            raw = await websocket.receive_text()

            # Parse JSON
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "detail": "Invalid JSON format.",
                }))
                continue

            # Validate message type
            if data.get("type") != "chat_message":
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "detail": "Unsupported message type. Use 'chat_message'.",
                }))
                continue

            # Validate content
            content = str(data.get("content", "")).strip()
            if not content:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "detail": "Message content cannot be empty.",
                }))
                continue

            if len(content) > 1000:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "detail": "Message too long. Maximum 1000 characters.",
                }))
                continue

            sent_at = datetime.now(timezone.utc)

            # Build outbound broadcast payload
            outbound = {
                "type":          "chat_message",
                "sender_id":     str(user.id),
                "sender_name":   user.full_name,
                "sender_avatar": user.avatar_url,
                "content":       content,
                "sent_at":       sent_at.isoformat(),
            }

            # Broadcast to all clients in this match room
            await ws_manager.broadcast_to_match(room_id, outbound)

            # Persist message to DB asynchronously (non-blocking)
            # The broadcast happens first — persistence is best-effort
            import asyncio
            asyncio.create_task(
                persist_chat_message(
                    match_id=match_id,
                    sender_id=user.id,
                    content=content,
                    sent_at=sent_at.isoformat(),
                )
            )

    except WebSocketDisconnect:
        await ws_manager.disconnect_from_match(room_id, websocket)
        logger.info(f"User {user.id} disconnected from chat room {room_id}")
    except Exception as e:
        logger.error(f"WebSocket error in match chat {room_id}: {e}")
        await ws_manager.disconnect_from_match(room_id, websocket)
