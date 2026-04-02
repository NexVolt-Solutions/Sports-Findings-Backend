"""
Phase 7 — QA & Hardening Tests

Tests for:
- Security: token expiry, token type cross-use, refresh token abuse
- Validation edge cases: past dates, boundary values, empty strings
- Pagination edge cases: limit clamping, page boundaries
- Match flow edge cases: last player leaves full match, geocoding failure resilience
- Profile edge cases: user with no sports, empty bio
- Admin edge cases: empty search, filter combinations
- Error handling: consistent 404/403/400 shapes
"""
import uuid
import pytest
from datetime import datetime, timedelta, timezone
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.match import Match
from app.models.match_player import MatchPlayer
from app.models.enums import (
    UserStatus, SportType, SkillLevel,
    MatchStatus, MatchPlayerRole, MatchPlayerStatus,
)
from app.utils.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
)
from jose import jwt
from app.config import settings


# ─── Helpers ──────────────────────────────────────────────────────────────────

def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def future_dt(hours: int = 24) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


def past_dt(hours: int = 2) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


async def make_user(
    db: AsyncSession,
    email: str,
    name: str = "Test User",
    status: UserStatus = UserStatus.ACTIVE,
    is_admin: bool = False,
) -> tuple[User, str]:
    user = User(
        email=email,
        hashed_password=hash_password("Secure123"),
        full_name=name,
        status=status,
        is_admin=is_admin,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user, create_access_token(str(user.id))


async def make_match(
    db: AsyncSession,
    host: User,
    status: MatchStatus = MatchStatus.OPEN,
    max_players: int = 10,
) -> Match:
    match = Match(
        host_id=host.id,
        sport=SportType.FOOTBALL,
        title="Hardening Test Match",
        description="Test",
        facility_address="Test Facility",
        scheduled_at=datetime.now(timezone.utc) + timedelta(hours=24),
        duration_minutes=90,
        max_players=max_players,
        skill_level=SkillLevel.INTERMEDIATE,
        status=status,
    )
    db.add(match)
    await db.flush()
    db.add(MatchPlayer(
        match_id=match.id,
        user_id=host.id,
        role=MatchPlayerRole.HOST,
        status=MatchPlayerStatus.ACTIVE,
    ))
    await db.commit()
    await db.refresh(match)
    return match


# ─── Security: Token Tests ────────────────────────────────────────────────────

async def test_expired_access_token_returns_401(client: AsyncClient, db_session: AsyncSession):
    """An expired access token should return 401."""
    user, _ = await make_user(db_session, "expired@example.com")

    # Create a token that expired 1 second ago
    expired_payload = {
        "sub": str(user.id),
        "exp": datetime.now(timezone.utc) - timedelta(seconds=1),
        "type": "access",
    }
    expired_token = jwt.encode(
        expired_payload,
        settings.secret_key,
        algorithm=settings.algorithm,
    )

    response = await client.get(
        "/api/v1/users/me",
        headers=auth(expired_token),
    )
    assert response.status_code == 401


async def test_refresh_token_cannot_be_used_as_access_token(
    client: AsyncClient, db_session: AsyncSession
):
    """A refresh token must not be accepted where an access token is required."""
    user, _ = await make_user(db_session, "refresh_abuse@example.com")
    refresh_token = create_refresh_token(str(user.id))

    response = await client.get(
        "/api/v1/users/me",
        headers=auth(refresh_token),
    )
    assert response.status_code == 401


async def test_access_token_cannot_be_used_as_refresh_token(
    client: AsyncClient, db_session: AsyncSession
):
    """An access token must not be accepted on the refresh endpoint."""
    user, access_token = await make_user(db_session, "access_as_refresh@example.com")

    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": access_token},
    )
    assert response.status_code == 401


async def test_tampered_token_returns_401(client: AsyncClient, db_session: AsyncSession):
    """A token with an invalid signature should return 401."""
    user, token = await make_user(db_session, "tampered@example.com")
    tampered = token[:-5] + "XXXXX"

    response = await client.get("/api/v1/users/me", headers=auth(tampered))
    assert response.status_code == 401


async def test_random_string_as_token_returns_401(client: AsyncClient):
    """A completely invalid token string should return 401."""
    response = await client.get(
        "/api/v1/users/me",
        headers=auth("this.is.not.a.jwt"),
    )
    assert response.status_code == 401


