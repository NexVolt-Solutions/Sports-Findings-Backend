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

# ─── ISO datetime parser (handles timezone-aware strings across Python 3.10+) ──

def _parse_iso_datetime(value: str) -> datetime:
    """
    Parse an ISO 8601 datetime string robustly.

    Python 3.10's datetime.fromisoformat() cannot parse "+00:00" timezone
    suffixes produced by JavaScript clients or Python's own .isoformat().
    Python 3.11+ fixed this, but we support 3.10+.

    Handles:
        "2025-06-01T14:00:00"           → naive datetime (assumed UTC)
        "2025-06-01T14:00:00Z"          → UTC
        "2025-06-01T14:00:00+00:00"     → UTC
        "2025-06-01T14:00:00+05:30"     → timezone-aware
    """
    value = value.strip()

    # Replace trailing Z with +00:00 for uniform handling
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"

    try:
        # Python 3.11+ handles this natively
        dt = datetime.fromisoformat(value)
    except ValueError:
        # Python 3.10 fallback: strip timezone offset manually
        # e.g. "2025-06-01T14:00:00+00:00" → "2025-06-01T14:00:00"
        import re
        value_stripped = re.sub(r"[+-]\d{2}:\d{2}$", "", value)
        dt = datetime.fromisoformat(value_stripped)
        dt = dt.replace(tzinfo=timezone.utc)

    # Ensure timezone-aware (assume UTC if naive)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt


# ─── Valid match status transitions ──────────────────────────────────────────
VALID_TRANSITIONS: dict[MatchStatus, list[MatchStatus]] = {
    MatchStatus.OPEN:      [MatchStatus.ONGOING, MatchStatus.CANCELLED],
    MatchStatus.FULL:      [MatchStatus.ONGOING, MatchStatus.CANCELLED],
    MatchStatus.ONGOING:   [MatchStatus.COMPLETED],
    MatchStatus.COMPLETED: [],
    MatchStatus.CANCELLED: [],
}


# ─── Internal helpers ─────────────────────────────────────────────────────────

async def _get_match_or_404(match_id: uuid.UUID, db: AsyncSession) -> Match:
    """Fetch a match by ID with host eagerly loaded. Raises 404 if not found."""
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
    """Returns the number of active (not left/removed) players in a match."""
    result = await db.execute(
        select(func.count()).where(
            and_(
                MatchPlayer.match_id == match_id,
                MatchPlayer.status == MatchPlayerStatus.ACTIVE,
            )
        )
    )
    return result.scalar_one()


async def _count_active_players_for_match_ids(
    match_ids: list[uuid.UUID],
    db: AsyncSession,
) -> dict[uuid.UUID, int]:
    """
    Batch-count active players for many matches at once.

    This avoids the N+1 query pattern where we previously counted per match
    inside list loops.
    """
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

    # result rows are tuples: (match_id, count)
    counts: dict[uuid.UUID, int] = {}
    for match_id, cnt in result.all():
        counts[match_id] = int(cnt)
    return counts


def _build_match_detail(match: Match, current_players: int) -> MatchDetailResponse:
    """Builds a MatchDetailResponse from a Match ORM object."""
    return MatchDetailResponse(
        id=match.id,
        title=match.title,
        description=match.description,
        sport=match.sport,
        skill_level=match.skill_level,
        status=match.status,
        scheduled_at=match.scheduled_at,
        duration_minutes=match.duration_minutes,
        facility_address=match.facility_address,
        location_name=match.location_name,
        latitude=match.latitude,
        longitude=match.longitude,
        max_players=match.max_players,
        current_players=current_players,
        host=UserSummaryResponse(
            id=match.host.id,
            full_name=match.host.full_name,
            avatar_url=match.host.avatar_url,
            avg_rating=match.host.avg_rating,
        ),
        created_at=match.created_at,
    )


# ─── Create Match ─────────────────────────────────────────────────────────────

