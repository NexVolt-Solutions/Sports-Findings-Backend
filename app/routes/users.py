import uuid
from fastapi import APIRouter, Depends, UploadFile, File, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_active_user
from app.models.user import User
from app.schemas.user import (
    UserResponse,
    UserProfileResponse,
    UpdateProfileRequest,
    UserStatsResponse,
)
from app.schemas.review import CreateReviewRequest, ReviewResponse
from app.schemas.common import MessageResponse, PaginatedResponse
from app.utils.pagination import PaginationParams
from app.services import user_service

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=UserResponse)
async def get_my_profile(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the authenticated user's own profile."""
    return await user_service.get_my_profile(current_user, db)


@router.put("/me", response_model=UserResponse)
async def update_my_profile(
    payload: UpdateProfileRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Update the authenticated user's profile fields and sport skill levels."""
    return await user_service.update_profile(current_user, payload, db)


@router.post("/me/avatar", response_model=MessageResponse)
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload or replace the user's profile picture. (Phase 1 — Cloudinary upload)"""
    # TODO: implement Cloudinary upload in Phase 1
    return MessageResponse(message="Avatar upload coming in Phase 1.")


@router.get("/{user_id}", response_model=UserProfileResponse)
async def get_user_profile(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """View another user's public profile."""
    return await user_service.get_user_profile(user_id, current_user, db)


@router.get("/{user_id}/stats", response_model=UserStatsResponse)
async def get_user_stats(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a user's stats: games played, avg rating, total reviews."""
    return await user_service.get_user_stats(user_id, db)


@router.get("/{user_id}/reviews", response_model=PaginatedResponse[ReviewResponse])
async def get_user_reviews(
    user_id: uuid.UUID,
    pagination: PaginationParams = Depends(),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Get paginated reviews on a user's public profile. Sorted newest first."""
    return await user_service.get_user_reviews(user_id, pagination, db)


@router.post("/{user_id}/reviews", response_model=ReviewResponse, status_code=201)
async def create_review(
    user_id: uuid.UUID,
    payload: CreateReviewRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Submit a star rating and written review for a player.
    Both users must have participated in the same completed match.
    One review per reviewer per reviewee per match.
    """
    from app.services.review_service import create_review as svc_create_review
    return await svc_create_review(user_id, payload, current_user, db, background_tasks)


@router.post("/{user_id}/follow", response_model=MessageResponse, status_code=201)
async def follow_user(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Follow another user."""
    await user_service.follow_user(user_id, current_user, db)
    return MessageResponse(message="User followed successfully.")


@router.delete("/{user_id}/follow", response_model=MessageResponse)
async def unfollow_user(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Unfollow a user."""
    await user_service.unfollow_user(user_id, current_user, db)
    return MessageResponse(message="User unfollowed successfully.")


@router.get("/{user_id}/followers", response_model=PaginatedResponse[UserProfileResponse])
async def get_followers(
    user_id: uuid.UUID,
    pagination: PaginationParams = Depends(),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Get paginated list of a user's followers."""
    return await user_service.get_followers(user_id, pagination, db)


@router.get("/{user_id}/following", response_model=PaginatedResponse[UserProfileResponse])
async def get_following(
    user_id: uuid.UUID,
    pagination: PaginationParams = Depends(),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Get paginated list of users this user follows."""
    return await user_service.get_following(user_id, pagination, db)
