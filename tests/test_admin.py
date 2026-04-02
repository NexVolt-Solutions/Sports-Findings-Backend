import calendar
import uuid
from datetime import datetime, timedelta, timezone

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import (
    MatchPlayerRole,
    MatchPlayerStatus,
    MatchStatus,
    SkillLevel,
    SportType,
    SupportRequestStatus,
    UserStatus,
)
from app.models.match import Match
from app.models.match_player import MatchPlayer
from app.models.review import Review
from app.models.support_request import SupportRequest
from app.models.user import User, UserSport
from app.utils.security import create_access_token, hash_password


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def make_user(
    db: AsyncSession,
    email: str,
    *,
    name: str = "Test User",
    is_admin: bool = False,
    status: UserStatus = UserStatus.ACTIVE,
    location: str | None = None,
    phone: str | None = None,
    created_at: datetime | None = None,
    total_games_played: int = 0,
) -> tuple[User, str]:
    user = User(
        email=email,
        hashed_password=hash_password("Secure123"),
        full_name=name,
        status=status,
        is_admin=is_admin,
        location=location,
        phone_number=phone,
        total_games_played=total_games_played,
    )
    db.add(user)
    await db.commit()
    if created_at is not None:
        user.created_at = created_at
        user.updated_at = created_at
        await db.commit()
    await db.refresh(user)
    return user, create_access_token(str(user.id))


async def add_user_sport(
    db: AsyncSession,
    user: User,
    sport: SportType,
    skill_level: SkillLevel = SkillLevel.INTERMEDIATE,
) -> None:
    db.add(UserSport(user_id=user.id, sport=sport, skill_level=skill_level))
    await db.commit()


async def make_match(
    db: AsyncSession,
    host: User,
    *,
    title: str = "Test Match",
    sport: SportType = SportType.FOOTBALL,
    status: MatchStatus = MatchStatus.OPEN,
    scheduled_at: datetime | None = None,
    location_name: str | None = None,
    facility_address: str = "Test Facility",
) -> Match:
    match = Match(
        host_id=host.id,
        sport=sport,
        title=title,
        description="Test",
        facility_address=facility_address,
        location_name=location_name,
        scheduled_at=scheduled_at or (datetime.now(timezone.utc) + timedelta(days=1)),
        duration_minutes=90,
        max_players=10,
        skill_level=SkillLevel.INTERMEDIATE,
        status=status,
    )
    db.add(match)
    await db.flush()
    db.add(
        MatchPlayer(
            match_id=match.id,
            user_id=host.id,
            role=MatchPlayerRole.HOST,
            status=MatchPlayerStatus.ACTIVE,
        )
    )
    await db.commit()
    await db.refresh(match)
    return match


async def make_review(
    db: AsyncSession,
    reviewer: User,
    reviewee: User,
    match: Match,
    *,
    rating: int = 5,
    comment: str = "Great game!",
) -> Review:
    review = Review(
        reviewer_id=reviewer.id,
        reviewee_id=reviewee.id,
        match_id=match.id,
        rating=rating,
        comment=comment,
    )
    db.add(review)
    await db.commit()
    await db.refresh(review)
    return review


async def make_support_request(
    db: AsyncSession,
    user: User,
    *,
    subject: str = "App feedback",
    message: str = "This is feedback",
    status: SupportRequestStatus = SupportRequestStatus.OPEN,
    created_at: datetime | None = None,
) -> SupportRequest:
    request = SupportRequest(
        user_id=user.id,
        subject=subject,
        message=message,
        status=status,
    )
    db.add(request)
    await db.commit()
    if created_at is not None:
        request.created_at = created_at
        request.updated_at = created_at
        await db.commit()
    await db.refresh(request)
    return request


