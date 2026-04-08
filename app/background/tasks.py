"""
Background Tasks
----------------
All non-blocking operations triggered after a primary API response.
Tasks run via FastAPI BackgroundTasks (Phase 1-2).
Will be migrated to Celery + Redis in a later phase for retry support.
"""

import logging
from uuid import UUID

from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType

from app.config import settings

logger = logging.getLogger(__name__)


def _mail_config() -> ConnectionConfig:
    return ConnectionConfig(
        MAIL_USERNAME=settings.mail_username,
        MAIL_PASSWORD=settings.mail_password,
        MAIL_FROM=settings.mail_from,
        MAIL_PORT=settings.mail_port,
        MAIL_SERVER=settings.mail_server,
        MAIL_STARTTLS=settings.mail_starttls,
        MAIL_SSL_TLS=settings.mail_ssl_tls,
        USE_CREDENTIALS=True,
        VALIDATE_CERTS=True,
    )


def _reset_url(token: str) -> str:
    return f"{settings.app_base_url}/reset-password?token={token}"


async def send_verification_email(user_id: UUID, email: str, otp: str) -> None:
    """Send a 6-digit email verification OTP to a newly registered user."""
    logger.info(f"[TASK] send_verification_email -> user={user_id} email={email}")

    if not settings.mail_username or not settings.mail_password or not settings.mail_from:
        logger.warning(
            "[TASK] send_verification_email skipped: missing mail configuration. "
            f"verification_otp={otp}"
        )
        return

    message = MessageSchema(
        subject=f"Verify your {settings.app_name} account",
        recipients=[email],
        body=(
            f"Welcome to {settings.app_name}.\n\n"
            "Use this 6-digit OTP to verify your email address:\n"
            f"{otp}\n\n"
            "This OTP will expire in 10 minutes.\n\n"
            "If you did not create this account, you can ignore this email."
        ),
        subtype=MessageType.plain,
    )

    try:
        await FastMail(_mail_config()).send_message(message)
        logger.info(f"[TASK] send_verification_email sent successfully -> email={email}")
    except Exception as e:
        logger.error(
            f"[TASK] send_verification_email failed for user={user_id} email={email}: {e}"
        )
    finally:
        # Never log OTPs in normal operation. If you absolutely need it for local
        # troubleshooting, enable allow_secret_logging explicitly.
        if settings.allow_secret_logging:
            logger.info(f"[DEV] verification_otp={otp}")


async def send_password_reset_email(user_id: UUID, email: str, token: str) -> None:
    """Send a password reset link."""
    logger.info(f"[TASK] send_password_reset_email -> user={user_id} email={email}")
    reset_url = _reset_url(token)

    if not settings.mail_username or not settings.mail_password or not settings.mail_from:
        logger.warning(
            "[TASK] send_password_reset_email skipped: missing mail configuration. "
            f"reset_url={reset_url}"
        )
        return

    message = MessageSchema(
        subject=f"Reset your {settings.app_name} password",
        recipients=[email],
        body=(
            f"We received a request to reset your {settings.app_name} password.\n\n"
            "Use this link to set a new password:\n"
            f"{reset_url}\n\n"
            "If you did not request this, you can ignore this email."
        ),
        subtype=MessageType.plain,
    )

    try:
        await FastMail(_mail_config()).send_message(message)
        logger.info(f"[TASK] send_password_reset_email sent successfully -> email={email}")
    except Exception as e:
        logger.error(
            f"[TASK] send_password_reset_email failed for user={user_id} email={email}: {e}"
        )
    finally:
        # Never log password reset URLs in normal operation.
        if settings.allow_secret_logging:
            logger.info(f"[DEV] reset_url={reset_url}")


