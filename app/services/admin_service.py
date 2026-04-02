import calendar
import logging
import re
import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, func, and_, or_, extract, cast, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.content_page import ContentPage
from app.models.enums import (
    MatchPlayerStatus,
    MatchStatus,
    SportType,
    SupportRequestStatus,
    UserStatus,
)
from app.models.match import Match
from app.models.match_player import MatchPlayer
from app.models.review import Review
from app.models.support_request import SupportRequest
from app.models.user import User, UserSport
from app.schemas.admin import (
    AdminAccountResponse,
    AdminMatchListItemResponse,
    AdminUserDetailResponse,
    AdminUserListItemResponse,
    ContentPageResponse,
    CreateUserRequest,
    DailyMatchCount,
    DashboardStatsResponse,
    MonthlyUserCount,
    ReviewModerationReviewItemResponse,
    ReviewModerationUserItemResponse,
    ReviewModerationUserReviewsResponse,
    SportDistribution,
    SupportRequestDetailResponse,
    SupportRequestListItemResponse,
    UpdateAdminAccountRequest,
    UpdateContentPageRequest,
)
from app.schemas.common import MessageResponse, PaginatedResponse
from app.schemas.match import MatchDetailResponse, UpdateMatchRequest
from app.schemas.user import UserSummaryResponse
from app.utils.exceptions import MatchNotFound, UserNotFound, bad_request, conflict, forbidden, not_found
from app.utils.pagination import PaginationParams, paginate
from app.utils.security import hash_password, verify_password

logger = logging.getLogger(__name__)

CONTENT_SECTIONS = {
    "terms-of-service": "Terms of Service",
    "privacy-policy": "Privacy Policy",
    "help-support": "Help & Support",
}


def _map_user_status_for_ui(status: UserStatus) -> str:
    if status == UserStatus.ACTIVE:
        return "Active"
    if status == UserStatus.BLOCKED:
        return "Suspended"
    return "Inactive"


def _parse_ui_user_status(status: str) -> UserStatus | None:
    normalized = status.strip().lower()
    if normalized == "all":
        return None
    if normalized == "active":
        return UserStatus.ACTIVE
    if normalized == "inactive":
        return UserStatus.PENDING_VERIFICATION
    if normalized == "suspended":
        return UserStatus.BLOCKED
    raise bad_request("Invalid status. Valid values: All, Active, Inactive, Suspended")


def _parse_datetime(value: str, field_name: str) -> datetime:
    try:
        dt = datetime.fromisoformat(value)
    except ValueError as exc:
        raise bad_request(f"Invalid {field_name} format. Use ISO 8601.") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _validate_content_section(section: str) -> str:
    if section not in CONTENT_SECTIONS:
        raise bad_request(
            f"Invalid content section '{section}'. Valid values: {list(CONTENT_SECTIONS)}"
        )
    return section


def _build_match_detail_response(match: Match, current_players: int) -> MatchDetailResponse:
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


async def get_dashboard_stats(db: AsyncSession) -> DashboardStatsResponse:
    now = datetime.now(timezone.utc)
    last_24_hours = now - timedelta(hours=24)
    year_start = datetime(now.year, 1, 1, tzinfo=timezone.utc)
    year_end = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)

    total_users = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    new_users_today = (await db.execute(
        select(func.count()).where(User.created_at >= last_24_hours)
    )).scalar_one()
    total_matches = (await db.execute(
        select(func.count()).where(Match.status == MatchStatus.COMPLETED)
    )).scalar_one()
    active_matches = (await db.execute(
        select(func.count()).where(Match.status.in_([MatchStatus.OPEN, MatchStatus.FULL]))
    )).scalar_one()

    monthly_users_result = await db.execute(
        select(extract("month", User.created_at).label("month"), func.count().label("count"))
        .where(User.created_at >= year_start, User.created_at < year_end)
        .group_by(extract("month", User.created_at))
    )
    monthly_map = {int(row.month): row.count for row in monthly_users_result.fetchall()}
    total_users_by_month = [
        MonthlyUserCount(month=calendar.month_abbr[month].upper(), count=monthly_map.get(month, 0))
        for month in range(1, 13)
    ]

    completed_matches_by_day_result = await db.execute(
        select(extract("dow", Match.scheduled_at).label("day"), func.count().label("count"))
        .where(Match.status == MatchStatus.COMPLETED)
        .group_by(extract("dow", Match.scheduled_at))
    )
    day_map = {int(row.day): row.count for row in completed_matches_by_day_result.fetchall()}
    day_order = [("Mon", 1), ("Tue", 2), ("Wed", 3), ("Thu", 4), ("Fri", 5), ("Sat", 6), ("Sun", 0)]
    matches_per_day = [
        DailyMatchCount(day=label, count=day_map.get(index, 0))
        for label, index in day_order
    ]

    sport_counts_result = await db.execute(
        select(Match.sport, func.count().label("count"))
        .where(Match.status == MatchStatus.COMPLETED)
        .group_by(Match.sport)
    )
    sport_counts = {row.sport: row.count for row in sport_counts_result.fetchall()}
    denominator = total_matches or 1
    most_popular_sports = [
        SportDistribution(
            sport=sport,
            count=sport_counts[sport],
            percentage=round((sport_counts[sport] / denominator) * 100, 2) if total_matches else 0.0,
        )
        for sport in SportType
        if sport in sport_counts
    ]
    most_popular_sports.sort(key=lambda item: item.count, reverse=True)

    return DashboardStatsResponse(
        generated_at=now,
        total_users=total_users,
        total_matches=total_matches,
        active_matches=active_matches,
        new_users_today=new_users_today,
        total_users_by_month=total_users_by_month,
        matches_per_day=matches_per_day,
        most_popular_sports=most_popular_sports,
    )


