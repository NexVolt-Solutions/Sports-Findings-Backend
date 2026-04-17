import uuid
from datetime import datetime
from pydantic import BaseModel
from app.models.enums import NotificationType


class NotificationResponse(BaseModel):
    """
    Notification response optimized for UI rendering.
    Contains pre-formatted title and body for direct display.
    """
    id: uuid.UUID
    type: NotificationType
    payload: dict
    is_read: bool
    created_at: datetime

    # ─── UI Display Fields ────────────────────────────────────
    title: str = ""
    body: str = ""
    actor_name: str = ""
    actor_avatar: str | None = None

    model_config = {"from_attributes": True}

    