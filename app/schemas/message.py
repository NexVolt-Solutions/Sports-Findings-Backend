import uuid
from datetime import datetime
from pydantic import BaseModel


class ChatMessageResponse(BaseModel):
    id: uuid.UUID
    sender_id: uuid.UUID
    sender_name: str
    sender_avatar: str | None
    content: str
    sent_at: datetime

    model_config = {"from_attributes": True}



MessageResponse = ChatMessageResponse  # backward-compat alias


class WSMessageInbound(BaseModel):
    """Schema for messages received from the client over WebSocket."""
    type: str = "chat_message"
    content: str


class WSMessageOutbound(BaseModel):
    """Schema for messages broadcast to all clients in the match room."""
    type: str = "chat_message"
    message_id: str
    sender_id: str
    sender_name: str
    sender_avatar: str | None
    content: str
    sent_at: str