async def list_users(
    search: str | None,
    status: str | None,
    sport: str | None,
    date_from: str | None,
    date_to: str | None,
    location: str | None,
    pagination: PaginationParams,
    db: AsyncSession,
) -> PaginatedResponse:
    # Admin dashboard "Users" list is for end users only (exclude admin accounts).
    query = select(User).where(User.is_admin.is_(False)).order_by(User.created_at.desc())

    if search:
        term = f"%{search.lower()}%"
        query = query.where(
            or_(
                func.lower(User.full_name).like(term),
                func.lower(User.email).like(term),
                func.lower(func.coalesce(User.location, "")).like(term),
            )
        )

    if location:
        term = f"%{location.lower()}%"
        query = query.where(func.lower(func.coalesce(User.location, "")).like(term))

    if status:
        mapped_status = _parse_ui_user_status(status)
        if mapped_status is not None:
            query = query.where(User.status == mapped_status)

    if sport:
        try:
            sport_enum = SportType(sport)
        except ValueError as exc:
            raise bad_request(
                f"Invalid sport '{sport}'. Valid values: {[value.value for value in SportType]}"
            ) from exc
        query = query.join(UserSport).where(UserSport.sport == sport_enum)

    if date_from:
        query = query.where(User.created_at >= _parse_datetime(date_from, "date_from"))
    if date_to:
        query = query.where(User.created_at <= _parse_datetime(date_to, "date_to"))

    paginated = await paginate(db, query, pagination)
    paginated.items = [
        AdminUserListItemResponse(
            id=user.id,
            full_name=user.full_name,
            email=user.email,
            location=user.location,
            matches=user.total_games_played,
            status=_map_user_status_for_ui(user.status),
        )
        for user in paginated.items
    ]
    return paginated