async def test_nonexistent_user_token_returns_401(client: AsyncClient):
    """A valid JWT for a user that doesn't exist should return 401."""
    ghost_token = create_access_token(str(uuid.uuid4()))
    response = await client.get("/api/v1/users/me", headers=auth(ghost_token))
    assert response.status_code == 401


# ─── Validation Edge Cases ────────────────────────────────────────────────────

async def test_create_match_past_date_rejected(client: AsyncClient, db_session: AsyncSession):
    """Creating a match with a past scheduled_at should return 422."""
    _, token = await make_user(db_session, "past_date@example.com")

    response = await client.post(
        "/api/v1/matches",
        json={
            "title": "Past Match",
            "description": "Test",
            "sport": "Football",
            "facility_address": "Test Facility",
            "scheduled_at": past_dt(2),
            "duration_minutes": 90,
            "max_players": 10,
            "skill_level": "Intermediate",
        },
        headers=auth(token),
    )
    assert response.status_code == 422


async def test_create_match_title_too_short(client: AsyncClient, db_session: AsyncSession):
    """Match title shorter than 3 chars should return 422."""
    _, token = await make_user(db_session, "short_title@example.com")

    response = await client.post(
        "/api/v1/matches",
        json={
            "title": "AB",
            "description": "Test",
            "sport": "Football",
            "facility_address": "Test Facility",
            "scheduled_at": future_dt(24),
            "duration_minutes": 90,
            "max_players": 10,
            "skill_level": "Intermediate",
        },
        headers=auth(token),
    )
    assert response.status_code == 422


async def test_create_match_duration_too_short(client: AsyncClient, db_session: AsyncSession):
    """Match duration under 10 minutes should return 422."""
    _, token = await make_user(db_session, "short_dur@example.com")

    response = await client.post(
        "/api/v1/matches",
        json={
            "title": "Short Match",
            "description": "Test",
            "sport": "Basketball",
            "facility_address": "Test Court",
            "scheduled_at": future_dt(24),
            "duration_minutes": 5,
            "max_players": 10,
            "skill_level": "Beginner",
        },
        headers=auth(token),
    )
    assert response.status_code == 422


async def test_create_match_duration_too_long(client: AsyncClient, db_session: AsyncSession):
    """Match duration over 480 minutes (8 hours) should return 422."""
    _, token = await make_user(db_session, "long_dur@example.com")

    response = await client.post(
        "/api/v1/matches",
        json={
            "title": "Long Match",
            "description": "Test",
            "sport": "Cricket",
            "facility_address": "Cricket Ground",
            "scheduled_at": future_dt(24),
            "duration_minutes": 500,
            "max_players": 11,
            "skill_level": "Advanced",
        },
        headers=auth(token),
    )
    assert response.status_code == 422


async def test_review_comment_exactly_500_chars_allowed(
    client: AsyncClient, db_session: AsyncSession
):
    """Review comment of exactly 500 characters should be accepted."""
    host, host_token = await make_user(db_session, "rev_500_h@example.com")
    player, _ = await make_user(db_session, "rev_500_p@example.com")

    match = await make_match(db_session, host, status=MatchStatus.COMPLETED)
    db_session.add(MatchPlayer(
        match_id=match.id, user_id=player.id,
        role=MatchPlayerRole.PLAYER, status=MatchPlayerStatus.ACTIVE,
    ))
    await db_session.commit()

    response = await client.post(
        f"/api/v1/users/{player.id}/reviews",
        json={
            "match_id": str(match.id),
            "rating": 3,
            "comment": "x" * 500,
        },
        headers=auth(host_token),
    )
    assert response.status_code == 201


async def test_review_comment_501_chars_rejected(
    client: AsyncClient, db_session: AsyncSession
):
    """Review comment of 501 characters should return 422."""
    _, token = await make_user(db_session, "rev_501@example.com")
    other, _ = await make_user(db_session, "rev_501_o@example.com")

    response = await client.post(
        f"/api/v1/users/{other.id}/reviews",
        json={
            "match_id": str(uuid.uuid4()),
            "rating": 3,
            "comment": "x" * 501,
        },
        headers=auth(token),
    )
    assert response.status_code == 422


async def test_register_password_no_number_rejected(client: AsyncClient):
    """Password without a number should return 422."""
    response = await client.post("/api/v1/auth/register", json={
        "full_name": "Test User",
        "email": "nonum@example.com",
        "password": "NoNumbers!",
    })
    assert response.status_code == 422


async def test_register_short_full_name_rejected(client: AsyncClient):
    """Full name shorter than 2 chars should return 422."""
    response = await client.post("/api/v1/auth/register", json={
        "full_name": "A",
        "email": "shortname@example.com",
        "password": "Secure123",
    })
    assert response.status_code == 422


