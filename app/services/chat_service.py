import uuid
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from sqlalchemy.orm import selectinload

from app.models.direct_message import DirectMessage
from app.models.message import Message
from app.models.match import Match
from app.models.match_player import MatchPlayer
from app.models.user import User
from app.models.enums import MatchPlayerStatus, UserStatus
from app.schemas.message import ChatMessageResponse as MessageResponse
from app.schemas.common import PaginatedResponse
from app.utils.pagination import PaginationParams, paginate
from app.utils.exceptions import MatchNotFound, UserNotFound, forbidden, bad_request

logger = logging.getLogger(__name__)


async def verify_participant(
    match_id: uuid.UUID,
    user: User,
    db: AsyncSession,
) -> None:
    """
    Verify that a user is an active participant in a match before
    allowing them to connect to the chat WebSocket.

    Raises HTTP 403 if the user is not an active participant.
    Raises HTTP 404 if the match does not exist.
    """
    # Verify match exists
    match_result = await db.execute(
        select(Match).where(Match.id == match_id)
    )
    match = match_result.scalar_one_or_none()
    if not match:
        raise MatchNotFound()

    # Verify user is an active participant
    player_result = await db.execute(
        select(MatchPlayer).where(
            and_(
                MatchPlayer.match_id == match_id,
                MatchPlayer.user_id == user.id,
                MatchPlayer.status == MatchPlayerStatus.ACTIVE,
            )
        )
    )
    if not player_result.scalar_one_or_none():
        raise forbidden("You must be an active participant to join this chat.")


async def get_chat_history(
    match_id: uuid.UUID,
    current_user: User,
    pagination: PaginationParams,
    db: AsyncSession,
) -> PaginatedResponse:
    """
    Fetch paginated chat history for a match.

    - Sorted newest first (reverse chronological)
    - Only participants can view chat history
    - Includes sender name and avatar for each message
    """
    # Verify match exists
    match_result = await db.execute(select(Match).where(Match.id == match_id))
    match = match_result.scalar_one_or_none()
    if not match:
        raise MatchNotFound()

    # Verify requester is a participant
    player_result = await db.execute(
        select(MatchPlayer).where(
            and_(
                MatchPlayer.match_id == match_id,
                MatchPlayer.user_id == current_user.id,
                MatchPlayer.status == MatchPlayerStatus.ACTIVE,
            )
        )
    )
    if not player_result.scalar_one_or_none():
        raise forbidden("You must be a participant to view this chat.")

    # Query messages with sender eagerly loaded, newest first
    query = (
        select(Message)
        .options(selectinload(Message.sender))
        .where(Message.match_id == match_id)
        .order_by(Message.sent_at.desc())
    )

    paginated = await paginate(db, query, pagination)

    items = [
        MessageResponse(
            id=msg.id,
            sender_id=msg.sender_id,
            sender_name=msg.sender.full_name,
            sender_avatar=msg.sender.avatar_url,
            content=msg.content,
            sent_at=msg.sent_at,
        )
        for msg in paginated.items
    ]

    paginated.items = items
    return paginated


async def verify_direct_chat_target(
    target_user_id: uuid.UUID,
    current_user: User,
    db: AsyncSession,
) -> User:
    """Validate that a direct-chat target exists and can be contacted."""
    if target_user_id == current_user.id:
        raise bad_request("You cannot start a direct chat with yourself.")

    result = await db.execute(select(User).where(User.id == target_user_id))
    target = result.scalar_one_or_none()
    if not target:
        raise UserNotFound()
    if target.status != UserStatus.ACTIVE:
        raise bad_request("Direct chat target is not available.")

    return target


async def get_direct_chat_history(
    target_user_id: uuid.UUID,
    current_user: User,
    pagination: PaginationParams,
    db: AsyncSession,
) -> PaginatedResponse:
    """
    Fetch paginated direct-message history between two users.

    - Sorted newest first
    - Only returns messages exchanged between the current user and the target
    - Includes sender name and avatar for each message
    """
    await verify_direct_chat_target(target_user_id, current_user, db)

    query = (
        select(DirectMessage)
        .options(selectinload(DirectMessage.sender))
        .where(
            or_(
                and_(
                    DirectMessage.sender_id == current_user.id,
                    DirectMessage.recipient_id == target_user_id,
                ),
                and_(
                    DirectMessage.sender_id == target_user_id,
                    DirectMessage.recipient_id == current_user.id,
                ),
            )
        )
        .order_by(DirectMessage.sent_at.desc())
    )

    paginated = await paginate(db, query, pagination)

    items = [
        MessageResponse(
            id=msg.id,
            sender_id=msg.sender_id,
            sender_name=msg.sender.full_name,
            sender_avatar=msg.sender.avatar_url,
            content=msg.content,
            sent_at=msg.sent_at,
        )
        for msg in paginated.items
    ]

    paginated.items = items
    return paginated


async def persist_message(
    match_id: uuid.UUID,
    sender_id: uuid.UUID,
    content: str,
    sent_at: datetime,
    db: AsyncSession,
) -> Message:
    """
    Persist a chat message to the database.
    Called after the message has already been broadcast via WebSocket.
    """
    message = Message(
        match_id=match_id,
        sender_id=sender_id,
        content=content,
        sent_at=sent_at,
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return message