async def create_user(payload: CreateUserRequest, db: AsyncSession) -> AdminUserDetailResponse:
    existing = (await db.execute(
        select(User).where(func.lower(User.email) == payload.email.lower())
    )).scalar_one_or_none()
    if existing:
        raise conflict(f"A user with email '{payload.email}' already exists.")

    if payload.is_admin:
        existing_admin = (await db.execute(
            select(User).where(User.is_admin.is_(True))
        )).scalar_one_or_none()
        if existing_admin:
            raise conflict("Only one admin account is allowed.")

    user = User(
        full_name=payload.full_name,
        email=payload.email.lower(),
        hashed_password=hash_password(payload.password),
        status=UserStatus.ACTIVE,
        is_admin=payload.is_admin,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return AdminUserDetailResponse(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        phone=user.phone_number,
        location=user.location,
        status=_map_user_status_for_ui(user.status),
        matches=user.total_games_played,
    )


async def get_user(user_id: uuid.UUID, db: AsyncSession) -> AdminUserDetailResponse:
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise UserNotFound()
    return AdminUserDetailResponse(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        phone=user.phone_number,
        location=user.location,
        status=_map_user_status_for_ui(user.status),
        matches=user.total_games_played,
    )


async def block_user(user_id: uuid.UUID, admin: User, db: AsyncSession) -> MessageResponse:
    if user_id == admin.id:
        raise bad_request("You cannot block your own admin account.")
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise UserNotFound()
    if user.is_admin:
        raise forbidden("Admin accounts cannot be blocked.")

    if user.status == UserStatus.BLOCKED:
        user.status = UserStatus.ACTIVE
        action = "unblocked"
    else:
        user.status = UserStatus.BLOCKED
        action = "blocked"
    await db.commit()
    return MessageResponse(message=f"User has been {action} successfully.")


async def delete_user(user_id: uuid.UUID, admin: User, db: AsyncSession) -> MessageResponse:
    if user_id == admin.id:
        raise bad_request("You cannot delete your own admin account.")
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise UserNotFound()
    if user.is_admin:
        raise forbidden("Admin accounts cannot be deleted via the dashboard.")
    await db.delete(user)
    await db.commit()
    return MessageResponse(message="User and all associated data permanently deleted.")


async def list_all_matches(
    search: str | None,
    location: str | None,
    name: str | None,
    date_from: str | None,
    date_to: str | None,
    pagination: PaginationParams,
    db: AsyncSession,
) -> PaginatedResponse:
    query = select(Match).options(selectinload(Match.host)).order_by(Match.created_at.desc())

    if search:
        term = f"%{search.lower()}%"
        query = query.where(
            or_(
                func.lower(Match.title).like(term),
                func.lower(func.coalesce(Match.location_name, Match.facility_address)).like(term),
                Match.host.has(func.lower(User.full_name).like(term)),
                Match.host.has(func.lower(User.email).like(term)),
            )
        )
    if location:
        term = f"%{location.lower()}%"
        query = query.where(
            func.lower(func.coalesce(Match.location_name, Match.facility_address)).like(term)
        )
    if name:
        term = f"%{name.lower()}%"
        query = query.where(func.lower(Match.title).like(term))
    if date_from:
        query = query.where(Match.scheduled_at >= _parse_datetime(date_from, "date_from"))
    if date_to:
        query = query.where(Match.scheduled_at <= _parse_datetime(date_to, "date_to"))

    paginated = await paginate(db, query, pagination)
    paginated.items = [
        AdminMatchListItemResponse(
            id=match.id,
            title=match.title,
            host_name=match.host.full_name,
            host_email=match.host.email,
            location=match.location_name or match.facility_address,
            scheduled_at=match.scheduled_at,
        )
        for match in paginated.items
    ]
    return paginated


async def get_match(match_id: uuid.UUID, db: AsyncSession) -> MatchDetailResponse:
    result = await db.execute(
        select(Match).options(selectinload(Match.host)).where(Match.id == match_id)
    )
    match = result.scalar_one_or_none()
    if not match:
        raise MatchNotFound()
    current_players = (await db.execute(
        select(func.count()).where(
            and_(
                MatchPlayer.match_id == match.id,
                MatchPlayer.status == MatchPlayerStatus.ACTIVE,
            )
        )
    )).scalar_one()
    return _build_match_detail_response(match, current_players)


async def edit_match(
    match_id: uuid.UUID,
    payload: UpdateMatchRequest,
    admin: User,
    db: AsyncSession,
) -> MatchDetailResponse:
    result = await db.execute(
        select(Match).options(selectinload(Match.host)).where(Match.id == match_id)
    )
    match = result.scalar_one_or_none()
    if not match:
        raise MatchNotFound()
    if match.status in [MatchStatus.COMPLETED, MatchStatus.CANCELLED]:
        raise bad_request(f"Cannot edit a '{match.status.value}' match.")

    if payload.title is not None:
        match.title = payload.title.strip()
    if payload.description is not None:
        match.description = payload.description
    if payload.facility_address is not None:
        match.facility_address = payload.facility_address.strip()
    if payload.scheduled_at is not None:
        match.scheduled_at = payload.scheduled_at
    if payload.duration_minutes is not None:
        match.duration_minutes = payload.duration_minutes
    if payload.skill_level is not None:
        match.skill_level = payload.skill_level

    if payload.max_players is not None:
        current_count = (await db.execute(
            select(func.count()).where(
                and_(
                    MatchPlayer.match_id == match_id,
                    MatchPlayer.status == MatchPlayerStatus.ACTIVE,
                )
            )
        )).scalar_one()
        if payload.max_players < current_count:
            raise bad_request(
                f"Cannot set max_players to {payload.max_players} — there are already {current_count} active players in this match."
            )
        match.max_players = payload.max_players

    await db.commit()
    await db.refresh(match)
    current_players = (await db.execute(
        select(func.count()).where(
            and_(
                MatchPlayer.match_id == match_id,
                MatchPlayer.status == MatchPlayerStatus.ACTIVE,
            )
        )
    )).scalar_one()
    return _build_match_detail_response(match, current_players)


async def delete_match(match_id: uuid.UUID, admin: User, db: AsyncSession) -> MessageResponse:
    match = (await db.execute(select(Match).where(Match.id == match_id))).scalar_one_or_none()
    if not match:
        raise MatchNotFound()
    await db.delete(match)
    await db.commit()
    return MessageResponse(message=f"Match '{match.title}' permanently deleted.")


async def list_review_users(
    search: str | None,
    pagination: PaginationParams,
    db: AsyncSession,
) -> PaginatedResponse:
    reviews_count_subquery = (
        select(Review.reviewee_id.label("user_id"), func.count().label("reviews_count"))
        .group_by(Review.reviewee_id)
        .subquery()
    )
    query = (
        select(User, func.coalesce(reviews_count_subquery.c.reviews_count, 0).label("reviews_count"))
        .outerjoin(reviews_count_subquery, reviews_count_subquery.c.user_id == User.id)
        .order_by(User.full_name.asc())
    )
    if search:
        term = f"%{search.lower()}%"
        query = query.where(
            or_(
                func.lower(User.full_name).like(term),
                func.lower(User.email).like(term),
            )
        )

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar_one()
    result = await db.execute(query.offset(pagination.skip).limit(pagination.limit))
    rows = result.all()

    return PaginatedResponse(
        items=[
            ReviewModerationUserItemResponse(
                id=user.id,
                full_name=user.full_name,
                avatar_url=user.avatar_url,
                reviews_count=reviews_count,
            )
            for user, reviews_count in rows
        ],
        total=total,
        page=pagination.page,
        limit=pagination.limit,
        has_next=(pagination.skip + pagination.limit) < total,
        has_prev=pagination.page > 1,
    )


async def get_review_user_reviews(
    user_id: uuid.UUID,
    pagination: PaginationParams,
    db: AsyncSession,
) -> ReviewModerationUserReviewsResponse:
    reviews_count = (await db.execute(
        select(func.count()).where(Review.reviewee_id == user_id)
    )).scalar_one()
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise UserNotFound()

    query = (
        select(Review)
        .options(selectinload(Review.reviewer))
        .where(Review.reviewee_id == user_id)
        .order_by(Review.created_at.desc())
    )
    paginated = await paginate(db, query, pagination)
    items = [
        ReviewModerationReviewItemResponse(
            id=review.id,
            reviewer_name=review.reviewer.full_name,
            rating=review.rating,
            comment=review.comment,
            created_at=review.created_at,
        )
        for review in paginated.items
    ]
    return ReviewModerationUserReviewsResponse(
        user=ReviewModerationUserItemResponse(
            id=user.id,
            full_name=user.full_name,
            avatar_url=user.avatar_url,
            reviews_count=reviews_count,
        ),
        items=items,
        total=paginated.total,
        page=paginated.page,
        limit=paginated.limit,
        has_next=paginated.has_next,
        has_prev=paginated.has_prev,
    )


async def delete_review(review_id: uuid.UUID, db: AsyncSession) -> MessageResponse:
    review = (await db.execute(select(Review).where(Review.id == review_id))).scalar_one_or_none()
    if not review:
        raise not_found("Review")
    await db.delete(review)
    await db.commit()
    return MessageResponse(message="Review deleted successfully.")


async def get_content_page(section: str, db: AsyncSession) -> ContentPageResponse:
    section = _validate_content_section(section)
    page = (await db.execute(
        select(ContentPage).where(ContentPage.section == section)
    )).scalar_one_or_none()
    if not page:
        page = ContentPage(
            section=section,
            title=CONTENT_SECTIONS[section],
            content="",
        )
        db.add(page)
        await db.commit()
        await db.refresh(page)
    return ContentPageResponse(section=page.section, title=page.title, content=page.content)


async def update_content_page(
    section: str,
    payload: UpdateContentPageRequest,
    db: AsyncSession,
) -> MessageResponse:
    section = _validate_content_section(section)
    page = (await db.execute(
        select(ContentPage).where(ContentPage.section == section)
    )).scalar_one_or_none()
    if not page:
        page = ContentPage(section=section, title=payload.title, content=payload.content)
        db.add(page)
    else:
        page.title = payload.title
        page.content = payload.content
    await db.commit()
    return MessageResponse(message="Content updated successfully.")


async def list_support_requests(
    search: str | None,
    status: str | None,
    pagination: PaginationParams,
    db: AsyncSession,
) -> PaginatedResponse:
    query = select(SupportRequest).options(selectinload(SupportRequest.user)).order_by(SupportRequest.created_at.desc())

    if search:
        term = f"%{search.lower()}%"
        query = query.where(
            or_(
                func.lower(SupportRequest.subject).like(term),
                func.lower(SupportRequest.message).like(term),
                SupportRequest.user.has(func.lower(User.full_name).like(term)),
                SupportRequest.user.has(func.lower(func.coalesce(User.location, "")).like(term)),
                cast(SupportRequest.user_id, String).like(term),
            )
        )

    if status:
        try:
            status_enum = SupportRequestStatus(status)
        except ValueError as exc:
            raise bad_request(
                f"Invalid status '{status}'. Valid values: {[value.value for value in SupportRequestStatus]}"
            ) from exc
        query = query.where(SupportRequest.status == status_enum)

    paginated = await paginate(db, query, pagination)
    paginated.items = [
        SupportRequestListItemResponse(
            id=request.id,
            user_id=request.user_id,
            subject=request.subject,
            submitted_at=request.created_at,
            status=request.status,
        )
        for request in paginated.items
    ]
    return paginated


async def get_support_request(request_id: uuid.UUID, db: AsyncSession) -> SupportRequestDetailResponse:
    request = (await db.execute(
        select(SupportRequest).where(SupportRequest.id == request_id)
    )).scalar_one_or_none()
    if not request:
        raise not_found("Support request")
    return SupportRequestDetailResponse(
        id=request.id,
        user_id=request.user_id,
        subject=request.subject,
        message=request.message,
        submitted_at=request.created_at,
        status=request.status,
    )


async def resolve_support_request(request_id: uuid.UUID, db: AsyncSession) -> MessageResponse:
    request = (await db.execute(
        select(SupportRequest).where(SupportRequest.id == request_id)
    )).scalar_one_or_none()
    if not request:
        raise not_found("Support request")
    request.status = SupportRequestStatus.RESOLVED
    await db.commit()
    return MessageResponse(message="Support request marked as resolved.")


async def delete_support_request(request_id: uuid.UUID, db: AsyncSession) -> MessageResponse:
    request = (await db.execute(
        select(SupportRequest).where(SupportRequest.id == request_id)
    )).scalar_one_or_none()
    if not request:
        raise not_found("Support request")
    await db.delete(request)
    await db.commit()
    return MessageResponse(message="Support request deleted successfully.")


async def get_admin_account(admin: User) -> AdminAccountResponse:
    return AdminAccountResponse(
        full_name=admin.full_name,
        email=admin.email,
        phone=admin.phone_number,
    )


async def update_admin_account(
    admin: User,
    payload: UpdateAdminAccountRequest,
    db: AsyncSession,
) -> MessageResponse:
    email_owner = (await db.execute(
        select(User).where(func.lower(User.email) == payload.email.lower(), User.id != admin.id)
    )).scalar_one_or_none()
    if email_owner:
        raise conflict(f"A user with email '{payload.email}' already exists.")

    phone_owner = None
    if payload.phone:
        phone_owner = (await db.execute(
            select(User).where(User.phone_number == payload.phone, User.id != admin.id)
        )).scalar_one_or_none()
    if phone_owner:
        raise conflict(f"A user with phone '{payload.phone}' already exists.")

    admin.full_name = payload.full_name
    admin.email = payload.email.lower()
    admin.phone_number = payload.phone
    await db.commit()
    return MessageResponse(message="Admin profile updated successfully.")


async def change_admin_password(
    admin: User,
    current_password: str,
    new_password: str,
    db: AsyncSession,
) -> MessageResponse:
    if not verify_password(current_password, admin.hashed_password):
        raise bad_request("Current password is incorrect.")
    if len(new_password) < 8:
        raise bad_request("New password must be at least 8 characters.")
    if not re.search(r"[A-Z]", new_password):
        raise bad_request("New password must contain at least one uppercase letter.")
    if not re.search(r"\d", new_password):
        raise bad_request("New password must contain at least one number.")
    if verify_password(new_password, admin.hashed_password):
        raise bad_request("New password must be different from the current password.")
    admin.hashed_password = hash_password(new_password)
    await db.commit()
    return MessageResponse(message="Password changed successfully.")