# ─── Pagination Edge Cases ────────────────────────────────────────────────────

async def test_pagination_limit_clamped_to_100(client: AsyncClient, db_session: AsyncSession):
    """Requesting limit > 100 should be clamped to 100 (FastAPI le=100 returns 422)."""
    _, token = await make_user(db_session, "clamp_limit@example.com")

    response = await client.get(
        "/api/v1/matches?limit=200",
        headers=auth(token),
    )
    # FastAPI validation rejects values > 100 with 422
    assert response.status_code == 422


async def test_pagination_page_zero_rejected(client: AsyncClient, db_session: AsyncSession):
    """page=0 should be rejected (minimum is 1)."""
    _, token = await make_user(db_session, "page_zero@example.com")

    response = await client.get(
        "/api/v1/matches?page=0",
        headers=auth(token),
    )
    assert response.status_code == 422


async def test_pagination_negative_page_rejected(client: AsyncClient, db_session: AsyncSession):
    """Negative page number should be rejected."""
    _, token = await make_user(db_session, "neg_page@example.com")

    response = await client.get(
        "/api/v1/matches?page=-1",
        headers=auth(token),
    )
    assert response.status_code == 422


async def test_pagination_has_prev_false_on_page_1(client: AsyncClient, db_session: AsyncSession):
    """has_prev should always be False on page 1."""
    _, token = await make_user(db_session, "hasprev@example.com")

    response = await client.get("/api/v1/matches?page=1&limit=20", headers=auth(token))
    assert response.status_code == 200
    assert response.json()["has_prev"] is False


async def test_pagination_second_page_has_prev_true(client: AsyncClient, db_session: AsyncSession):
    """has_prev should be True on page 2."""
    _, token = await make_user(db_session, "hasprev2@example.com")

    response = await client.get("/api/v1/matches?page=2&limit=20", headers=auth(token))
    assert response.status_code == 200
    assert response.json()["has_prev"] is True


# ─── Match Flow Edge Cases ────────────────────────────────────────────────────

async def test_last_non_host_leaves_full_match_reopens_slot(
    client: AsyncClient, db_session: AsyncSession
):
    """When the last non-host player leaves a FULL match, status should return to OPEN."""
    host, host_token = await make_user(db_session, "lastleave_host@example.com")
    player, player_token = await make_user(db_session, "lastleave_player@example.com")

    # max_players=2 — host fills slot 1, player fills slot 2 → FULL
    match = await make_match(db_session, host, max_players=2)
    await client.post(f"/api/v1/matches/{match.id}/join", headers=auth(player_token))

    # Verify match is FULL
    get_resp = await client.get(f"/api/v1/matches/{match.id}", headers=auth(host_token))
    assert get_resp.json()["status"] == "Full"

    # Player leaves → slot reopens → OPEN
    leave_resp = await client.delete(
        f"/api/v1/matches/{match.id}/leave", headers=auth(player_token)
    )
    assert leave_resp.status_code == 200

    get_resp2 = await client.get(f"/api/v1/matches/{match.id}", headers=auth(host_token))
    assert get_resp2.json()["status"] == "Open"


async def test_match_with_null_coordinates_creates_successfully(
    client: AsyncClient, db_session: AsyncSession
):
    """
    Match creation should succeed even if geocoding fails (coordinates remain null).
    Geocoding is async — match must be created first, coordinates updated later.
    """
    _, token = await make_user(db_session, "null_coords@example.com")

    response = await client.post(
        "/api/v1/matches",
        json={
            "title": "Geocoding Test Match",
            "description": "Test",
            "sport": "Tennis",
            "facility_address": "Some Unknown Address XYZ123",
            "scheduled_at": future_dt(24),
            "duration_minutes": 60,
            "max_players": 4,
            "skill_level": "Beginner",
        },
        headers=auth(token),
    )
    # Match should be created regardless of geocoding result
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Geocoding Test Match"
    # Coordinates may or may not be populated (geocoding is async)
    assert "latitude" in data
    assert "longitude" in data


async def test_cannot_join_cancelled_match(client: AsyncClient, db_session: AsyncSession):
    """Joining a cancelled match should return 409."""
    host, host_token = await make_user(db_session, "cancelled_join_h@example.com")
    player, player_token = await make_user(db_session, "cancelled_join_p@example.com")

    match = await make_match(db_session, host, status=MatchStatus.CANCELLED)

    response = await client.post(
        f"/api/v1/matches/{match.id}/join",
        headers=auth(player_token),
    )
    assert response.status_code == 409