async def create_match(
    payload: CreateMatchRequest,
    host: User,
    db: AsyncSession,
    background_tasks: BackgroundTasks,
) -> MatchDetailResponse:
    """
    Create a new match and auto-join the host as a participant.

    - Match starts with status OPEN
    - Host is automatically added as MatchPlayer with role=Host
    - Address geocoding is queued as a background task
    - Match immediately appears in host's My Matches
    """
    # 1. Create Match record
    match = Match(
        host_id=host.id,
        sport=payload.sport,
        title=payload.title.strip(),
        description=payload.description.strip() if payload.description else None,
        facility_address=payload.facility_address.strip(),
        scheduled_at=payload.scheduled_at,
        duration_minutes=payload.duration_minutes,
        max_players=payload.max_players,
        skill_level=payload.skill_level,
        status=MatchStatus.OPEN,
    )
    db.add(match)
    await db.flush()  # Get match.id before creating MatchPlayer

    # 2. Auto-join host as participant with role=Host
    host_player = MatchPlayer(
        match_id=match.id,
        user_id=host.id,
        role=MatchPlayerRole.HOST,
        status=MatchPlayerStatus.ACTIVE,
    )
    db.add(host_player)

    await db.commit()
    await db.refresh(match)

    # 3. Reload match with host relationship
    result = await db.execute(
        select(Match)
        .options(selectinload(Match.host))
        .where(Match.id == match.id)
    )
    match = result.scalar_one()

    # 4. Queue geocoding as background task (non-blocking)
    background_tasks.add_task(
        geocode_match_address,
        match.id,
        match.facility_address,
    )

    logger.info(f"Match created: '{match.title}' (id={match.id}) by host={host.id}")

    # Host counts as 1 active player
    return _build_match_detail(match, current_players=1)


# ─── Get Match by ID ──────────────────────────────────────────────────────────

async def get_match_by_id(
    match_id: uuid.UUID,
    db: AsyncSession,
) -> MatchDetailResponse:
    """Fetch full details of a single match including current player count."""
    match = await _get_match_or_404(match_id, db)
    current_players = await _count_active_players(match_id, db)
    return _build_match_detail(match, current_players)


# ─── List Matches ─────────────────────────────────────────────────────────────

async def list_matches(
    sport: SportType | None,
    skill_level: SkillLevel | None,
    date_from: str | None,
    date_to: str | None,
    pagination: PaginationParams,
    db: AsyncSession,
) -> PaginatedResponse:
    """
    List matches with optional filters.
    Only returns OPEN and FULL matches scheduled in the future.
    """
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
            dt_from = _parse_iso_datetime(date_from)
            query = query.where(Match.scheduled_at >= dt_from)
        except ValueError:
            raise bad_request("Invalid date_from format. Use ISO 8601 (e.g. 2025-06-01T00:00:00).")
    if date_to:
        try:
            dt_to = _parse_iso_datetime(date_to)
            query = query.where(Match.scheduled_at <= dt_to)
        except ValueError:
            raise bad_request("Invalid date_to format. Use ISO 8601 (e.g. 2025-06-30T23:59:59).")

    paginated = await paginate(db, query, pagination)

    # Build summary responses with current player counts
    match_ids = [m.id for m in paginated.items]
    active_counts = await _count_active_players_for_match_ids(match_ids, db)

    items = []
    for match in paginated.items:
        count = active_counts.get(match.id, 0)
        items.append(MatchSummaryResponse(
            id=match.id,
            title=match.title,
            sport=match.sport,
            skill_level=match.skill_level,
            status=match.status,
            scheduled_at=match.scheduled_at,
            duration_minutes=match.duration_minutes,
            location_name=match.location_name,
            facility_address=match.facility_address,
            latitude=match.latitude,
            longitude=match.longitude,
            max_players=match.max_players,
            current_players=count,
            host=UserSummaryResponse(
                id=match.host.id,
                full_name=match.host.full_name,
                avatar_url=match.host.avatar_url,
                avg_rating=match.host.avg_rating,
            ),
        ))

    paginated.items = items
    return paginated


# ─── Get My Matches ───────────────────────────────────────────────────────────

