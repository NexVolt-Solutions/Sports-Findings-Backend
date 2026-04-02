import uuid
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_

from app.models.notification import Notification
from app.models.user import User
from app.schemas.notification import NotificationResponse
from app.schemas.common import PaginatedResponse, MessageResponse
from app.utils.pagination import PaginationParams, paginate
from app.utils.exceptions import not_found, forbidden

logger = logging.getLogger(__name__)


async def get_notifications(
    current_user: User,
    pagination: PaginationParams,
    db: AsyncSession,
) -> PaginatedResponse:
    """
    Fetch paginated notifications for the current user.
    Sort order: unread first, then newest first within each group.
    """
    query = (
        select(Notification)
        .where(Notification.user_id == current_user.id)
        .order_by(
            Notification.is_read.asc(),      # Unread (False=0) before read (True=1)
            Notification.created_at.desc(),  # Newest first within each group
        )
    )

    paginated = await paginate(db, query, pagination)

    items = [
        NotificationResponse(
            id=n.id,
            type=n.type,
            payload=n.payload,
            is_read=n.is_read,
            created_at=n.created_at,
        )
        for n in paginated.items
    ]

    paginated.items = items
    return paginated


async def mark_notification_read(
    notification_id: uuid.UUID,
    current_user: User,
    db: AsyncSession,
) -> MessageResponse:
    """
    Mark a single notification as read.
    Only the notification owner can mark it as read.
    """
    result = await db.execute(
        select(Notification).where(Notification.id == notification_id)
    )
    notification = result.scalar_one_or_none()

    if not notification:
        raise not_found("Notification")

    if notification.user_id != current_user.id:
        raise forbidden("You do not have permission to update this notification.")

    notification.is_read = True
    await db.commit()

    return MessageResponse(message="Notification marked as read.")


async def mark_all_notifications_read(
    current_user: User,
    db: AsyncSession,
) -> MessageResponse:
    """
    Mark all unread notifications as read for the current user.
    Uses a bulk UPDATE for efficiency.
    """
    await db.execute(
        update(Notification)
        .where(
            and_(
                Notification.user_id == current_user.id,
                Notification.is_read == False,  # noqa: E712
            )
        )
        .values(is_read=True)
    )
    await db.commit()

    return MessageResponse(message="All notifications marked as read.")


async def get_unread_count(
    current_user: User,
    db: AsyncSession,
) -> int:
    """
    Returns the count of unread notifications for the current user.
    Used internally by the WebSocket connection handler on connect.
    """
    from sqlalchemy import func
    result = await db.execute(
        select(func.count()).where(
            and_(
                Notification.user_id == current_user.id,
                Notification.is_read == False,  # noqa: E712
            )
        )
    )
    return result.scalar_one()