async def test_admin_dashboard_matches_ui_contract(client: AsyncClient, db_session: AsyncSession):
    now = datetime.now(timezone.utc)
    current_year = now.year
    admin, admin_token = await make_user(
        db_session,
        "dashboard_admin@example.com",
        is_admin=True,
        created_at=datetime(current_year, 1, 15, 12, 0, tzinfo=timezone.utc),
    )
    host, _ = await make_user(
        db_session,
        "dashboard_host@example.com",
        created_at=datetime(current_year, 2, 10, 12, 0, tzinfo=timezone.utc),
    )
    await make_user(
        db_session,
        "dashboard_recent@example.com",
        created_at=now - timedelta(hours=6),
    )
    await make_user(
        db_session,
        "dashboard_last_year@example.com",
        created_at=datetime(current_year - 1, 12, 10, 12, 0, tzinfo=timezone.utc),
    )

    await make_match(
        db_session,
        host,
        title="Completed Football Match",
        sport=SportType.FOOTBALL,
        status=MatchStatus.COMPLETED,
        scheduled_at=datetime(current_year, 3, 2, 18, 0, tzinfo=timezone.utc),
    )
    await make_match(
        db_session,
        host,
        title="Completed Cricket Match",
        sport=SportType.CRICKET,
        status=MatchStatus.COMPLETED,
        scheduled_at=datetime(current_year, 3, 4, 18, 0, tzinfo=timezone.utc),
    )
    await make_match(
        db_session,
        host,
        title="Open Basketball Match",
        sport=SportType.BASKETBALL,
        status=MatchStatus.OPEN,
    )

    response = await client.get("/api/v1/admin/dashboard", headers=auth(admin_token))
    assert response.status_code == 200
    data = response.json()
    assert data["total_users"] == 4
    assert data["new_users_today"] == 1
    assert data["total_matches"] == 2
    assert data["active_matches"] == 1
    month_counts = {item["month"]: item["count"] for item in data["total_users_by_month"]}
    assert month_counts["JAN"] == 1
    assert month_counts["FEB"] == 1
    assert month_counts[calendar.month_abbr[now.month].upper()] == 1