async def get_my_matches(
    current_user: User,
    pagination: PaginationParams,
    db: AsyncSession,
) -> PaginatedResponse:
    """
    Get all matches the current user is participating in (as host or player).
    Sorted by scheduled_at descending (newest first).
    """
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

    items = []
    for match in paginated.items:
        count = active_counts.get(match.id, 0)
        items.append(MatchSummaryResponse(
            id=match.id,
            title=match.title,
            sport=match.sport,
            skill_level=match.skill_level,
            status=match.status,
            scheduled_at=match.scheduled_at,
            duration_minutes=match.duration_minutes,
            location_name=match.location_name,
            facility_address=match.facility_address,
            latitude=match.latitude,
            longitude=match.longitude,
            max_players=match.max_players,
            current_players=count,
            host=UserSummaryResponse(
                id=match.host.id,
                full_name=match.host.full_name,
                avatar_url=match.host.avatar_url,
                avg_rating=match.host.avg_rating,
            ),
        ))

    paginated.items = items
    return paginated


# ─── Update Match ─────────────────────────────────────────────────────────────

async def update_match(
    match_id: uuid.UUID,
    payload: UpdateMatchRequest,
    current_user: User,
    db: AsyncSession,
    background_tasks: BackgroundTasks,
) -> MatchDetailResponse:
    """
    Update match details. Host only.
    Only provided (non-None) fields are updated.
    If facility_address changes, geocoding is re-queued.
    """
    match = await _get_match_or_404(match_id, db)

    if match.host_id != current_user.id:
        raise NotMatchHost()

    # Cannot edit a match that is already ongoing, completed or cancelled
    if match.status in [MatchStatus.ONGOING, MatchStatus.COMPLETED, MatchStatus.CANCELLED]:
        raise bad_request(f"Cannot edit a match with status '{match.status.value}'")

    address_changed = False

    if payload.title is not None:
        match.title = payload.title.strip()
    if payload.description is not None:
        match.description = payload.description.strip()
    if payload.scheduled_at is not None:
        match.scheduled_at = payload.scheduled_at
    if payload.duration_minutes is not None:
        match.duration_minutes = payload.duration_minutes
    if payload.skill_level is not None:
        match.skill_level = payload.skill_level
    if payload.max_players is not None:
        # New limit cannot be less than current active player count
        active_count = await _count_active_players(match_id, db)
        if payload.max_players < active_count:
            raise bad_request(
                f"Cannot set max_players to {payload.max_players} — "
                f"{active_count} players are already in the match."
            )
        match.max_players = payload.max_players
    if payload.facility_address is not None:
        match.facility_address = payload.facility_address.strip()
        match.latitude = None
        match.longitude = None
        match.location_name = None
        address_changed = True

    await db.commit()
    await db.refresh(match)

    if address_changed:
        background_tasks.add_task(geocode_match_address, match.id, match.facility_address)

    result = await db.execute(
        select(Match).options(selectinload(Match.host)).where(Match.id == match.id)
    )
    match = result.scalar_one()
    current_players = await _count_active_players(match_id, db)
    return _build_match_detail(match, current_players)


# ─── Delete Match ─────────────────────────────────────────────────────────────