async def test_cannot_join_completed_match(client: AsyncClient, db_session: AsyncSession):
    """Joining a completed match should return 409."""
    host, host_token = await make_user(db_session, "completed_join_h@example.com")
    player, player_token = await make_user(db_session, "completed_join_p@example.com")

    match = await make_match(db_session, host, status=MatchStatus.COMPLETED)

    response = await client.post(
        f"/api/v1/matches/{match.id}/join",
        headers=auth(player_token),
    )
    assert response.status_code == 409


async def test_update_max_players_below_current_count_rejected(
    client: AsyncClient, db_session: AsyncSession
):
    """
    Setting max_players lower than current active player count should return 400.
    E.g. 3 players in match, trying to set max_players=2.
    """
    host, host_token = await make_user(db_session, "below_count_h@example.com")
    p1, p1_token = await make_user(db_session, "below_count_p1@example.com")
    p2, p2_token = await make_user(db_session, "below_count_p2@example.com")

    # max_players=5, host + 2 players = 3 active
    match = await make_match(db_session, host, max_players=5)
    await client.post(f"/api/v1/matches/{match.id}/join", headers=auth(p1_token))
    await client.post(f"/api/v1/matches/{match.id}/join", headers=auth(p2_token))

    # Try to reduce max_players to 2 (below current count of 3)
    response = await client.put(
        f"/api/v1/matches/{match.id}",
        json={"max_players": 2},
        headers=auth(host_token),
    )
    assert response.status_code == 400


# ─── Profile Edge Cases ───────────────────────────────────────────────────────

async def test_user_with_no_sports_has_valid_profile(
    client: AsyncClient, db_session: AsyncSession
):
    """A user with no sports added should still return a valid profile."""
    user, token = await make_user(db_session, "no_sports@example.com", "No Sports User")

    response = await client.get("/api/v1/users/me", headers=auth(token))
    assert response.status_code == 200
    data = response.json()
    assert data["sports"] == []
    assert data["full_name"] == "No Sports User"


async def test_update_profile_with_empty_bio_allowed(
    client: AsyncClient, db_session: AsyncSession
):
    """Setting bio to empty string should clear it (treated as None after strip)."""
    user, token = await make_user(db_session, "empty_bio@example.com")

    response = await client.put(
        "/api/v1/users/me",
        json={"bio": ""},
        headers=auth(token),
    )
    assert response.status_code == 200


async def test_public_profile_does_not_expose_email(
    client: AsyncClient, db_session: AsyncSession
):
    """Public profile endpoint must never expose the user's email."""
    viewer, viewer_token = await make_user(db_session, "viewer_email@example.com")
    target, _ = await make_user(db_session, "target_email@example.com")

    response = await client.get(
        f"/api/v1/users/{target.id}",
        headers=auth(viewer_token),
    )
    assert response.status_code == 200
    assert "email" not in response.json()


async def test_public_profile_does_not_expose_status(
    client: AsyncClient, db_session: AsyncSession
):
    """Public profile endpoint must not expose the user's account status."""
    viewer, viewer_token = await make_user(db_session, "viewer_status@example.com")
    target, _ = await make_user(db_session, "target_status@example.com")

    response = await client.get(
        f"/api/v1/users/{target.id}",
        headers=auth(viewer_token),
    )
    assert response.status_code == 200
    assert "status" not in response.json()


async def test_follower_count_updates_after_follow(
    client: AsyncClient, db_session: AsyncSession
):
    """Follower count on public profile should increase after being followed."""
    follower, follower_token = await make_user(db_session, "fcount_f@example.com")
    followee, followee_token = await make_user(db_session, "fcount_e@example.com")

    before = await client.get(
        f"/api/v1/users/{followee.id}", headers=auth(follower_token)
    )
    count_before = before.json()["followers_count"]

    await client.post(
        f"/api/v1/users/{followee.id}/follow", headers=auth(follower_token)
    )

    after = await client.get(
        f"/api/v1/users/{followee.id}", headers=auth(follower_token)
    )
    assert after.json()["followers_count"] == count_before + 1