async def test_admin_users_list_supports_ui_filters(client: AsyncClient, db_session: AsyncSession):
    admin, admin_token = await make_user(db_session, "admin@example.com", is_admin=True)
    active_user, _ = await make_user(
        db_session,
        "alex@example.com",
        name="Alex Mitchell",
        location="San Francisco, CA",
        total_games_played=24,
    )
    await add_user_sport(db_session, active_user, SportType.FOOTBALL)
    await make_user(
        db_session,
        "blocked@example.com",
        name="Blocked User",
        status=UserStatus.BLOCKED,
        location="Austin, TX",
    )

    response = await client.get(
        "/api/v1/admin/users?search=alex&status=Active&sport=Football&location=Francisco",
        headers=auth(admin_token),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["full_name"] == "Alex Mitchell"
    assert data["items"][0]["matches"] == 24
    assert data["items"][0]["status"] == "Active"


async def test_admin_create_user_returns_ui_shape(client: AsyncClient, db_session: AsyncSession):
    admin, admin_token = await make_user(db_session, "creator_admin@example.com", is_admin=True)
    response = await client.post(
        "/api/v1/admin/users",
        json={
            "full_name": "New User",
            "email": "newuser@example.com",
            "password": "Secure123",
        },
        headers=auth(admin_token),
    )
    assert response.status_code == 201
    data = response.json()
    assert data["full_name"] == "New User"
    assert data["email"] == "newuser@example.com"
    assert data["status"] == "Active"


async def test_admin_cannot_create_second_admin(client: AsyncClient, db_session: AsyncSession):
    admin, admin_token = await make_user(db_session, "existing_admin@example.com", is_admin=True)
    response = await client.post(
        "/api/v1/admin/users",
        json={
            "full_name": "Another Admin",
            "email": "second_admin@example.com",
            "password": "Secure123",
            "is_admin": True,
        },
        headers=auth(admin_token),
    )
    assert response.status_code == 409


async def test_admin_matches_list_returns_ui_shape(client: AsyncClient, db_session: AsyncSession):
    admin, admin_token = await make_user(db_session, "match_admin@example.com", is_admin=True)
    host, _ = await make_user(db_session, "host@example.com", name="Alex Johnson")
    match = await make_match(
        db_session,
        host,
        title="Sunday Football Match",
        location_name="New York",
        scheduled_at=datetime.now(timezone.utc) + timedelta(days=2),
    )

    response = await client.get(
        "/api/v1/admin/matches?search=Sunday&location=York&name=Football",
        headers=auth(admin_token),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == str(match.id)
    assert data["items"][0]["host_name"] == "Alex Johnson"
    assert data["items"][0]["host_email"] == "host@example.com"
    assert data["items"][0]["location"] == "New York"


async def test_admin_can_edit_match(client: AsyncClient, db_session: AsyncSession):
    admin, admin_token = await make_user(db_session, "editor_admin@example.com", is_admin=True)
    host, _ = await make_user(db_session, "editor_host@example.com")
    match = await make_match(db_session, host, title="Original Title")

    response = await client.put(
        f"/api/v1/admin/matches/{match.id}",
        json={"title": "Updated Title", "duration_minutes": 120},
        headers=auth(admin_token),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Updated Title"
    assert data["duration_minutes"] == 120


async def test_admin_review_moderation_lists_users_and_reviews(client: AsyncClient, db_session: AsyncSession):
    admin, admin_token = await make_user(db_session, "review_admin@example.com", is_admin=True)
    reviewer, _ = await make_user(db_session, "reviewer@example.com", name="Alex Johnson")
    reviewee, _ = await make_user(db_session, "reviewee@example.com", name="Rimsha")
    match = await make_match(db_session, reviewer, status=MatchStatus.COMPLETED)
    db_session.add(
        MatchPlayer(
            match_id=match.id,
            user_id=reviewee.id,
            role=MatchPlayerRole.PLAYER,
            status=MatchPlayerStatus.ACTIVE,
        )
    )
    await db_session.commit()
    review = await make_review(db_session, reviewer, reviewee, match, comment="Great game everyone!")

    users_response = await client.get(
        "/api/v1/admin/reviews/users?search=rim",
        headers=auth(admin_token),
    )
    assert users_response.status_code == 200
    users_data = users_response.json()
    assert users_data["items"][0]["full_name"] == "Rimsha"
    assert users_data["items"][0]["reviews_count"] == 1

    reviews_response = await client.get(
        f"/api/v1/admin/reviews/users/{reviewee.id}",
        headers=auth(admin_token),
    )
    assert reviews_response.status_code == 200
    reviews_data = reviews_response.json()
    assert reviews_data["user"]["full_name"] == "Rimsha"
    assert reviews_data["items"][0]["id"] == str(review.id)
    assert reviews_data["items"][0]["reviewer_name"] == "Alex Johnson"


async def test_admin_can_delete_review(client: AsyncClient, db_session: AsyncSession):
    admin, admin_token = await make_user(db_session, "delete_review_admin@example.com", is_admin=True)
    reviewer, _ = await make_user(db_session, "delete_reviewer@example.com")
    reviewee, _ = await make_user(db_session, "delete_reviewee@example.com")
    match = await make_match(db_session, reviewer, status=MatchStatus.COMPLETED)
    db_session.add(
        MatchPlayer(
            match_id=match.id,
            user_id=reviewee.id,
            role=MatchPlayerRole.PLAYER,
            status=MatchPlayerStatus.ACTIVE,
        )
    )
    await db_session.commit()
    review = await make_review(db_session, reviewer, reviewee, match)

    response = await client.delete(
        f"/api/v1/admin/reviews/{review.id}",
        headers=auth(admin_token),
    )
    assert response.status_code == 200
    assert "deleted successfully" in response.json()["message"].lower()


async def test_content_management_get_and_update(client: AsyncClient, db_session: AsyncSession):
    admin, admin_token = await make_user(db_session, "content_admin@example.com", is_admin=True)

    get_response = await client.get(
        "/api/v1/admin/content/terms-of-service",
        headers=auth(admin_token),
    )
    assert get_response.status_code == 200
    assert get_response.json()["section"] == "terms-of-service"

    update_response = await client.put(
        "/api/v1/admin/content/terms-of-service",
        json={"title": "Terms of Service", "content": "Updated content"},
        headers=auth(admin_token),
    )
    assert update_response.status_code == 200

    verify_response = await client.get(
        "/api/v1/admin/content/terms-of-service",
        headers=auth(admin_token),
    )
    assert verify_response.json()["content"] == "Updated content"


async def test_support_request_endpoints_match_ui(client: AsyncClient, db_session: AsyncSession):
    admin, admin_token = await make_user(db_session, "support_admin@example.com", is_admin=True)
    user, _ = await make_user(db_session, "support_user@example.com", name="Support User", location="Karachi")
    support_request = await make_support_request(
        db_session,
        user,
        subject="App feedback",
        message="Full feedback text here",
    )

    list_response = await client.get(
        "/api/v1/admin/support-requests?search=feedback",
        headers=auth(admin_token),
    )
    assert list_response.status_code == 200
    list_data = list_response.json()
    assert list_data["items"][0]["id"] == str(support_request.id)
    assert list_data["items"][0]["status"] == "Open"

    detail_response = await client.get(
        f"/api/v1/admin/support-requests/{support_request.id}",
        headers=auth(admin_token),
    )
    assert detail_response.status_code == 200
    assert detail_response.json()["message"] == "Full feedback text here"

    resolve_response = await client.patch(
        f"/api/v1/admin/support-requests/{support_request.id}/resolve",
        headers=auth(admin_token),
    )
    assert resolve_response.status_code == 200

    resolved_detail = await client.get(
        f"/api/v1/admin/support-requests/{support_request.id}",
        headers=auth(admin_token),
    )
    assert resolved_detail.json()["status"] == "Resolved"

    delete_response = await client.delete(
        f"/api/v1/admin/support-requests/{support_request.id}",
        headers=auth(admin_token),
    )
    assert delete_response.status_code == 200


async def test_admin_account_get_and_update(client: AsyncClient, db_session: AsyncSession):
    admin, admin_token = await make_user(
        db_session,
        "account_admin@example.com",
        is_admin=True,
        name="Admin User",
        phone="+1234567890",
    )

    get_response = await client.get("/api/v1/admin/account", headers=auth(admin_token))
    assert get_response.status_code == 200
    assert get_response.json()["full_name"] == "Admin User"

    update_response = await client.put(
        "/api/v1/admin/account",
        json={
            "full_name": "Updated Admin",
            "email": "account_admin@example.com",
            "phone": "+19876543210",
        },
        headers=auth(admin_token),
    )
    assert update_response.status_code == 200

    verify_response = await client.get("/api/v1/admin/account", headers=auth(admin_token))
    assert verify_response.json()["full_name"] == "Updated Admin"
    assert verify_response.json()["phone"] == "+19876543210"


async def test_admin_change_password_requires_confirmation(client: AsyncClient, db_session: AsyncSession):
    admin, admin_token = await make_user(db_session, "password_admin@example.com", is_admin=True)

    bad_response = await client.patch(
        "/api/v1/admin/account/password",
        json={
            "current_password": "Secure123",
            "new_password": "NewSecure456",
            "confirm_new_password": "Mismatch456",
        },
        headers=auth(admin_token),
    )
    assert bad_response.status_code == 422

    good_response = await client.patch(
        "/api/v1/admin/account/password",
        json={
            "current_password": "Secure123",
            "new_password": "NewSecure456",
            "confirm_new_password": "NewSecure456",
        },
        headers=auth(admin_token),
    )
    assert good_response.status_code == 200
