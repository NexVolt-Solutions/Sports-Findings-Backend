import uuid
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func, and_

from app.models.notification import Notification
from app.models.user import User
from app.models.enums import NotificationType
from app.schemas.notification import NotificationResponse
from app.schemas.common import PaginatedResponse, MessageResponse
from app.utils.pagination import PaginationParams, paginate
from app.utils.exceptions import not_found, forbidden

logger = logging.getLogger(__name__)


def _build_notification_display(
    notification_type: NotificationType,
    payload: dict,
) -> tuple[str, str, str, str | None]:
    """
    Build UI-ready display fields from notification type and payload.
    Returns: (title, body, actor_name, actor_avatar)
    """
    actor_name = payload.get("host_name") or payload.get("follower_name") or payload.get("user_name") or ""
    actor_avatar = payload.get("host_avatar") or payload.get("follower_avatar") or payload.get("user_avatar")
    match_title = payload.get("match_title", "a match")
    location = payload.get("location", "")
    sport = payload.get("sport", "")
    joiner_name = payload.get("joiner_name", "Someone")

    if notification_type == NotificationType.MATCH_INVITED:
        title = f"{actor_name} invited you to join a {sport} match"
        body = location

    elif notification_type == NotificationType.MATCH_JOINED:
        title = f"{joiner_name} joined your match"
        actor_name = joiner_name
        body = sport

    elif notification_type == NotificationType.MATCH_INVITE_ACCEPTED:
        user_name = payload.get("user_name", "Someone")
        title = f"{user_name} accepted your match invitation"
        actor_name = user_name
        body = match_title

    elif notification_type == NotificationType.MATCH_INVITE_DECLINED:
        user_name = payload.get("user_name", "Someone")
        title = f"{user_name} declined your match invitation"
        actor_name = user_name
        body = match_title

    elif notification_type == NotificationType.MATCH_STARTED:
        title = "Your match has started!"
        body = match_title

    elif notification_type == NotificationType.MATCH_STATUS_CHANGED:
        status = payload.get("status", "")
        title = f"Match status changed to {status}"
        body = match_title

    elif notification_type == NotificationType.PLAYER_REMOVED:
        title = "You have been removed from a match"
        body = "Slot available now"

    elif notification_type == NotificationType.NEW_FOLLOWER:
        title = f"{actor_name} started following you"
        body = ""

    elif notification_type == NotificationType.NEW_REVIEW:
        title = f"{actor_name} left you a review"
        body = payload.get("comment", "")

    else:
        title = "New notification"
        body = ""

    return title, body, actor_name, actor_avatar


async def get_notifications(
    current_user: User,
    pagination: PaginationParams,
    db: AsyncSession,
) -> PaginatedResponse:
    """
    Fetch paginated notifications for the current user.
    Unread first, then newest first within each group.
    """
    query = (
        select(Notification)
        .where(Notification.user_id == current_user.id)
        .order_by(
            Notification.is_read.asc(),
            Notification.created_at.desc(),
        )
    )

    paginated = await paginate(db, query, pagination)

    items = []
    for n in paginated.items:
        title, body, actor_name, actor_avatar = _build_notification_display(
            n.type, n.payload
        )
        items.append(
            NotificationResponse(
                id=n.id,
                type=n.type,
                payload=n.payload,
                is_read=n.is_read,
                created_at=n.created_at,
                title=title,
                body=body,
                actor_name=actor_name,
                actor_avatar=actor_avatar,
            )
        )

    paginated.items = items
    return paginated


async def mark_notification_read(
    notification_id: uuid.UUID,
    current_user: User,
    db: AsyncSession,
) -> MessageResponse:
    """Mark a single notification as read. Owner only."""
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
    """Mark all unread notifications as read for the current user."""
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
    """Returns unread notification count for the current user."""
    result = await db.execute(
        select(func.count()).where(
            and_(
                Notification.user_id == current_user.id,
                Notification.is_read == False,  # noqa: E712
            )
        )
    )
    return result.scalar_one()