async def delete_match(
    match_id: uuid.UUID,
    current_user: User,
    db: AsyncSession,
) -> None:
    """
    Permanently delete a match. Host only.
    Cascade deletes all MatchPlayer, Message, and Review records.
    """
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
    """
    Join an open match.

    Rules:
    - Match must be OPEN (not FULL, ONGOING, COMPLETED, or CANCELLED)
    - User must not already be an active participant
    - Active player count must be below max_players
    - If joining fills the match → status auto-set to FULL
    - Notifies the host via background task
    """
    match = await _get_match_or_404(match_id, db)

    # 1. Check status allows joining
    if match.status not in [MatchStatus.OPEN]:
        if match.status == MatchStatus.FULL:
            raise MatchFull()
        raise MatchNotOpen()

    # 2. Check user not already an active participant
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

    # 3. Check capacity
    active_count = await _count_active_players(match_id, db)
    if active_count >= match.max_players:
        raise MatchFull()

    # 4. Add player to match
    player_record = MatchPlayer(
        match_id=match_id,
        user_id=current_user.id,
        role=MatchPlayerRole.PLAYER,
        status=MatchPlayerStatus.ACTIVE,
    )
    db.add(player_record)

    # 5. Auto-set to FULL if this player fills the last slot
    new_count = active_count + 1
    if new_count >= match.max_players:
        match.status = MatchStatus.FULL
        logger.info(f"Match {match_id} is now FULL ({new_count}/{match.max_players})")

    await db.commit()

    # 6. Notify host in background
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
    """
    Leave a match.

    Rules:
    - Host cannot leave — must delete the match instead
    - Player must be an active participant
    - If match was FULL, leaving reopens a slot → status → OPEN
    """
    match = await _get_match_or_404(match_id, db)

    # 1. Host cannot leave
    if match.host_id == current_user.id:
        raise forbidden("As the host, you cannot leave. Delete the match instead.")

    # 2. Cannot leave a match that is COMPLETED or CANCELLED
    if match.status in [MatchStatus.COMPLETED, MatchStatus.CANCELLED]:
        raise bad_request(f"Cannot leave a match with status '{match.status.value}'")

    # 3. Find active player record
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

    # 4. Mark as LEFT
    player_record.status = MatchPlayerStatus.LEFT

    # 5. Reopen slot if match was FULL
    if match.status == MatchStatus.FULL:
        match.status = MatchStatus.OPEN
        logger.info(f"Match {match_id} reopened (player left, slot available)")

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
    """
    Remove a player from the match. Host only.

    Rules:
    - Host cannot remove themselves
    - Target must be an active participant
    - If match was FULL, removal reopens a slot → status → OPEN
    - Removed player receives a PLAYER_REMOVED notification
    """
    match = await _get_match_or_404(match_id, db)

    # 1. Must be host
    if match.host_id != current_user.id:
        raise NotMatchHost()

    # 2. Cannot remove self
    if target_user_id == current_user.id:
        raise bad_request("You cannot remove yourself. Delete the match instead.")

    # 3. Cannot remove from completed/cancelled match
    if match.status in [MatchStatus.COMPLETED, MatchStatus.CANCELLED]:
        raise bad_request(f"Cannot remove players from a '{match.status.value}' match.")

    # 4. Find target player record
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

    # 5. Mark as REMOVED
    player_record.status = MatchPlayerStatus.REMOVED

    # 6. Reopen slot if match was FULL
    if match.status == MatchStatus.FULL:
        match.status = MatchStatus.OPEN
        logger.info(f"Match {match_id} reopened (player removed, slot available)")

    await db.commit()

    # 7. Notify the removed player in background
    background_tasks.add_task(
        send_player_removed_notification,
        match_id,
        target_user_id,
    )

    logger.info(f"Host {current_user.id} removed player {target_user_id} from match {match_id}")
    return MessageResponse(message="Player has been removed from the match.")


# ─── Update Match Status (Start Game / Complete / Cancel) ─────────────────────

async def update_match_status(
    match_id: uuid.UUID,
    payload: MatchStatusUpdateRequest,
    current_user: User,
    db: AsyncSession,
    background_tasks: BackgroundTasks,
) -> MatchDetailResponse:
    """
    Update match status. Host only.

    Valid transitions:
      OPEN | FULL  → ONGOING    (Start Game — slots NOT required to be full)
      ONGOING      → COMPLETED
      OPEN | FULL  → CANCELLED

    Key rule: Host can start the game at ANY time regardless of how many
    slots are filled. The player limit is a maximum capacity, not a
    start requirement.
    """
    match = await _get_match_or_404(match_id, db)

    # 1. Must be host
    if match.host_id != current_user.id:
        raise NotMatchHost()

    new_status = payload.status
    allowed = VALID_TRANSITIONS.get(match.status, [])

    # 2. Validate the transition is allowed
    if new_status not in allowed:
        raise bad_request(
            f"Cannot transition match from '{match.status.value}' to '{new_status.value}'. "
            f"Allowed transitions: {[s.value for s in allowed] or 'none'}"
        )

    # 3. Apply new status
    match.status = new_status
    await db.commit()
    await db.refresh(match)

    # 4. Trigger background tasks based on new status
    if new_status == MatchStatus.ONGOING:
        # Notify all active players that the match has started
        players_result = await db.execute(
            select(MatchPlayer.user_id).where(
                and_(
                    MatchPlayer.match_id == match_id,
                    MatchPlayer.status == MatchPlayerStatus.ACTIVE,
                    MatchPlayer.user_id != current_user.id,  # Skip host
                )
            )
        )
        player_ids = [row[0] for row in players_result.fetchall()]
        if player_ids:
            background_tasks.add_task(
                send_match_started_notification,
                match_id,
                player_ids,
            )
        logger.info(f"Match {match_id} STARTED by host {current_user.id}")

    elif new_status == MatchStatus.COMPLETED:
        # Increment games_played for all active participants
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

    # 5. Reload with host relationship and return
    result = await db.execute(
        select(Match).options(selectinload(Match.host)).where(Match.id == match_id)
    )
    match = result.scalar_one()
    current_players = await _count_active_players(match_id, db)
    return _build_match_detail(match, current_players)


