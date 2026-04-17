import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_active_user
from app.models.user import User
from app.models.enums import SportType, SkillLevel
from app.schemas.match import (
    CreateMatchRequest,
    UpdateMatchRequest,
    MatchDetailResponse,
    MatchSummaryResponse,
    MatchStatusUpdateRequest,
)
from app.schemas.common import MessageResponse, PaginatedResponse
from app.utils.pagination import PaginationParams
from app.services import match_service

router = APIRouter(prefix="/matches", tags=["Matches"])


@router.post("", response_model=MatchDetailResponse, status_code=201)
async def create_match(
    payload: CreateMatchRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new match. Creator is automatically added as host."""
    return await match_service.create_match(
        payload, current_user, db, background_tasks
    )


@router.get("", response_model=PaginatedResponse[MatchSummaryResponse])
async def list_matches(
    type: Literal["all", "my", "nearby"] = Query(default="all"),
    sport: SportType | None = Query(default=None),
    skill_level: SkillLevel | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    lat: float | None = Query(default=None),
    lng: float | None = Query(default=None),
    radius_km: int = Query(default=20, ge=1, le=100),
    pagination: PaginationParams = Depends(),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """List matches. Use type=my for user matches, type=nearby for proximity search."""
    return await match_service.list_matches_by_type(
        list_type=type,
        current_user=current_user,
        sport=sport,
        skill_level=skill_level,
        date_from=date_from,
        date_to=date_to,
        lat=lat,
        lng=lng,
        radius_km=radius_km,
        pagination=pagination,
        db=db,
    )


@router.get("/{match_id}", response_model=MatchDetailResponse)
async def get_match(
    match_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Get full details of a single match."""
    return await match_service.get_match_by_id(match_id, db)


@router.put("/{match_id}", response_model=MatchDetailResponse)
async def update_match(
    match_id: uuid.UUID,
    payload: UpdateMatchRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Update match details. Host only."""
    return await match_service.update_match(
        match_id, payload, current_user, db, background_tasks
    )


@router.delete("/{match_id}", status_code=204)
async def delete_match(
    match_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a match. Host only."""
    await match_service.delete_match(match_id, current_user, db)


@router.post("/{match_id}/join", response_model=MessageResponse, status_code=201)
async def join_match(
    match_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Join an open match. Notifies the host."""
    return await match_service.join_match(
        match_id, current_user, db, background_tasks
    )


@router.delete("/{match_id}/leave", response_model=MessageResponse)
async def leave_match(
    match_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Leave a match. Host cannot leave — must delete instead."""
    return await match_service.leave_match(match_id, current_user, db)


@router.delete("/{match_id}/players/{user_id}", response_model=MessageResponse)
async def remove_player(
    match_id: uuid.UUID,
    user_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a player from the match. Host only."""
    return await match_service.remove_player(
        match_id, user_id, current_user, db, background_tasks
    )


@router.patch("/{match_id}/status", response_model=MatchDetailResponse)
async def update_match_status(
    match_id: uuid.UUID,
    payload: MatchStatusUpdateRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Update match status. Host only. OPEN|FULL → ONGOING → COMPLETED."""
    return await match_service.update_match_status(
        match_id, payload, current_user, db, background_tasks
    )


@router.post("/{match_id}/invite/{user_id}", response_model=MessageResponse, status_code=201)
async def invite_player(
    match_id: uuid.UUID,
    user_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Invite a user to join the match. Host only.
    Sends MATCH_INVITED notification with Accept/Decline actions.
    """
    return await match_service.invite_player(
        match_id, user_id, current_user, db, background_tasks
    )


@router.post("/{match_id}/invite/accept", response_model=MessageResponse)
async def accept_invite(
    match_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Accept a match invitation.
    Joins the match and notifies the host.
    """
    return await match_service.accept_invite(
        match_id, current_user, db, background_tasks
    )


@router.post("/{match_id}/invite/decline", response_model=MessageResponse)
async def decline_invite(
    match_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Decline a match invitation.
    Notifies the host that the invite was declined.
    """
    return await match_service.decline_invite(
        match_id, current_user, db, background_tasks
    )

