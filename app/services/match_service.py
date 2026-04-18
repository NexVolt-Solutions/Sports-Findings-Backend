import uuid
import logging
from datetime import datetime, timezone

from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload

from app.models.match import Match
from app.models.match_player import MatchPlayer
from app.models.user import User
from app.models.enums import (
    SportType,
    SkillLevel,
    MatchStatus,
    MatchPlayerRole,
    MatchPlayerStatus,
    NotificationType,
)
from app.schemas.match import (
    CreateMatchRequest,
    UpdateMatchRequest,
    MatchDetailResponse,
    MatchSummaryResponse,
    MatchPlayerResponse,
    MatchStatusUpdateRequest,
)
from app.schemas.user import UserSummaryResponse
from app.schemas.common import MessageResponse
from app.utils.exceptions import (
    MatchNotFound,
    MatchFull,
    MatchNotOpen,
    AlreadyJoined,
    NotMatchHost,
    UserNotFound,
    forbidden,
    bad_request,
    conflict,
)
from app.utils.pagination import PaginationParams, PaginatedResponse, paginate
from app.background.tasks import (
    geocode_match_address,
    send_match_joined_notification,
    send_match_started_notification,
    send_player_removed_notification,
    update_games_played,
)

logger = logging.getLogger(__name__)


def _format_scheduled_date(value: datetime) -> str:
    return value.strftime("%Y-%m-%d")


def _format_scheduled_time(value: datetime) -> str:
    return value.strftime("%H:%M")


