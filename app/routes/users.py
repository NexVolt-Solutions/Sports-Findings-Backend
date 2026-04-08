import json
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, UploadFile
from starlette.datastructures import UploadFile as StarletteUploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_active_user
from app.models.user import User
from app.schemas.common import MessageResponse, PaginatedResponse
from app.schemas.review import CreateReviewRequest, ReviewResponse
from app.schemas.user import (
    UpdateProfileRequest,
    UserListItemResponse,
    UserProfileResponse,
    UserResponse,
)
from app.services import user_service
from app.utils.exceptions import bad_request
from app.utils.pagination import PaginationParams

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("", response_model=PaginatedResponse[UserListItemResponse])
async def list_users(
    search: str | None = Query(default=None),
    pagination: PaginationParams = Depends(),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Browse public users for the frontend. Excludes the current user and admin accounts."""
    return await user_service.list_users(current_user, pagination, db, search)


@router.get("/me", response_model=UserResponse)
async def get_my_profile(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the authenticated user's own profile."""
    return await user_service.get_my_profile(current_user, db)


def _read_optional_form_value(form, key: str) -> str | None:
    value = form.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text if text else ""


async def _parse_update_profile_request(request: Request) -> tuple[UpdateProfileRequest, UploadFile | None]:
    content_type = request.headers.get("content-type", "").lower()

    if "multipart/form-data" in content_type:
        form = await request.form()
        sports_raw = _read_optional_form_value(form, "sports")
        sports = None
        if sports_raw is not None:
            try:
                sports = json.loads(sports_raw) if sports_raw else []
            except json.JSONDecodeError as exc:
                raise bad_request("Invalid sports payload. Expected JSON array.") from exc

        payload = UpdateProfileRequest.model_validate(
            {
                "full_name": _read_optional_form_value(form, "full_name"),
                "bio": _read_optional_form_value(form, "bio"),
                "location": _read_optional_form_value(form, "location"),
                "phone_number": _read_optional_form_value(form, "phone_number"),
                "avatar_url": _read_optional_form_value(form, "avatar_url"),
                "sports": sports,
            }
        )

        avatar = form.get("avatar") or form.get("file")
        if isinstance(avatar, (UploadFile, StarletteUploadFile)):
            return payload, avatar
        return payload, None

    if "application/json" in content_type:
        data = await request.json()
        return UpdateProfileRequest.model_validate(data), None

    raise bad_request("Unsupported content type. Use application/json or multipart/form-data.")


@router.put("/me", response_model=UserResponse)
async def update_my_profile(
    request: Request,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update the authenticated user's profile.
    Supports JSON for profile-only updates and multipart/form-data for profile + avatar updates.
    """
    payload, avatar_file = await _parse_update_profile_request(request)
    return await user_service.update_profile(current_user, payload, db, avatar_file)


@router.get("/{user_id}", response_model=UserProfileResponse)
async def get_user_profile(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """View another user's public profile."""
    return await user_service.get_user_profile(user_id, current_user, db)


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