# ─── Get Match Players ────────────────────────────────────────────────────────

async def get_match_players(
    match_id: uuid.UUID,
    pagination: PaginationParams,
    db: AsyncSession,
) -> PaginatedResponse:
    """
    Get paginated list of active participants in a match.
    Host is always included (role=Host). Sorted by joined_at ascending.
    """
    # Verify match exists
    await _get_match_or_404(match_id, db)

    query = (
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

    paginated = await paginate(db, query, pagination)

    items = [
        MatchPlayerResponse(
            user=UserSummaryResponse(
                id=mp.user.id,
                full_name=mp.user.full_name,
                avatar_url=mp.user.avatar_url,
                avg_rating=mp.user.avg_rating,
            ),
            role=mp.role.value,
            joined_at=mp.joined_at,
        )
        for mp in paginated.items
    ]

    paginated.items = items
    return paginated


# ─── Get Nearby Matches (Phase 3) ─────────────────────────────────────────────

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
    """
    Discover nearby matches using the Haversine formula.

    Haversine formula calculates the great-circle distance between two
    points on Earth given their latitude/longitude coordinates.

    Formula:
        a = sin²(Δlat/2) + cos(lat1) * cos(lat2) * sin²(Δlng/2)
        distance_km = 2 * R * asin(√a)   where R = 6371 km

    Filters applied (all optional, with documented defaults):
        - sport:       defaults to the sport the user is browsing (passed by client)
        - radius_km:   default 20 km
        - skill_level: default Any (no filter)
        - date_from:   default None (all upcoming matches)
        - date_to:     default None (no upper date limit)

    Results:
        - Only OPEN and FULL matches
        - Only future matches (scheduled_at >= now)
        - Sorted by distance ASC (closest first)
        - Matches with no coordinates yet (geocoding pending) are excluded
    """
    now = datetime.now(timezone.utc)

    # ── Build base filter conditions ──────────────────────────────────────────
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
            dt_from = _parse_iso_datetime(date_from)
            conditions.append(Match.scheduled_at >= dt_from)
        except ValueError:
            raise bad_request("Invalid date_from format. Use ISO 8601 (e.g. 2025-06-01T00:00:00).")

    if date_to:
        try:
            dt_to = _parse_iso_datetime(date_to)
            conditions.append(Match.scheduled_at <= dt_to)
        except ValueError:
            raise bad_request("Invalid date_to format. Use ISO 8601 (e.g. 2025-06-30T23:59:59).")

    # Distance filtering is done in Python using Haversine after the
    # bounding-box pre-filter. No PostGIS extension required.

        # ── Bounding box pre-filter (fast index scan before trig) ───────────────
    from app.utils.geocoding import build_bounding_box, haversine_distance_km
    import math
    bbox = build_bounding_box(lat, lng, radius_km)

    bbox_conditions = conditions + [
        Match.latitude.between(bbox.lat_min, bbox.lat_max),
        Match.longitude.between(bbox.lng_min, bbox.lng_max),
    ]

    # ── Fetch candidates within bounding box ─────────────────────────────────
    candidate_query = (
        select(Match)
        .options(selectinload(Match.host))
        .where(and_(*bbox_conditions))
        .order_by(Match.scheduled_at.asc())
    )

    result = await db.execute(candidate_query)
    candidates = result.scalars().all()

    # ── Apply exact Haversine filter and compute distances ────────────────────
    matches_with_distance: list[tuple[Match, float]] = []

    for match in candidates:
        if match.latitude is None or match.longitude is None:
            continue

        # Exact Haversine distance using shared utility function
        distance_km = haversine_distance_km(lat, lng, match.latitude, match.longitude)

        if distance_km <= radius_km:
            matches_with_distance.append((match, round(distance_km, 2)))

    # ── Sort by distance ascending ────────────────────────────────────────────
    matches_with_distance.sort(key=lambda x: x[1])

    # ── Apply pagination manually ─────────────────────────────────────────────
    total = len(matches_with_distance)
    start = pagination.skip
    end = start + pagination.limit
    page_items = matches_with_distance[start:end]

    # ── Build response items with player counts ───────────────────────────────
    page_match_ids = [match.id for match, _ in page_items]
    active_counts = await _count_active_players_for_match_ids(page_match_ids, db)

    items = []
    for match, distance_km in page_items:
        count = active_counts.get(match.id, 0)
        items.append(
            MatchSummaryResponse(
                id=match.id,
                title=match.title,
                sport=match.sport,
                skill_level=match.skill_level,
                status=match.status,
                scheduled_at=match.scheduled_at,
                duration_minutes=match.duration_minutes,
                location_name=match.location_name,
                facility_address=match.facility_address,
                latitude=match.latitude,
                longitude=match.longitude,
                max_players=match.max_players,
                current_players=count,
                distance_km=distance_km,
                host=UserSummaryResponse(
                    id=match.host.id,
                    full_name=match.host.full_name,
                    avatar_url=match.host.avatar_url,
                    avg_rating=match.host.avg_rating,
                ),
            )
        )

    return PaginatedResponse(
        items=items,
        total=total,
        page=pagination.page,
        limit=pagination.limit,
        has_next=(end < total),
        has_prev=(pagination.page > 1),
    )


# ─── Invite Player ────────────────────────────────────────────────────────────

async def invite_player(
    match_id: uuid.UUID,
    invited_user_id: uuid.UUID,
    current_user: User,
    db: AsyncSession,
) -> MessageResponse:
    """
    Invite a registered user to join a match. Host only.

    Rules:
    - Only the host can invite players
    - Match must be OPEN or FULL (cannot invite to ONGOING/COMPLETED/CANCELLED)
    - Cannot invite yourself (host is already in the match)
    - Cannot invite someone already in the match
    - Cannot invite someone who was removed from the match
    - Sends a MATCH_INVITED notification to the invited user
    """
    from app.models.user import User as UserModel
    from app.models.notification import Notification
    from app.models.enums import NotificationType, MatchPlayerStatus
    from app.websockets.connection_manager import ws_manager

    # 1. Fetch and validate match
    match = await _get_match_or_404(match_id, db)

    if match.host_id != current_user.id:
        raise NotMatchHost()

    if match.status not in [MatchStatus.OPEN, MatchStatus.FULL]:
        raise bad_request(
            f"Cannot invite players to a '{match.status.value}' match."
        )

    # 2. Cannot invite yourself
    if invited_user_id == current_user.id:
        raise bad_request("You are already in this match as the host.")

    # 3. Verify the invited user exists
    invited_result = await db.execute(
        select(UserModel).where(UserModel.id == invited_user_id)
    )
    invited_user = invited_result.scalar_one_or_none()
    if not invited_user:
        raise UserNotFound()

    # 4. Check if user is already an active participant
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
                f"{invited_user.full_name} was removed from this match and cannot be re-invited."
            )

    # 5. Build notification payload
    notification_payload = {
        "match_id":    str(match_id),
        "match_title": match.title,
        "host_name":   current_user.full_name,
        "sport":       match.sport.value,
        "scheduled_at": match.scheduled_at.isoformat(),
    }

    # 6. Create DB notification record
    notification = Notification(
        user_id=invited_user_id,
        type=NotificationType.MATCH_INVITED,
        payload=notification_payload,
    )
    db.add(notification)
    await db.commit()

    # 7. Push via WebSocket if user is online (best-effort, never raises)
    try:
        await ws_manager.send_to_user(str(invited_user_id), {
            "type":              "notification",
            "notification_type": NotificationType.MATCH_INVITED.value,
            "payload":           notification_payload,
        })
    except Exception as e:
        logger.warning(f"Could not push invite notification to user {invited_user_id}: {e}")

    logger.info(
        f"Host {current_user.id} invited user {invited_user_id} "
        f"to match {match_id}"
    )

    return MessageResponse(
        message=f"Invitation sent to {invited_user.full_name}."
    )
