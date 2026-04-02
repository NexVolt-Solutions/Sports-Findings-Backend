import uuid
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.models.user import User, UserSport
from app.models.follow import Follow
from app.models.review import Review
from app.schemas.user import (
    UserResponse,
    UserProfileResponse,
    UserSportResponse,
    UpdateProfileRequest,
    UserStatsResponse,
)
from app.schemas.review import ReviewResponse
from app.utils.exceptions import UserNotFound, conflict, bad_request
from app.utils.pagination import PaginationParams, PaginatedResponse, paginate

logger = logging.getLogger(__name__)


async def get_my_profile(user: User, db: AsyncSession) -> UserResponse:
    """Return the authenticated user's own full profile with sports."""
    result = await db.execute(
        select(User)
        .options(selectinload(User.sports))
        .where(User.id == user.id)
    )
    user_with_sports = result.scalar_one()
    return UserResponse.model_validate(user_with_sports)


async def update_profile(
    user: User,
    payload: UpdateProfileRequest,
    db: AsyncSession,
) -> UserResponse:
    """
    Update the authenticated user's profile.
    Only updates fields that are explicitly provided (non-None).
    If sports list is provided, replaces all existing sport records.
    """
    # Apply scalar field updates
    if payload.full_name is not None:
        user.full_name = payload.full_name.strip()
    if payload.bio is not None:
        user.bio = payload.bio.strip()
    if payload.location is not None:
        user.location = payload.location.strip()
    if payload.phone_number is not None:
        normalized_phone = payload.phone_number.strip()
        existing_phone = await db.execute(
            select(User).where(
                User.phone_number == normalized_phone,
                User.id != user.id,
            )
        )
        if existing_phone.scalar_one_or_none():
            raise conflict("Phone number is already in use")
        user.phone_number = normalized_phone
    if payload.avatar_url is not None:
        user.avatar_url = payload.avatar_url.strip()

    # Replace sports if provided
    if payload.sports is not None:
        # Delete all existing sport records for this user
        existing = await db.execute(
            select(UserSport).where(UserSport.user_id == user.id)
        )
        for sport_record in existing.scalars().all():
            await db.delete(sport_record)

        # Insert new sport records
        for sport_entry in payload.sports:
            new_sport = UserSport(
                user_id=user.id,
                sport=sport_entry.sport,
                skill_level=sport_entry.skill_level,
            )
            db.add(new_sport)

    await db.commit()
    await db.refresh(user)

    # Reload with sports
    result = await db.execute(
        select(User)
        .options(selectinload(User.sports))
        .where(User.id == user.id)
    )
    updated_user = result.scalar_one()
    return UserResponse.model_validate(updated_user)


async def get_user_profile(
    target_user_id: uuid.UUID,
    current_user: User,
    db: AsyncSession,
) -> UserProfileResponse:
    """
    Return another user's public profile.
    Includes followers/following counts and is_following flag.
    """
    # Fetch target user with sports
    result = await db.execute(
        select(User)
        .options(selectinload(User.sports))
        .where(User.id == target_user_id)
    )
    target = result.scalar_one_or_none()
    if not target:
        raise UserNotFound()

    # Count followers
    followers_count_result = await db.execute(
        select(func.count()).where(Follow.following_id == target_user_id)
    )
    followers_count = followers_count_result.scalar_one()

    # Count following
    following_count_result = await db.execute(
        select(func.count()).where(Follow.follower_id == target_user_id)
    )
    following_count = following_count_result.scalar_one()

    # Check if current user follows this profile
    is_following_result = await db.execute(
        select(Follow).where(
            Follow.follower_id == current_user.id,
            Follow.following_id == target_user_id,
        )
    )
    is_following = is_following_result.scalar_one_or_none() is not None

    return UserProfileResponse(
        id=target.id,
        full_name=target.full_name,
        bio=target.bio,
        location=target.location,
        avatar_url=target.avatar_url,
        avg_rating=target.avg_rating,
        total_games_played=target.total_games_played,
        sports=[UserSportResponse.model_validate(s) for s in target.sports],
        followers_count=followers_count,
        following_count=following_count,
        is_following=is_following,
    )


