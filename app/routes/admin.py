import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_admin
from app.models.user import User
from app.schemas.admin import (
    DashboardStatsResponse,
    CreateUserRequest,
    AdminUserListItemResponse,
    AdminUserDetailResponse,
    AdminMatchListItemResponse,
    ReviewModerationUserItemResponse,
    ReviewModerationUserReviewsResponse,
    ContentPageResponse,
    UpdateContentPageRequest,
    SupportRequestListItemResponse,
    SupportRequestDetailResponse,
    AdminAccountResponse,
    UpdateAdminAccountRequest,
    ChangePasswordRequest,
)
from app.schemas.match import MatchDetailResponse, UpdateMatchRequest
from app.schemas.common import PaginatedResponse, MessageResponse
from app.utils.pagination import PaginationParams
from app.services import admin_service

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/dashboard", response_model=DashboardStatsResponse)
async def get_dashboard_stats(
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Get dashboard statistics.
    Returns: total users, total matches, active matches, pending support requests, etc.
    """
    return await admin_service.get_dashboard_stats(db)


@router.get("/users", response_model=PaginatedResponse[AdminUserListItemResponse])
async def list_users(
    search: str | None = Query(default=None),
    status: str | None = Query(default=None),
    sport: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    location: str | None = Query(default=None),
    pagination: PaginationParams = Depends(),
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    return await admin_service.list_users(
        search, status, sport, date_from, date_to, location, pagination, db
    )


@router.post("/users", response_model=AdminUserDetailResponse, status_code=201)
async def create_user(
    payload: CreateUserRequest,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    return await admin_service.create_user(payload, db)


@router.get("/users/{user_id}", response_model=AdminUserDetailResponse)
async def get_user(
    user_id: uuid.UUID,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    return await admin_service.get_user(user_id, db)


@router.patch("/users/{user_id}/block", response_model=MessageResponse)
async def block_user(
    user_id: uuid.UUID,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    return await admin_service.block_user(user_id, admin, db)


@router.delete("/users/{user_id}", response_model=MessageResponse)
async def delete_user(
    user_id: uuid.UUID,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    return await admin_service.delete_user(user_id, admin, db)


@router.get("/matches", response_model=PaginatedResponse[AdminMatchListItemResponse])
async def list_matches(
    search: str | None = Query(default=None),
    location: str | None = Query(default=None),
    name: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    pagination: PaginationParams = Depends(),
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    return await admin_service.list_all_matches(
        search, location, name, date_from, date_to, pagination, db
    )


@router.put("/matches/{match_id}", response_model=MatchDetailResponse)
async def edit_match(
    match_id: uuid.UUID,
    payload: UpdateMatchRequest,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    return await admin_service.edit_match(match_id, payload, admin, db)


@router.delete("/matches/{match_id}", response_model=MessageResponse)
async def delete_match(
    match_id: uuid.UUID,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    return await admin_service.delete_match(match_id, admin, db)


@router.get("/reviews/users", response_model=PaginatedResponse[ReviewModerationUserItemResponse])
async def list_review_users(
    search: str | None = Query(default=None),
    pagination: PaginationParams = Depends(),
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    return await admin_service.list_review_users(search, pagination, db)


@router.get("/reviews/users/{user_id}", response_model=ReviewModerationUserReviewsResponse)
async def get_review_user_reviews(
    user_id: uuid.UUID,
    pagination: PaginationParams = Depends(),
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    return await admin_service.get_review_user_reviews(user_id, pagination, db)


@router.delete("/reviews/{review_id}", response_model=MessageResponse)
async def delete_review(
    review_id: uuid.UUID,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    return await admin_service.delete_review(review_id, db)


@router.get("/content/terms-of-service", response_model=ContentPageResponse)
async def get_terms_of_service(
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Fetch the Terms of Service content (managed by frontend)."""
    return await admin_service.get_content_page("terms-of-service", db)


@router.put("/content/terms-of-service", response_model=MessageResponse)
async def update_terms_of_service(
    payload: UpdateContentPageRequest,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update the Terms of Service content (admin-managed via frontend)."""
    return await admin_service.update_content_page("terms-of-service", payload, db)


@router.get("/content/privacy-policy", response_model=ContentPageResponse)
async def get_privacy_policy(
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Fetch the Privacy Policy content (managed by frontend)."""
    return await admin_service.get_content_page("privacy-policy", db)


@router.put("/content/privacy-policy", response_model=MessageResponse)
async def update_privacy_policy(
    payload: UpdateContentPageRequest,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update the Privacy Policy content (admin-managed via frontend)."""
    return await admin_service.update_content_page("privacy-policy", payload, db)


@router.get("/content/help-support", response_model=ContentPageResponse)
async def get_help_support(
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Fetch the Help & Support content (managed by frontend)."""
    return await admin_service.get_content_page("help-support", db)


@router.put("/content/help-support", response_model=MessageResponse)
async def update_help_support(
    payload: UpdateContentPageRequest,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update the Help & Support content (admin-managed via frontend)."""
    return await admin_service.update_content_page("help-support", payload, db)


@router.get("/support-requests", response_model=PaginatedResponse[SupportRequestListItemResponse])
async def list_support_requests(
    search: str | None = Query(default=None),
    status: str | None = Query(default=None),
    pagination: PaginationParams = Depends(),
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    return await admin_service.list_support_requests(search, status, pagination, db)


@router.get("/support-requests/{request_id}", response_model=SupportRequestDetailResponse)
async def get_support_request(
    request_id: uuid.UUID,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    return await admin_service.get_support_request(request_id, db)


@router.patch("/support-requests/{request_id}/resolve", response_model=MessageResponse)
async def resolve_support_request(
    request_id: uuid.UUID,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    return await admin_service.resolve_support_request(request_id, db)


@router.delete("/support-requests/{request_id}", response_model=MessageResponse)
async def delete_support_request(
    request_id: uuid.UUID,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    return await admin_service.delete_support_request(request_id, db)


@router.get("/account", response_model=AdminAccountResponse)
async def get_admin_account(
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    return await admin_service.get_admin_account(admin)


@router.put("/account", response_model=MessageResponse)
async def update_admin_account(
    payload: UpdateAdminAccountRequest,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    return await admin_service.update_admin_account(admin, payload, db)


@router.patch("/account/password", response_model=MessageResponse)
async def change_password(
    payload: ChangePasswordRequest,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    return await admin_service.change_admin_password(
        admin, payload.current_password, payload.new_password, db
    )
