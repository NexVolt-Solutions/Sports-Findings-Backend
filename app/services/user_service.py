import uuid
import logging
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.models.user import User, UserSport
from app.models.enums import UserStatus
from app.models.follow import Follow
from app.models.review import Review
from app.schemas.user import (
    UserResponse,
    UserProfileResponse,
    UserListItemResponse,
    UserSportResponse,
    UpdateProfileRequest,
    UserStatsResponse,
    UserActionsResponse,
    UserSettingsResponse,
    UserNavigationResponse,
    UserCtaResponse,
)
from app.schemas.review import ReviewResponse
from app.utils.exceptions import UserNotFound, conflict, bad_request
from app.utils.pagination import PaginationParams, PaginatedResponse, paginate
from app.utils.uploads import save_avatar_upload

logger = logging.getLogger(__name__)


async def list_users(
    current_user: User,
    pagination: PaginationParams,
    db: AsyncSession,
    search: str | None = None,
) -> PaginatedResponse:
    """
    Return a paginated list of public user cards for the frontend.
    Excludes the authenticated user, admin accounts, and non-active accounts.
    """
    query = (
        select(User)
        .options(selectinload(User.sports))
        .where(User.id != current_user.id)
        .where(User.is_admin.is_(False))
        .where(User.status == UserStatus.ACTIVE)
        .order_by(User.created_at.desc())
    )

    if search:
        normalized_search = f"%{search.strip()}%"
        query = query.where(
            (User.full_name.ilike(normalized_search)) |
            (User.location.ilike(normalized_search))
        )

    paginated = await paginate(db, query, pagination)

    user_ids = [user.id for user in paginated.items]
    followed_ids: set[uuid.UUID] = set()
    if user_ids:
        followed_result = await db.execute(
            select(Follow.following_id).where(
                Follow.follower_id == current_user.id,
                Follow.following_id.in_(user_ids),
            )
        )
        followed_ids = set(followed_result.scalars().all())

    paginated.items = [
        UserListItemResponse(
            id=user.id,
            full_name=user.full_name,
            bio=user.bio,
            location=user.location,
            avatar_url=user.avatar_url,
            avg_rating=user.avg_rating,
            total_games_played=user.total_games_played,
            sports=[UserSportResponse.model_validate(sport) for sport in user.sports],
            is_following=user.id in followed_ids,
        )
        for user in paginated.items
    ]
    return paginated


async def get_my_profile(user: User, db: AsyncSession) -> UserResponse:
    """Return the authenticated user's own full profile."""
    result = await db.execute(
        select(User)
        .options(selectinload(User.sports))
        .where(User.id == user.id)
    )
    user_with_sports = result.scalar_one()

    # Count followers
    followers_result = await db.execute(
        select(func.count()).where(Follow.following_id == user.id)
    )
    followers_count = followers_result.scalar_one()

    # Count following
    following_result = await db.execute(
        select(func.count()).where(Follow.follower_id == user.id)
    )
    following_count = following_result.scalar_one()

    # Count reviews
    total_reviews_result = await db.execute(
        select(func.count()).where(Review.reviewee_id == user_with_sports.id)
    )
    total_reviews = total_reviews_result.scalar_one()

    # Fetch reviews
    reviews_result = await db.execute(
        select(Review)
        .options(selectinload(Review.reviewer).selectinload(User.sports))
        .where(Review.reviewee_id == user_with_sports.id)
        .order_by(Review.created_at.desc())
    )
    reviews = reviews_result.scalars().all()

    return UserResponse(
        id=user_with_sports.id,
        full_name=user_with_sports.full_name,
        email=user_with_sports.email,
        bio=user_with_sports.bio,
        location=user_with_sports.location,
        avatar_url=user_with_sports.avatar_url,
        is_admin=user_with_sports.is_admin,
        status=user_with_sports.status,
        sports=[UserSportResponse.model_validate(s) for s in user_with_sports.sports],
        total_reviews=total_reviews,
        reviews=[ReviewResponse.model_validate(review) for review in reviews],
        stats=UserStatsResponse(
            followers=followers_count,
            following=following_count,
            matches=user_with_sports.total_games_played,
        ),
        actions=UserActionsResponse(
            can_follow=False,
            can_message=False,
            can_rate=False,
            is_own_profile=True,
        ),
        settings=UserSettingsResponse(
            notifications_enabled=True,
        ),
        navigation=UserNavigationResponse(
            public_profile_enabled=True,
            private_profile_enabled=False,
            terms_url="https://sportfinding.com/terms",
            privacy_url="https://sportfinding.com/privacy",
        ),
        cta=UserCtaResponse(
            edit_profile=True,
            share_profile=True,
        ),
        created_at=user_with_sports.created_at,
    )


