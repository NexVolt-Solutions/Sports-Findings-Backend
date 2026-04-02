import asyncio
import json
from collections import defaultdict
from fastapi import WebSocket
import logging

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Manages all active WebSocket connections.

    Two connection pools:
    - match_rooms: { match_id -> list of WebSocket connections }
      Used for match chat rooms.
    - user_connections: { user_id -> list of WebSocket connections }
      Used for personal notification streams.

    Thread-safe using asyncio.Lock per operation.
    """

    def __init__(self):
        # Match chat rooms: match_id (str) -> list[WebSocket]
        self.match_rooms: dict[str, list[WebSocket]] = defaultdict(list)
        # Personal notification channels: user_id (str) -> list[WebSocket]
        self.user_connections: dict[str, list[WebSocket]] = defaultdict(list)
        self._lock = asyncio.Lock()

    # ─── Match Chat Room ──────────────────────────────────────────────────────

    async def connect_to_match(self, match_id: str, websocket: WebSocket) -> None:
        """Accepts a WebSocket and adds it to the match room."""
        await websocket.accept()
        async with self._lock:
            self.match_rooms[match_id].append(websocket)
        logger.info(f"WebSocket connected to match room {match_id}")

    async def disconnect_from_match(self, match_id: str, websocket: WebSocket) -> None:
        """Removes a WebSocket from the match room."""
        async with self._lock:
            connections = self.match_rooms.get(match_id, [])
            if websocket in connections:
                connections.remove(websocket)
            if not connections:
                self.match_rooms.pop(match_id, None)
        logger.info(f"WebSocket disconnected from match room {match_id}")

    async def broadcast_to_match(self, match_id: str, message: dict) -> None:
        """
        Broadcasts a JSON message to all connected clients in a match room.
        Automatically removes stale (disconnected) connections.
        """
        message_str = json.dumps(message)
        stale: list[WebSocket] = []

        async with self._lock:
            connections = list(self.match_rooms.get(match_id, []))

        for websocket in connections:
            try:
                await websocket.send_text(message_str)
            except Exception:
                stale.append(websocket)
                logger.warning(f"Stale WebSocket in match room {match_id} — removing")

        # Clean up stale connections
        for ws in stale:
            await self.disconnect_from_match(match_id, ws)

    def get_match_connection_count(self, match_id: str) -> int:
        """Returns the number of active connections in a match room."""
        return len(self.match_rooms.get(match_id, []))

    # ─── Personal Notification Stream ────────────────────────────────────────

    async def connect_user(self, user_id: str, websocket: WebSocket) -> None:
        """Accepts a WebSocket for personal notifications."""
        await websocket.accept()
        async with self._lock:
            self.user_connections[user_id].append(websocket)
        logger.info(f"Notification WebSocket connected for user {user_id}")

    async def disconnect_user(self, user_id: str, websocket: WebSocket) -> None:
        """Removes a WebSocket from the user's notification pool."""
        async with self._lock:
            connections = self.user_connections.get(user_id, [])
            if websocket in connections:
                connections.remove(websocket)
            if not connections:
                self.user_connections.pop(user_id, None)

    async def send_to_user(self, user_id: str, message: dict) -> None:
        """
        Sends a JSON notification to all of a user's active connections.
        Used for real-time notification delivery.
        """
        message_str = json.dumps(message)
        stale: list[WebSocket] = []

        async with self._lock:
            connections = list(self.user_connections.get(user_id, []))

        for websocket in connections:
            try:
                await websocket.send_text(message_str)
            except Exception:
                stale.append(websocket)

        for ws in stale:
            await self.disconnect_user(user_id, ws)


# ─── Singleton Instance ───────────────────────────────────────────────────────
# One shared manager for the entire application lifetime.
ws_manager = ConnectionManager()