def _parse_iso_datetime(value: str) -> datetime:
    value = value.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        import re
        value_stripped = re.sub(r"[+-]\d{2}:\d{2}$", "", value)
        dt = datetime.fromisoformat(value_stripped)
        dt = dt.replace(tzinfo=timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


VALID_TRANSITIONS: dict[MatchStatus, list[MatchStatus]] = {
    MatchStatus.OPEN:      [MatchStatus.ONGOING, MatchStatus.CANCELLED],
    MatchStatus.FULL:      [MatchStatus.ONGOING, MatchStatus.CANCELLED],
    MatchStatus.ONGOING:   [MatchStatus.COMPLETED],
    MatchStatus.COMPLETED: [],
    MatchStatus.CANCELLED: [],
}


# ─── Internal Helpers ─────────────────────────────────────────────────────────

async def _get_match_or_404(match_id: uuid.UUID, db: AsyncSession) -> Match:
    result = await db.execute(
        select(Match)
        .options(selectinload(Match.host))
        .where(Match.id == match_id)
    )
    match = result.scalar_one_or_none()
    if not match:
        raise MatchNotFound()
    return match


async def _count_active_players(match_id: uuid.UUID, db: AsyncSession) -> int:
    result = await db.execute(
        select(func.count()).where(
            and_(
                MatchPlayer.match_id == match_id,
                MatchPlayer.status == MatchPlayerStatus.ACTIVE,
            )
        )
    )
    return result.scalar_one()


async def _fetch_match_participants(
    match_id: uuid.UUID, db: AsyncSession
) -> list[MatchPlayerResponse]:
    result = await db.execute(
        select(MatchPlayer)
        .options(selectinload(MatchPlayer.user))
        .where(
            and_(
                MatchPlayer.match_id == match_id,
                MatchPlayer.status == MatchPlayerStatus.ACTIVE,
            )
        )
        .order_by(MatchPlayer.joined_at.asc())
    )
    participants = []
    for mp in result.scalars().all():
        participants.append(
            MatchPlayerResponse(
                user=UserSummaryResponse(
                    id=mp.user.id,
                    full_name=mp.user.full_name,
                    avatar_url=mp.user.avatar_url,
                    avg_rating=mp.user.avg_rating,
                    total_games_played=mp.user.total_games_played,
                ),
                role=mp.role.value,
                joined_at=mp.joined_at,
            )
        )
    return participants


async def _count_active_players_for_match_ids(
    match_ids: list[uuid.UUID],
    db: AsyncSession,
) -> dict[uuid.UUID, int]:
    if not match_ids:
        return {}
    result = await db.execute(
        select(MatchPlayer.match_id, func.count())
        .where(
            and_(
                MatchPlayer.match_id.in_(match_ids),
                MatchPlayer.status == MatchPlayerStatus.ACTIVE,
            )
        )
        .group_by(MatchPlayer.match_id)
    )
    counts: dict[uuid.UUID, int] = {}
    for match_id, cnt in result.all():
        counts[match_id] = int(cnt)
    return counts


async def _build_match_detail(
    match: Match,
    current_players: int,
    db: AsyncSession,
    participants: list[MatchPlayerResponse] | None = None,
) -> MatchDetailResponse:
    location = match.location_name or match.facility_address
    if participants is None:
        participants = await _fetch_match_participants(match.id, db)
    return MatchDetailResponse(
        id=match.id,
        title=match.title,
        description=match.description,
        sport=match.sport,
        skill_level=match.skill_level,
        status=match.status,
        scheduled_at=match.scheduled_at,
        duration_minutes=match.duration_minutes,
        scheduled_date=_format_scheduled_date(match.scheduled_at),
        scheduled_time=_format_scheduled_time(match.scheduled_at),
        facility_address=match.facility_address,
        location=location,
        latitude=match.latitude,
        longitude=match.longitude,
        max_players=match.max_players,
        current_players=current_players,
        host=UserSummaryResponse(
            id=match.host.id,
            full_name=match.host.full_name,
            avatar_url=match.host.avatar_url,
            avg_rating=match.host.avg_rating,
            total_games_played=match.host.total_games_played,
        ),
        host_games_played=match.host.total_games_played,
        participants=participants,
        created_at=match.created_at,
    )


# ─── Create Match ─────────────────────────────────────────────────────────────

async def create_match(
    payload: CreateMatchRequest,
    host: User,
    db: AsyncSession,
    background_tasks: BackgroundTasks,
) -> MatchDetailResponse:
    match = Match(
        host_id=host.id,
        sport=payload.sport,
        title=payload.title.strip(),
        description=payload.description.strip() if payload.description else None,
        facility_address=payload.facility_address.strip(),
        location_name=payload.location.strip() if payload.location else None,
        latitude=payload.latitude,
        longitude=payload.longitude,
        scheduled_at=payload.scheduled_at,
        duration_minutes=payload.duration_minutes,
        max_players=payload.max_players,
        skill_level=payload.skill_level,
        status=MatchStatus.OPEN,
    )
    db.add(match)
    await db.flush()

    host_player = MatchPlayer(
        match_id=match.id,
        user_id=host.id,
        role=MatchPlayerRole.HOST,
        status=MatchPlayerStatus.ACTIVE,
    )
    db.add(host_player)
    await db.commit()
    await db.refresh(match)

    result = await db.execute(
        select(Match)
        .options(selectinload(Match.host))
        .where(Match.id == match.id)
    )
    match = result.scalar_one()

    if match.latitude is None or match.longitude is None:
        background_tasks.add_task(
            geocode_match_address,
            match.id,
            match.facility_address,
        )

    logger.info(f"Match created: '{match.title}' (id={match.id}) by host={host.id}")

    host_participant = MatchPlayerResponse(
        user=UserSummaryResponse(
            id=match.host.id,
            full_name=match.host.full_name,
            avatar_url=match.host.avatar_url,
            avg_rating=match.host.avg_rating,
            total_games_played=match.host.total_games_played,
        ),
        role=MatchPlayerRole.HOST.value,
        joined_at=host_player.joined_at,
    )
    return await _build_match_detail(
        match, current_players=1, db=db, participants=[host_participant]
    )


# ─── Get Match by ID ──────────────────────────────────────────────────────────

async def get_match_by_id(
    match_id: uuid.UUID,
    db: AsyncSession,
) -> MatchDetailResponse:
    match = await _get_match_or_404(match_id, db)
    current_players = await _count_active_players(match_id, db)
    participants = await _fetch_match_participants(match_id, db)
    return await _build_match_detail(match, current_players, db, participants)


# ─── List Matches ─────────────────────────────────────────────────────────────

async def list_matches_by_type(
    list_type: str,
    current_user: User,
    sport: SportType | None,
    skill_level: SkillLevel | None,
    date_from: str | None,
    date_to: str | None,
    lat: float | None,
    lng: float | None,
    radius_km: int,
    pagination: PaginationParams,
    db: AsyncSession,
) -> PaginatedResponse:
    if list_type == "all":
        return await list_matches(
            sport=sport,
            skill_level=skill_level,
            date_from=date_from,
            date_to=date_to,
            pagination=pagination,
            db=db,
        )
    if list_type == "my":
        return await get_my_matches(
            current_user=current_user, pagination=pagination, db=db
        )
    if list_type == "nearby":
        if lat is None or lng is None:
            raise bad_request("lat and lng are required when type=nearby")
        return await get_nearby_matches(
            lat=lat,
            lng=lng,
            radius_km=radius_km,
            sport=sport,
            skill_level=skill_level,
            date_from=date_from,
            date_to=date_to,
            pagination=pagination,
            db=db,
        )
    raise bad_request("Invalid type. Use one of: all, my, nearby")


async def list_matches(
    sport: SportType | None,
    skill_level: SkillLevel | None,
    date_from: str | None,
    date_to: str | None,
    pagination: PaginationParams,
    db: AsyncSession,
) -> PaginatedResponse:
    query = (
        select(Match)
        .options(selectinload(Match.host))
        .where(Match.scheduled_at >= datetime.now(timezone.utc))
        .where(Match.status.in_([MatchStatus.OPEN, MatchStatus.FULL]))
        .order_by(Match.scheduled_at.asc())
    )
    if sport:
        query = query.where(Match.sport == sport)
    if skill_level:
        query = query.where(Match.skill_level == skill_level)
    if date_from:
        try:
            query = query.where(Match.scheduled_at >= _parse_iso_datetime(date_from))
        except ValueError:
            raise bad_request("Invalid date_from format.")
    if date_to:
        try:
            query = query.where(Match.scheduled_at <= _parse_iso_datetime(date_to))
        except ValueError:
            raise bad_request("Invalid date_to format.")

    paginated = await paginate(db, query, pagination)
    match_ids = [m.id for m in paginated.items]
    active_counts = await _count_active_players_for_match_ids(match_ids, db)

    paginated.items = [
        MatchSummaryResponse(
            id=m.id,
            title=m.title,
            sport=m.sport,
            skill_level=m.skill_level,
            status=m.status,
            scheduled_at=m.scheduled_at,
            duration_minutes=m.duration_minutes,
            scheduled_date=_format_scheduled_date(m.scheduled_at),
            scheduled_time=_format_scheduled_time(m.scheduled_at),
            location_name=m.location_name,
            location=m.location_name or m.facility_address,
            facility_address=m.facility_address,
            latitude=m.latitude,
            longitude=m.longitude,
            max_players=m.max_players,
            current_players=active_counts.get(m.id, 0),
            host=UserSummaryResponse(
                id=m.host.id,
                full_name=m.host.full_name,
                avatar_url=m.host.avatar_url,
                avg_rating=m.host.avg_rating,
            ),
        )
        for m in paginated.items
    ]
    return paginated


async def get_my_matches(
    current_user: User,
    pagination: PaginationParams,
    db: AsyncSession,
) -> PaginatedResponse:
    query = (
        select(Match)
        .options(selectinload(Match.host))
        .join(MatchPlayer, MatchPlayer.match_id == Match.id)
        .where(
            and_(
                MatchPlayer.user_id == current_user.id,
                MatchPlayer.status == MatchPlayerStatus.ACTIVE,
            )
        )
        .order_by(Match.scheduled_at.desc())
    )
    paginated = await paginate(db, query, pagination)
    match_ids = [m.id for m in paginated.items]
    active_counts = await _count_active_players_for_match_ids(match_ids, db)

    paginated.items = [
        MatchSummaryResponse(
            id=m.id,
            title=m.title,
            sport=m.sport,
            skill_level=m.skill_level,
            status=m.status,
            scheduled_at=m.scheduled_at,
            duration_minutes=m.duration_minutes,
            scheduled_date=_format_scheduled_date(m.scheduled_at),
            scheduled_time=_format_scheduled_time(m.scheduled_at),
            location_name=m.location_name,
            location=m.location_name or m.facility_address,
            facility_address=m.facility_address,
            latitude=m.latitude,
            longitude=m.longitude,
            max_players=m.max_players,
            current_players=active_counts.get(m.id, 0),
            host=UserSummaryResponse(
                id=m.host.id,
                full_name=m.host.full_name,
                avatar_url=m.host.avatar_url,
                avg_rating=m.host.avg_rating,
            ),
        )
        for m in paginated.items
    ]
    return paginated


# ─── Update Match ─────────────────────────────────────────────────────────────

async def update_match(
    match_id: uuid.UUID,
    payload: UpdateMatchRequest,
    current_user: User,
    db: AsyncSession,
    background_tasks: BackgroundTasks,
) -> MatchDetailResponse:
    match = await _get_match_or_404(match_id, db)

    if match.host_id != current_user.id:
        raise NotMatchHost()

    if match.status in [MatchStatus.ONGOING, MatchStatus.COMPLETED, MatchStatus.CANCELLED]:
        raise bad_request(f"Cannot edit a match with status '{match.status.value}'")

    address_changed = False

    if payload.title is not None:
        match.title = payload.title.strip()
    if payload.description is not None:
        match.description = payload.description.strip()
    if payload.sport is not None:
        match.sport = payload.sport
    if payload.scheduled_at is not None:
        match.scheduled_at = payload.scheduled_at
    if payload.duration_minutes is not None:
        match.duration_minutes = payload.duration_minutes
    if payload.skill_level is not None:
        match.skill_level = payload.skill_level
    if payload.max_players is not None:
        active_count = await _count_active_players(match_id, db)
        if payload.max_players < active_count:
            raise bad_request(
                f"Cannot set max_players to {payload.max_players} — "
                f"{active_count} players are already in the match."
            )
        match.max_players = payload.max_players
    if payload.facility_address is not None:
        match.facility_address = payload.facility_address.strip()
        address_changed = True
    if payload.location_name is not None:
        match.location_name = payload.location_name.strip() if payload.location_name else None
    if payload.latitude is not None and payload.longitude is not None:
        match.latitude = payload.latitude
        match.longitude = payload.longitude
        if payload.location_name is None and payload.facility_address is not None:
            match.location_name = payload.facility_address.strip()
        address_changed = False
    elif payload.facility_address is not None:
        match.latitude = None
        match.longitude = None
        if payload.location_name is None:
            match.location_name = None

    await db.commit()
    await db.refresh(match)

    if address_changed and match.latitude is None and match.longitude is None:
        background_tasks.add_task(
            geocode_match_address, match.id, match.facility_address
        )

    result = await db.execute(
        select(Match).options(selectinload(Match.host)).where(Match.id == match.id)
    )
    match = result.scalar_one()
    current_players = await _count_active_players(match_id, db)
    return await _build_match_detail(match, current_players, db)


# ─── Delete Match ─────────────────────────────────────────────────────────────

async def delete_match(
    match_id: uuid.UUID,
    current_user: User,
    db: AsyncSession,
) -> None:
    match = await _get_match_or_404(match_id, db)
    if match.host_id != current_user.id:
        raise NotMatchHost()
    await db.delete(match)
    await db.commit()
    logger.info(f"Match deleted: id={match_id} by host={current_user.id}")


# ─── Join Match ───────────────────────────────────────────────────────────────

async def join_match(
    match_id: uuid.UUID,
    current_user: User,
    db: AsyncSession,
    background_tasks: BackgroundTasks,
) -> MessageResponse:
    match = await _get_match_or_404(match_id, db)

    if match.status not in [MatchStatus.OPEN]:
        if match.status == MatchStatus.FULL:
            raise MatchFull()
        raise MatchNotOpen()

    existing = await db.execute(
        select(MatchPlayer).where(
            and_(
                MatchPlayer.match_id == match_id,
                MatchPlayer.user_id == current_user.id,
                MatchPlayer.status == MatchPlayerStatus.ACTIVE,
            )
        )
    )
    if existing.scalar_one_or_none():
        raise AlreadyJoined()

    active_count = await _count_active_players(match_id, db)
    if active_count >= match.max_players:
        raise MatchFull()

    player_record = MatchPlayer(
        match_id=match_id,
        user_id=current_user.id,
        role=MatchPlayerRole.PLAYER,
        status=MatchPlayerStatus.ACTIVE,
    )
    db.add(player_record)

    new_count = active_count + 1
    if new_count >= match.max_players:
        match.status = MatchStatus.FULL
        logger.info(f"Match {match_id} is now FULL ({new_count}/{match.max_players})")

    await db.commit()

    background_tasks.add_task(
        send_match_joined_notification,
        match_id,
        match.host_id,
        current_user.full_name,
    )

    logger.info(f"User {current_user.id} joined match {match_id}")
    return MessageResponse(message="You have successfully joined the match.")


# ─── Leave Match ──────────────────────────────────────────────────────────────

async def leave_match(
    match_id: uuid.UUID,
    current_user: User,
    db: AsyncSession,
) -> MessageResponse:
    match = await _get_match_or_404(match_id, db)

    if match.host_id == current_user.id:
        raise forbidden("As the host, you cannot leave. Delete the match instead.")

    if match.status in [MatchStatus.COMPLETED, MatchStatus.CANCELLED]:
        raise bad_request(f"Cannot leave a match with status '{match.status.value}'")

    result = await db.execute(
        select(MatchPlayer).where(
            and_(
                MatchPlayer.match_id == match_id,
                MatchPlayer.user_id == current_user.id,
                MatchPlayer.status == MatchPlayerStatus.ACTIVE,
            )
        )
    )
    player_record = result.scalar_one_or_none()
    if not player_record:
        raise bad_request("You are not an active participant in this match.")

    player_record.status = MatchPlayerStatus.LEFT

    if match.status == MatchStatus.FULL:
        match.status = MatchStatus.OPEN
        logger.info(f"Match {match_id} reopened (player left)")

    await db.commit()
    logger.info(f"User {current_user.id} left match {match_id}")
    return MessageResponse(message="You have left the match.")


# ─── Remove Player ────────────────────────────────────────────────────────────

async def remove_player(
    match_id: uuid.UUID,
    target_user_id: uuid.UUID,
    current_user: User,
    db: AsyncSession,
    background_tasks: BackgroundTasks,
) -> MessageResponse:
    match = await _get_match_or_404(match_id, db)

    if match.host_id != current_user.id:
        raise NotMatchHost()

    if target_user_id == current_user.id:
        raise bad_request("You cannot remove yourself. Delete the match instead.")

    if match.status in [MatchStatus.COMPLETED, MatchStatus.CANCELLED]:
        raise bad_request(f"Cannot remove players from a '{match.status.value}' match.")

    result = await db.execute(
        select(MatchPlayer).where(
            and_(
                MatchPlayer.match_id == match_id,
                MatchPlayer.user_id == target_user_id,
                MatchPlayer.status == MatchPlayerStatus.ACTIVE,
            )
        )
    )
    player_record = result.scalar_one_or_none()
    if not player_record:
        raise bad_request("This user is not an active participant in the match.")

    player_record.status = MatchPlayerStatus.REMOVED

    if match.status == MatchStatus.FULL:
        match.status = MatchStatus.OPEN
        logger.info(f"Match {match_id} reopened (player removed)")

    await db.commit()

    background_tasks.add_task(
        send_player_removed_notification,
        match_id,
        target_user_id,
    )

    logger.info(
        f"Host {current_user.id} removed player {target_user_id} from match {match_id}"
    )
    return MessageResponse(message="Player has been removed from the match.")


# ─── Update Match Status ──────────────────────────────────────────────────────

async def update_match_status(
    match_id: uuid.UUID,
    payload: MatchStatusUpdateRequest,
    current_user: User,
    db: AsyncSession,
    background_tasks: BackgroundTasks,
) -> MatchDetailResponse:
    match = await _get_match_or_404(match_id, db)

    if match.host_id != current_user.id:
        raise NotMatchHost()

    new_status = payload.status
    allowed = VALID_TRANSITIONS.get(match.status, [])

    if new_status not in allowed:
        raise bad_request(
            f"Cannot transition match from '{match.status.value}' to "
            f"'{new_status.value}'. "
            f"Allowed: {[s.value for s in allowed] or 'none'}"
        )

    match.status = new_status
    await db.commit()
    await db.refresh(match)

    if new_status == MatchStatus.ONGOING:
        players_result = await db.execute(
            select(MatchPlayer.user_id).where(
                and_(
                    MatchPlayer.match_id == match_id,
                    MatchPlayer.status == MatchPlayerStatus.ACTIVE,
                    MatchPlayer.user_id != current_user.id,
                )
            )
        )
        player_ids = [row[0] for row in players_result.fetchall()]
        if player_ids:
            background_tasks.add_task(
                send_match_started_notification, match_id, player_ids
            )
        logger.info(f"Match {match_id} STARTED by host {current_user.id}")

    elif new_status == MatchStatus.COMPLETED:
        players_result = await db.execute(
            select(MatchPlayer.user_id).where(
                and_(
                    MatchPlayer.match_id == match_id,
                    MatchPlayer.status == MatchPlayerStatus.ACTIVE,
                )
            )
        )
        all_player_ids = [row[0] for row in players_result.fetchall()]
        if all_player_ids:
            background_tasks.add_task(update_games_played, all_player_ids)
        logger.info(f"Match {match_id} COMPLETED by host {current_user.id}")

    elif new_status == MatchStatus.CANCELLED:
        logger.info(f"Match {match_id} CANCELLED by host {current_user.id}")

    result = await db.execute(
        select(Match).options(selectinload(Match.host)).where(Match.id == match_id)
    )
    match = result.scalar_one()
    current_players = await _count_active_players(match_id, db)
    return await _build_match_detail(match, current_players, db)


# ─── Invite Player ────────────────────────────────────────────────────────────

async def invite_player(
    match_id: uuid.UUID,
    invited_user_id: uuid.UUID,
    current_user: User,
    db: AsyncSession,
    background_tasks: BackgroundTasks,
) -> MessageResponse:
    """Invite a user to join the match. Host only."""
    from app.models.notification import Notification
    from app.websockets.connection_manager import ws_manager

    match = await _get_match_or_404(match_id, db)

    if match.host_id != current_user.id:
        raise NotMatchHost()

    if match.status not in [MatchStatus.OPEN, MatchStatus.FULL]:
        raise bad_request(
            f"Cannot invite players to a '{match.status.value}' match."
        )

    if invited_user_id == current_user.id:
        raise bad_request("You are already in this match as the host.")

    invited_result = await db.execute(
        select(User).where(User.id == invited_user_id)
    )
    invited_user = invited_result.scalar_one_or_none()
    if not invited_user:
        raise UserNotFound()

    existing_mp = await db.execute(
        select(MatchPlayer).where(
            and_(
                MatchPlayer.match_id == match_id,
                MatchPlayer.user_id == invited_user_id,
            )
        )
    )
    existing = existing_mp.scalar_one_or_none()
    if existing:
        if existing.status == MatchPlayerStatus.ACTIVE:
            raise conflict(f"{invited_user.full_name} is already in this match.")
        elif existing.status == MatchPlayerStatus.REMOVED:
            raise bad_request(
                f"{invited_user.full_name} was removed from this match "
                "and cannot be re-invited."
            )

    notification_payload = {
        "match_id":     str(match_id),
        "match_title":  match.title,
        "host_id":      str(current_user.id),
        "host_name":    current_user.full_name,
        "host_avatar":  current_user.avatar_url,
        "sport":        match.sport.value,
        "location":     match.location_name or match.facility_address,
        "scheduled_at": match.scheduled_at.isoformat(),
    }

    notification = Notification(
        user_id=invited_user_id,
        type=NotificationType.MATCH_INVITED,
        payload=notification_payload,
    )
    db.add(notification)
    await db.commit()

    try:
        await ws_manager.send_to_user(str(invited_user_id), {
            "type": "notification",
            "notification_type": NotificationType.MATCH_INVITED.value,
            "payload": notification_payload,
        })
    except Exception as e:
        logger.warning(
            f"Could not push invite notification to user {invited_user_id}: {e}"
        )

    logger.info(
        f"Host {current_user.id} invited user {invited_user_id} to match {match_id}"
    )
    return MessageResponse(message=f"Invitation sent to {invited_user.full_name}.")


# ─── Accept Invite ────────────────────────────────────────────────────────────

async def accept_invite(
    match_id: uuid.UUID,
    current_user: User,
    db: AsyncSession,
    background_tasks: BackgroundTasks,
) -> MessageResponse:
    """
    Accept a match invitation.
    Joins the match and notifies the host.
    """
    from app.models.notification import Notification
    from app.websockets.connection_manager import ws_manager

    match = await _get_match_or_404(match_id, db)

    # Match must still be joinable
    if match.status not in [MatchStatus.OPEN, MatchStatus.FULL]:
        raise bad_request(
            f"Cannot accept invite — match is '{match.status.value}'."
        )

    if match.status == MatchStatus.FULL:
        raise MatchFull()

    # Check user not already in match
    existing = await db.execute(
        select(MatchPlayer).where(
            and_(
                MatchPlayer.match_id == match_id,
                MatchPlayer.user_id == current_user.id,
                MatchPlayer.status == MatchPlayerStatus.ACTIVE,
            )
        )
    )
    if existing.scalar_one_or_none():
        raise AlreadyJoined()

    # Check capacity
    active_count = await _count_active_players(match_id, db)
    if active_count >= match.max_players:
        raise MatchFull()

    # Add player to match
    player_record = MatchPlayer(
        match_id=match_id,
        user_id=current_user.id,
        role=MatchPlayerRole.PLAYER,
        status=MatchPlayerStatus.ACTIVE,
    )
    db.add(player_record)

    # Auto-set to FULL if last slot filled
    new_count = active_count + 1
    if new_count >= match.max_players:
        match.status = MatchStatus.FULL
        logger.info(f"Match {match_id} is now FULL ({new_count}/{match.max_players})")

    # Notify host about acceptance
    notification_payload = {
        "match_id":    str(match_id),
        "match_title": match.title,
        "user_id":     str(current_user.id),
        "user_name":   current_user.full_name,
        "user_avatar": current_user.avatar_url,
    }

    notification = Notification(
        user_id=match.host_id,
        type=NotificationType.MATCH_INVITE_ACCEPTED,
        payload=notification_payload,
    )
    db.add(notification)
    await db.commit()

    # Push WebSocket notification to host
    try:
        await ws_manager.send_to_user(str(match.host_id), {
            "type": "notification",
            "notification_type": NotificationType.MATCH_INVITE_ACCEPTED.value,
            "payload": notification_payload,
        })
    except Exception as e:
        logger.warning(
            f"Could not push accept notification to host {match.host_id}: {e}"
        )

    logger.info(
        f"User {current_user.id} accepted invite to match {match_id}"
    )
    return MessageResponse(
        message="You have accepted the invitation and joined the match."
    )


# ─── Decline Invite ───────────────────────────────────────────────────────────

async def decline_invite(
    match_id: uuid.UUID,
    current_user: User,
    db: AsyncSession,
    background_tasks: BackgroundTasks,
) -> MessageResponse:
    """
    Decline a match invitation.
    Notifies the host that the invite was declined.
    """
    from app.models.notification import Notification
    from app.websockets.connection_manager import ws_manager

    match = await _get_match_or_404(match_id, db)

    # Notify host about decline
    notification_payload = {
        "match_id":    str(match_id),
        "match_title": match.title,
        "user_id":     str(current_user.id),
        "user_name":   current_user.full_name,
        "user_avatar": current_user.avatar_url,
    }

    notification = Notification(
        user_id=match.host_id,
        type=NotificationType.MATCH_INVITE_DECLINED,
        payload=notification_payload,
    )
    db.add(notification)
    await db.commit()

    # Push WebSocket notification to host
    try:
        await ws_manager.send_to_user(str(match.host_id), {
            "type": "notification",
            "notification_type": NotificationType.MATCH_INVITE_DECLINED.value,
            "payload": notification_payload,
        })
    except Exception as e:
        logger.warning(
            f"Could not push decline notification to host {match.host_id}: {e}"
        )

    logger.info(
        f"User {current_user.id} declined invite to match {match_id}"
    )
    return MessageResponse(message="You have declined the invitation.")


# ─── Get Nearby Matches ───────────────────────────────────────────────────────

async def get_nearby_matches(
    lat: float,
    lng: float,
    radius_km: int,
    sport: SportType | None,
    skill_level: SkillLevel | None,
    date_from: str | None,
    date_to: str | None,
    pagination: PaginationParams,
    db: AsyncSession,
) -> PaginatedResponse:
    now = datetime.now(timezone.utc)

    conditions = [
        Match.status.in_([MatchStatus.OPEN, MatchStatus.FULL]),
        Match.scheduled_at >= now,
        Match.latitude.isnot(None),
        Match.longitude.isnot(None),
    ]

    if sport:
        conditions.append(Match.sport == sport)
    if skill_level:
        conditions.append(Match.skill_level == skill_level)
    if date_from:
        try:
            conditions.append(Match.scheduled_at >= _parse_iso_datetime(date_from))
        except ValueError:
            raise bad_request("Invalid date_from format.")
    if date_to:
        try:
            conditions.append(Match.scheduled_at <= _parse_iso_datetime(date_to))
        except ValueError:
            raise bad_request("Invalid date_to format.")

    from app.utils.geocoding import build_bounding_box, haversine_distance_km
    bbox = build_bounding_box(lat, lng, radius_km)

    bbox_conditions = conditions + [
        Match.latitude.between(bbox.lat_min, bbox.lat_max),
        Match.longitude.between(bbox.lng_min, bbox.lng_max),
    ]

    candidate_query = (
        select(Match)
        .options(selectinload(Match.host))
        .where(and_(*bbox_conditions))
        .order_by(Match.scheduled_at.asc())
    )

    result = await db.execute(candidate_query)
    candidates = result.scalars().all()

    matches_with_distance: list[tuple[Match, float]] = []
    for match in candidates:
        if match.latitude is None or match.longitude is None:
            continue
        distance_km = haversine_distance_km(lat, lng, match.latitude, match.longitude)
        if distance_km <= radius_km:
            matches_with_distance.append((match, round(distance_km, 2)))

    matches_with_distance.sort(key=lambda x: x[1])

    total = len(matches_with_distance)
    start = pagination.skip
    end = start + pagination.limit
    page_items = matches_with_distance[start:end]

    page_match_ids = [m.id for m, _ in page_items]
    active_counts = await _count_active_players_for_match_ids(page_match_ids, db)

    items = [
        MatchSummaryResponse(
            id=m.id,
            title=m.title,
            sport=m.sport,
            skill_level=m.skill_level,
            status=m.status,
            scheduled_at=m.scheduled_at,
            duration_minutes=m.duration_minutes,
            scheduled_date=_format_scheduled_date(m.scheduled_at),
            scheduled_time=_format_scheduled_time(m.scheduled_at),
            location_name=m.location_name,
            location=m.location_name or m.facility_address,
            facility_address=m.facility_address,
            latitude=m.latitude,
            longitude=m.longitude,
            max_players=m.max_players,
            current_players=active_counts.get(m.id, 0),
            distance_km=d,
            host=UserSummaryResponse(
                id=m.host.id,
                full_name=m.host.full_name,
                avatar_url=m.host.avatar_url,
                avg_rating=m.host.avg_rating,
            ),
        )
        for m, d in page_items
    ]

    return PaginatedResponse(
        items=items,
        total=total,
        page=pagination.page,
        limit=pagination.limit,
        has_next=(end < total),
        has_prev=(pagination.page > 1),
    )