async def test_is_following_flag_correct(client: AsyncClient, db_session: AsyncSession):
    """is_following flag should be True after following and False before."""
    follower, follower_token = await make_user(db_session, "isfollowing_f@example.com")
    followee, _ = await make_user(db_session, "isfollowing_e@example.com")

    before = await client.get(
        f"/api/v1/users/{followee.id}", headers=auth(follower_token)
    )
    assert before.json()["is_following"] is False

    await client.post(
        f"/api/v1/users/{followee.id}/follow", headers=auth(follower_token)
    )

    after = await client.get(
        f"/api/v1/users/{followee.id}", headers=auth(follower_token)
    )
    assert after.json()["is_following"] is True


# ─── Admin Edge Cases ─────────────────────────────────────────────────────────

async def test_admin_empty_search_returns_all_users(
    client: AsyncClient, db_session: AsyncSession
):
    """Empty search string should return all non-admin users (no filtering applied)."""
    admin, admin_token = await make_user(
        db_session, "empty_search_admin@example.com", is_admin=True
    )
    await make_user(db_session, "empty_s_u1@example.com")
    await make_user(db_session, "empty_s_u2@example.com")

    response = await client.get(
        "/api/v1/admin/users?search=",
        headers=auth(admin_token),
    )
    assert response.status_code == 200
    assert response.json()["total"] >= 2


async def test_admin_block_already_blocked_user_unblocks(
    client: AsyncClient, db_session: AsyncSession
):
    """Blocking an already-blocked user should unblock them (toggle behavior)."""
    admin, admin_token = await make_user(
        db_session, "toggle_admin@example.com", is_admin=True
    )
    target, _ = await make_user(
        db_session, "toggle_target@example.com", status=UserStatus.BLOCKED
    )

    # First toggle: BLOCKED → ACTIVE
    response = await client.patch(
        f"/api/v1/admin/users/{target.id}/block",
        headers=auth(admin_token),
    )
    assert response.status_code == 200
    assert "unblocked" in response.json()["message"].lower()


async def test_admin_cannot_block_other_admin(
    client: AsyncClient, db_session: AsyncSession
):
    """Admin should not be able to block another admin account."""
    admin1, admin1_token = await make_user(
        db_session, "admin1_block@example.com", is_admin=True
    )
    admin2, _ = await make_user(
        db_session, "admin2_block@example.com", is_admin=True
    )

    response = await client.patch(
        f"/api/v1/admin/users/{admin2.id}/block",
        headers=auth(admin1_token),
    )
    assert response.status_code == 403


async def test_admin_stats_generated_at_is_recent(
    client: AsyncClient, db_session: AsyncSession
):
    """generated_at in stats response should be within the last few seconds."""
    from datetime import datetime, timezone, timedelta

    admin, admin_token = await make_user(
        db_session, "stats_time_admin@example.com", is_admin=True
    )
    response = await client.get(
        "/api/v1/admin/dashboard/stats", headers=auth(admin_token)
    )
    assert response.status_code == 200

    generated_at = datetime.fromisoformat(response.json()["generated_at"])
    now = datetime.now(timezone.utc)
    # Should have been generated within the last 5 seconds
    assert abs((now - generated_at).total_seconds()) < 5


# ─── Error Response Shape Tests ───────────────────────────────────────────────

async def test_404_has_detail_field(client: AsyncClient, db_session: AsyncSession):
    """404 responses should always have a 'detail' field."""
    _, token = await make_user(db_session, "shape_404@example.com")

    response = await client.get(
        f"/api/v1/matches/{uuid.uuid4()}",
        headers=auth(token),
    )
    assert response.status_code == 404
    assert "detail" in response.json()


async def test_403_has_detail_field(client: AsyncClient, db_session: AsyncSession):
    """403 responses should always have a 'detail' field."""
    _, token = await make_user(db_session, "shape_403@example.com")

    response = await client.get(
        "/api/v1/admin/dashboard/stats",
        headers=auth(token),
    )
    assert response.status_code == 403
    assert "detail" in response.json()


async def test_401_has_detail_field(client: AsyncClient):
    """401 responses should always have a 'detail' field."""
    response = await client.get(
        "/api/v1/users/me",
        headers=auth("invalid.token.here"),
    )
    assert response.status_code == 401
    assert "detail" in response.json()


async def test_422_has_detail_field(client: AsyncClient):
    """422 validation errors should always have a 'detail' field."""
    response = await client.post(
        "/api/v1/auth/register",
        json={"full_name": "Test", "email": "not-an-email", "password": "weak"},
    )
    assert response.status_code == 422
    assert "detail" in response.json()


async def test_health_check_returns_correct_fields(client: AsyncClient):
    """Health check should return status, app, version, environment."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "app" in data
    assert "version" in data
    assert "environment" in data
