import uuid
from datetime import datetime
from pydantic import BaseModel
from app.models.enums import NotificationType


class NotificationResponse(BaseModel):
    id: uuid.UUID
    type: NotificationType
    payload: dict
    is_read: bool
    created_at: datetime

    model_config = {"from_attributes": True}