async def geocode_match_address(match_id: UUID, address: str) -> None:
    """
    Geocode a match facility address using Google Maps Geocoding API.
    Updates match.latitude, match.longitude in DB.

    Called as a background task after match creation or address update.
    Never raises - logs warning on failure so the match is not affected.
    """
    logger.info(f"[TASK] geocode_match_address -> match={match_id} address={address!r}")

    try:
        from app.utils.geocoding import geocode_address
        from app.database import AsyncSessionLocal
        from app.models.match import Match
        from sqlalchemy import select

        result = await geocode_address(address)

        if result is None:
            logger.warning(
                f"[TASK] geocode_match_address: no result for match={match_id} "
                f"address={address!r} - coordinates will remain null"
            )
            return

        async with AsyncSessionLocal() as db:
            match_result = await db.execute(select(Match).where(Match.id == match_id))
            match = match_result.scalar_one_or_none()
            if match:
                match.latitude = result.latitude
                match.longitude = result.longitude
                match.location_name = result.formatted_address
                await db.commit()
                logger.info(
                    f"[TASK] geocode_match_address: match={match_id} "
                    f"-> ({result.latitude}, {result.longitude})"
                )

    except Exception as e:
        logger.error(f"[TASK] geocode_match_address failed for match={match_id}: {e}")


async def send_match_joined_notification(
    match_id: UUID,
    host_id: UUID,
    joiner_name: str,
) -> None:
    """
    Notify the match host when a new player joins their match.

    Steps:
    1. Create Notification record (type=MATCH_JOINED)
    2. Push to host's WebSocket channel via ws_manager
    3. If host is offline: send FCM/APNs push (Phase 4)
    """
    logger.info(
        f"[TASK] send_match_joined_notification -> "
        f"match={match_id} host={host_id} joiner={joiner_name!r}"
    )
    try:
        from app.database import AsyncSessionLocal
        from app.models.notification import Notification
        from app.models.enums import NotificationType
        from app.websockets.connection_manager import ws_manager

        payload = {
            "match_id": str(match_id),
            "joiner_name": joiner_name,
            "message": f"{joiner_name} joined your match.",
        }

        async with AsyncSessionLocal() as db:
            notif = Notification(
                user_id=host_id,
                type=NotificationType.MATCH_JOINED,
                payload=payload,
            )
            db.add(notif)
            await db.commit()

        await ws_manager.send_to_user(str(host_id), {
            "type": "notification",
            "notification_type": NotificationType.MATCH_JOINED.value,
            "payload": payload,
        })

    except Exception as e:
        logger.error(f"[TASK] send_match_joined_notification failed: {e}")


async def send_match_started_notification(
    match_id: UUID,
    player_ids: list[UUID],
) -> None:
    """Notify all players when the host starts the match."""
    logger.info(
        f"[TASK] send_match_started_notification -> "
        f"match={match_id} players={len(player_ids)}"
    )
    try:
        from app.database import AsyncSessionLocal
        from app.models.notification import Notification
        from app.models.enums import NotificationType
        from app.websockets.connection_manager import ws_manager

        payload = {
            "match_id": str(match_id),
            "message": "The match has started!",
        }

        async with AsyncSessionLocal() as db:
            for player_id in player_ids:
                notif = Notification(
                    user_id=player_id,
                    type=NotificationType.MATCH_STARTED,
                    payload=payload,
                )
                db.add(notif)
            await db.commit()

        for player_id in player_ids:
            await ws_manager.send_to_user(str(player_id), {
                "type": "notification",
                "notification_type": NotificationType.MATCH_STARTED.value,
                "payload": payload,
            })

    except Exception as e:
        logger.error(f"[TASK] send_match_started_notification failed: {e}")


async def send_player_removed_notification(
    match_id: UUID,
    removed_user_id: UUID,
) -> None:
    """Notify a player that they were removed from a match by the host."""
    logger.info(
        f"[TASK] send_player_removed_notification -> "
        f"match={match_id} user={removed_user_id}"
    )
    try:
        from app.database import AsyncSessionLocal
        from app.models.notification import Notification
        from app.models.enums import NotificationType
        from app.websockets.connection_manager import ws_manager

        payload = {
            "match_id": str(match_id),
            "message": "You have been removed from a match by the host.",
        }

        async with AsyncSessionLocal() as db:
            notif = Notification(
                user_id=removed_user_id,
                type=NotificationType.PLAYER_REMOVED,
                payload=payload,
            )
            db.add(notif)
            await db.commit()

        await ws_manager.send_to_user(str(removed_user_id), {
            "type": "notification",
            "notification_type": NotificationType.PLAYER_REMOVED.value,
            "payload": payload,
        })

    except Exception as e:
        logger.error(f"[TASK] send_player_removed_notification failed: {e}")