async def get_user_stats(
    target_user_id: uuid.UUID,
    db: AsyncSession,
) -> UserStatsResponse:
    """Return a user's games played, avg rating, and total reviews count."""
    result = await db.execute(select(User).where(User.id == target_user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise UserNotFound()

    total_reviews_result = await db.execute(
        select(func.count()).where(Review.reviewee_id == target_user_id)
    )
    total_reviews = total_reviews_result.scalar_one()

    return UserStatsResponse(
        user_id=user.id,
        total_games_played=user.total_games_played,
        avg_rating=user.avg_rating,
        total_reviews=total_reviews,
    )


async def get_user_reviews(
    target_user_id: uuid.UUID,
    pagination: PaginationParams,
    db: AsyncSession,
) -> PaginatedResponse:
    """Return paginated reviews for a user's profile. Sorted newest first."""
    result = await db.execute(select(User).where(User.id == target_user_id))
    if not result.scalar_one_or_none():
        raise UserNotFound()

    query = (
        select(Review)
        .options(selectinload(Review.reviewer).selectinload(User.sports))
        .where(Review.reviewee_id == target_user_id)
        .order_by(Review.created_at.desc())
    )
    return await paginate(db, query, pagination)


async def follow_user(
    target_user_id: uuid.UUID,
    current_user: User,
    db: AsyncSession,
    background_tasks=None,
) -> None:
    """
    Follow another user.
    Sends a NEW_FOLLOWER notification to the followed user.
    """
    if target_user_id == current_user.id:
        raise bad_request("You cannot follow yourself")

    # Verify target exists
    result = await db.execute(select(User).where(User.id == target_user_id))
    if not result.scalar_one_or_none():
        raise UserNotFound()

    # Check not already following
    existing = await db.execute(
        select(Follow).where(
            Follow.follower_id == current_user.id,
            Follow.following_id == target_user_id,
        )
    )
    if existing.scalar_one_or_none():
        raise conflict("You are already following this user")

    follow = Follow(follower_id=current_user.id, following_id=target_user_id)
    db.add(follow)

    # Create NEW_FOLLOWER notification for the followed user
    from app.models.notification import Notification
    from app.models.enums import NotificationType
    notification = Notification(
        user_id=target_user_id,
        type=NotificationType.NEW_FOLLOWER,
        payload={
            "follower_id":   str(current_user.id),
            "follower_name": current_user.full_name,
            "follower_avatar": current_user.avatar_url,
        },
    )
    db.add(notification)
    await db.commit()

    # Push via WebSocket if user is online (best-effort)
    try:
        from app.websockets.connection_manager import ws_manager
        await ws_manager.send_to_user(str(target_user_id), {
            "type":              "notification",
            "notification_type": NotificationType.NEW_FOLLOWER.value,
            "payload": {
                "follower_id":   str(current_user.id),
                "follower_name": current_user.full_name,
            },
        })
    except Exception as e:
        logger.warning(f"Could not push follow notification to {target_user_id}: {e}")

    logger.info(f"User {current_user.id} followed {target_user_id}")


async def unfollow_user(
    target_user_id: uuid.UUID,
    current_user: User,
    db: AsyncSession,
) -> None:
    """Unfollow a user."""
    result = await db.execute(
        select(Follow).where(
            Follow.follower_id == current_user.id,
            Follow.following_id == target_user_id,
        )
    )
    follow = result.scalar_one_or_none()
    if not follow:
        raise bad_request("You are not following this user")

    await db.delete(follow)
    await db.commit()

    logger.info(f"User {current_user.id} unfollowed {target_user_id}")


async def get_followers(
    target_user_id: uuid.UUID,
    pagination: PaginationParams,
    db: AsyncSession,
) -> PaginatedResponse:
    """Return paginated followers list for a user."""
    result = await db.execute(select(User).where(User.id == target_user_id))
    if not result.scalar_one_or_none():
        raise UserNotFound()

    query = (
        select(User)
        .join(Follow, Follow.follower_id == User.id)
        .where(Follow.following_id == target_user_id)
        .order_by(Follow.created_at.desc())
    )
    return await paginate(db, query, pagination)


async def get_following(
    target_user_id: uuid.UUID,
    pagination: PaginationParams,
    db: AsyncSession,
) -> PaginatedResponse:
    """Return paginated list of users a user follows."""
    result = await db.execute(select(User).where(User.id == target_user_id))
    if not result.scalar_one_or_none():
        raise UserNotFound()

    query = (
        select(User)
        .join(Follow, Follow.following_id == User.id)
        .where(Follow.follower_id == target_user_id)
        .order_by(Follow.created_at.desc())
    )
    return await paginate(db, query, pagination)