async def update_profile(
    user: User,
    payload: UpdateProfileRequest,
    db: AsyncSession,
    avatar_file: UploadFile | None = None,
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
    if payload.avatar_url is not None:
        user.avatar_url = payload.avatar_url.strip()
    if avatar_file is not None:
        user.avatar_url = await save_avatar_upload(str(user.id), avatar_file)

    # Replace sports if provided
    if payload.sports is not None:
        existing = await db.execute(
            select(UserSport).where(UserSport.user_id == user.id)
        )
        for sport_record in existing.scalars().all():
            await db.delete(sport_record)

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

    return await get_my_profile(updated_user, db)


async def get_user_profile(
    target_user_id: uuid.UUID,
    current_user: User,
    db: AsyncSession,
) -> UserProfileResponse:
    """
    Return another user's public profile.
    Includes followers/following counts, is_following flag and actions.
    """
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

    # Check if this is own profile
    is_own_profile = current_user.id == target_user_id

    # Count reviews
    total_reviews_result = await db.execute(
        select(func.count()).where(Review.reviewee_id == target_user_id)
    )
    total_reviews = total_reviews_result.scalar_one()

    # Fetch reviews
    reviews_result = await db.execute(
        select(Review)
        .options(selectinload(Review.reviewer).selectinload(User.sports))
        .where(Review.reviewee_id == target_user_id)
        .order_by(Review.created_at.desc())
    )
    reviews = reviews_result.scalars().all()

    return UserProfileResponse(
        id=target.id,
        full_name=target.full_name,
        bio=target.bio,
        location=target.location,
        avatar_url=target.avatar_url,
        is_admin=target.is_admin,
        total_reviews=total_reviews,
        reviews=[ReviewResponse.model_validate(review) for review in reviews],
        sports=[UserSportResponse.model_validate(s) for s in target.sports],
        stats=UserStatsResponse(
            followers=followers_count,
            following=following_count,
            rating=target.avg_rating,
        ),
        actions=UserActionsResponse(
            can_follow=not is_own_profile,
            can_message=not is_own_profile,
            can_rate=not is_own_profile,
            is_following=is_following,
            is_own_profile=is_own_profile,
        ),
    )


async def follow_user(
    target_user_id: uuid.UUID,
    current_user: User,
    db: AsyncSession,
    background_tasks=None,
) -> None:
    """Follow another user."""
    if target_user_id == current_user.id:
        raise bad_request("You cannot follow yourself")

    result = await db.execute(select(User).where(User.id == target_user_id))
    if not result.scalar_one_or_none():
        raise UserNotFound()

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

    from app.models.notification import Notification
    from app.models.enums import NotificationType
    notification = Notification(
        user_id=target_user_id,
        type=NotificationType.NEW_FOLLOWER,
        payload={
            "follower_id": str(current_user.id),
            "follower_name": current_user.full_name,
            "follower_avatar": current_user.avatar_url,
        },
    )
    db.add(notification)
    await db.commit()

    try:
        from app.websockets.connection_manager import ws_manager
        await ws_manager.send_to_user(str(target_user_id), {
            "type": "notification",
            "notification_type": NotificationType.NEW_FOLLOWER.value,
            "payload": {
                "follower_id": str(current_user.id),
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