async def send_new_follower_notification(
    follower_id: UUID,
    following_id: UUID,
    follower_name: str,
) -> None:
    """
    Notify a user when someone follows them.

    Steps:
    1. Create Notification record (type=NEW_FOLLOWER)
    2. Push to following user's WebSocket channel via ws_manager
    3. If following user is offline: send FCM/APNs push (Phase 4)
    """
    logger.info(
        f"[TASK] send_new_follower_notification -> "
        f"follower={follower_id} ({follower_name!r}) following={following_id}"
    )
    try:
        from app.database import AsyncSessionLocal
        from app.models.notification import Notification
        from app.models.enums import NotificationType
        from app.websockets.connection_manager import ws_manager

        payload = {
            "follower_id": str(follower_id),
            "follower_name": follower_name,
            "message": f"{follower_name} started following you.",
        }

        async with AsyncSessionLocal() as db:
            notif = Notification(
                user_id=following_id,
                type=NotificationType.NEW_FOLLOWER,
                payload=payload,
            )
            db.add(notif)
            await db.commit()

        await ws_manager.send_to_user(str(following_id), {
            "type": "notification",
            "notification_type": NotificationType.NEW_FOLLOWER.value,
            "payload": payload,
        })

    except Exception as e:
        logger.error(f"[TASK] send_new_follower_notification failed: {e}")


async def update_games_played(player_ids: list[UUID]) -> None:
    """
    Increment total_games_played for all players in a completed match.
    Triggered when host marks a match as COMPLETED.
    """
    logger.info(f"[TASK] update_games_played -> {len(player_ids)} players")
    try:
        from app.database import AsyncSessionLocal
        from app.models.user import User
        from sqlalchemy import update

        async with AsyncSessionLocal() as db:
            await db.execute(
                update(User)
                .where(User.id.in_(player_ids))
                .values(total_games_played=User.total_games_played + 1)
            )
            await db.commit()
            logger.info(f"[TASK] update_games_played: incremented for {len(player_ids)} players")

    except Exception as e:
        logger.error(f"[TASK] update_games_played failed: {e}")


async def update_user_avg_rating(reviewee_id: UUID) -> None:
    """
    Recompute and update a user's average star rating after a new review.
    Phase 5.
    """
    logger.info(f"[TASK] update_user_avg_rating -> user={reviewee_id}")
    try:
        from app.database import AsyncSessionLocal
        from app.models.user import User
        from app.models.review import Review
        from sqlalchemy import func, select, update

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(func.avg(Review.rating)).where(Review.reviewee_id == reviewee_id)
            )
            avg = result.scalar_one_or_none() or 0.0

            await db.execute(
                update(User)
                .where(User.id == reviewee_id)
                .values(avg_rating=round(float(avg), 2))
            )
            await db.commit()
            logger.info(f"[TASK] update_user_avg_rating: user={reviewee_id} -> avg={avg:.2f}")

    except Exception as e:
        logger.error(f"[TASK] update_user_avg_rating failed: {e}")


async def persist_chat_message(
    match_id: UUID,
    sender_id: UUID,
    content: str,
    sent_at: str,
) -> None:
    """
    Persist a WebSocket chat message to the database.
    Called after broadcasting - never raises (must not crash WebSocket handler).
    Phase 4.
    """
    logger.info(f"[TASK] persist_chat_message -> match={match_id} sender={sender_id}")
    try:
        from app.database import AsyncSessionLocal
        from app.models.message import Message
        from datetime import datetime

        async with AsyncSessionLocal() as db:
            message = Message(
                match_id=match_id,
                sender_id=sender_id,
                content=content,
                sent_at=datetime.fromisoformat(sent_at),
            )
            db.add(message)
            await db.commit()

    except Exception as e:
        logger.error(f"[TASK] persist_chat_message failed: {e}")
