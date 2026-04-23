"""
Phase 5 — Social Features Tests

Tests for:
- Reviews: create, validation, duplicate prevention
- Player invitations: host-only, status checks, duplicate prevention
- Follow notifications: DB record created on follow
"""
import uuid
import pytest
from datetime import datetime, timedelta, timezone
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.match import Match
from app.models.match_player import MatchPlayer
from app.models.notification import Notification
from app.models.enums import (
    UserStatus, SportType, SkillLevel,
    MatchStatus, MatchPlayerRole, MatchPlayerStatus,
    NotificationType,
)
from app.utils.security import create_access_token, hash_password


# ─── Helpers ──────────────────────────────────────────────────────────────────

def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def future_dt(hours: int = 24) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


async def make_user(
    db: AsyncSession, email: str, name: str = "Test User"
) -> tuple[User, str]:
    user = User(
        email=email,
        hashed_password=hash_password("Secure123"),
        full_name=name,
        status=UserStatus.ACTIVE,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user, create_access_token(str(user.id))


async def make_match_with_status(
    db: AsyncSession,
    host: User,
    status: MatchStatus = MatchStatus.OPEN,
    title: str = "Test Match",
) -> Match:
    """Create a match directly in DB with the given status."""
    match = Match(
        host_id=host.id,
        sport=SportType.FOOTBALL,
        title=title,
        description="Test",
        facility_address="Test Facility",
        scheduled_at=datetime.now(timezone.utc) + timedelta(hours=24),
        duration_minutes=90,
        max_players=10,
        skill_level=SkillLevel.INTERMEDIATE,
        status=status,
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
    return match


async def add_player_to_match(
    db: AsyncSession,
    match_id: uuid.UUID,
    user_id: uuid.UUID,
    status: MatchPlayerStatus = MatchPlayerStatus.ACTIVE,
) -> MatchPlayer:
    mp = MatchPlayer(
        match_id=match_id,
        user_id=user_id,
        role=MatchPlayerRole.PLAYER,
        status=status,
    )
    db.add(mp)
    await db.commit()
    return mp


# ─── Review Tests ─────────────────────────────────────────────────────────────

async def test_create_review_success(client: AsyncClient, db_session: AsyncSession):
    """A user should be able to review another user without any match dependency."""
    host, host_token = await make_user(db_session, "rev_host@example.com", "Review Host")
    player, _ = await make_user(db_session, "rev_player@example.com", "Review Player")

    response = await client.post(
        f"/api/v1/users/{player.id}/reviews",
        json={
            "rating": 5,
            "comment": "Great player, very cooperative!",
        },
        headers=auth(host_token),
    )
    assert response.status_code == 201
    data = response.json()
    assert data["rating"] == 5
    assert data["comment"] == "Great player, very cooperative!"
    assert data["reviewer"]["id"] == str(host.id)


async def test_create_review_no_comment(client: AsyncClient, db_session: AsyncSession):
    """Review without a comment (rating only) should be allowed."""
    host, host_token = await make_user(db_session, "rev_nocomment_h@example.com")
    player, _ = await make_user(db_session, "rev_nocomment_p@example.com")

    response = await client.post(
        f"/api/v1/users/{player.id}/reviews",
        json={"rating": 4},
        headers=auth(host_token),
    )
    assert response.status_code == 201
    assert response.json()["comment"] is None


async def test_create_review_ignores_match_id_when_provided(
    client: AsyncClient, db_session: AsyncSession
):
    """Review creation should ignore match_id and still create a plain profile review."""
    reviewer, reviewer_token = await make_user(db_session, "profile_review_h@example.com")
    reviewee, _ = await make_user(db_session, "profile_review_p@example.com")

    response = await client.post(
        f"/api/v1/users/{reviewee.id}/reviews",
        json={
            "match_id": str(uuid.uuid4()),
            "rating": 5,
            "comment": "Excellent sportsmanship.",
        },
        headers=auth(reviewer_token),
    )
    assert response.status_code == 201
    data = response.json()
    assert data["rating"] == 5
    assert data["comment"] == "Excellent sportsmanship."
    assert data["reviewer"]["id"] == str(reviewer.id)


async def test_create_review_invalid_rating_above_5(client: AsyncClient, db_session: AsyncSession):
    """Rating above 5 should fail validation."""
    _, token = await make_user(db_session, "rev_high@example.com")
    other, _ = await make_user(db_session, "rev_high_other@example.com")

    response = await client.post(
        f"/api/v1/users/{other.id}/reviews",
        json={"rating": 6},
        headers=auth(token),
    )
    assert response.status_code == 422


async def test_create_review_invalid_rating_below_1(client: AsyncClient, db_session: AsyncSession):
    """Rating below 1 should fail validation."""
    _, token = await make_user(db_session, "rev_low@example.com")
    other, _ = await make_user(db_session, "rev_low_other@example.com")

    response = await client.post(
        f"/api/v1/users/{other.id}/reviews",
        json={"rating": 0},
        headers=auth(token),
    )
    assert response.status_code == 422


async def test_create_review_self_not_allowed(client: AsyncClient, db_session: AsyncSession):
    """User should not be able to review themselves."""
    user, token = await make_user(db_session, "rev_self@example.com")

    response = await client.post(
        f"/api/v1/users/{user.id}/reviews",
        json={"rating": 5},
        headers=auth(token),
    )
    assert response.status_code == 400


async def test_create_review_nonexistent_user(client: AsyncClient, db_session: AsyncSession):
    """Reviewing a non-existent user should return 404."""
    _, token = await make_user(db_session, "rev_404@example.com")

    response = await client.post(
        f"/api/v1/users/{uuid.uuid4()}/reviews",
        json={"rating": 3},
        headers=auth(token),
    )
    assert response.status_code == 404


async def test_create_review_with_open_match_id_still_succeeds(client: AsyncClient, db_session: AsyncSession):
    """Review creation should not care whether a provided match_id refers to an open match."""
    host, host_token = await make_user(db_session, "rev_open_h@example.com")
    player, _ = await make_user(db_session, "rev_open_p@example.com")

    match = await make_match_with_status(db_session, host, MatchStatus.OPEN)

    response = await client.post(
        f"/api/v1/users/{player.id}/reviews",
        json={"match_id": str(match.id), "rating": 4},
        headers=auth(host_token),
    )
    assert response.status_code == 201


async def test_create_review_with_ongoing_match_id_still_succeeds(client: AsyncClient, db_session: AsyncSession):
    """Review creation should not care whether a provided match_id refers to an ongoing match."""
    host, host_token = await make_user(db_session, "rev_ongoing_h@example.com")
    player, _ = await make_user(db_session, "rev_ongoing_p@example.com")

    match = await make_match_with_status(db_session, host, MatchStatus.ONGOING)

    response = await client.post(
        f"/api/v1/users/{player.id}/reviews",
        json={"match_id": str(match.id), "rating": 3},
        headers=auth(host_token),
    )
    assert response.status_code == 201


async def test_create_review_with_irrelevant_match_id_still_succeeds(
    client: AsyncClient, db_session: AsyncSession
):
    """Review creation should not depend on participation in any provided match."""
    host, _ = await make_user(db_session, "rev_nonp_h@example.com")
    player, _ = await make_user(db_session, "rev_nonp_p@example.com")
    outsider, outsider_token = await make_user(db_session, "rev_nonp_out@example.com")

    match = await make_match_with_status(db_session, host, MatchStatus.COMPLETED)
    await add_player_to_match(db_session, match.id, player.id)

    response = await client.post(
        f"/api/v1/users/{player.id}/reviews",
        json={"match_id": str(match.id), "rating": 5},
        headers=auth(outsider_token),
    )
    assert response.status_code == 201


async def test_create_review_with_non_participating_reviewee_still_succeeds(
    client: AsyncClient, db_session: AsyncSession
):
    """Review creation should not require the reviewee to be in any provided match."""
    host, host_token = await make_user(db_session, "rev_notinmatch_h@example.com")
    other, _ = await make_user(db_session, "rev_notinmatch_o@example.com")

    match = await make_match_with_status(db_session, host, MatchStatus.COMPLETED)

    response = await client.post(
        f"/api/v1/users/{other.id}/reviews",
        json={"match_id": str(match.id), "rating": 3},
        headers=auth(host_token),
    )
    assert response.status_code == 201


async def test_create_review_duplicate_rejected(client: AsyncClient, db_session: AsyncSession):
    """Submitting a second review for the same user should return 409."""
    host, host_token = await make_user(db_session, "rev_dup_h@example.com")
    player, _ = await make_user(db_session, "rev_dup_p@example.com")

    payload = {"rating": 5}

    first = await client.post(
        f"/api/v1/users/{player.id}/reviews",
        json=payload,
        headers=auth(host_token),
    )
    assert first.status_code == 201

    second = await client.post(
        f"/api/v1/users/{player.id}/reviews",
        json=payload,
        headers=auth(host_token),
    )
    assert second.status_code == 409


async def test_review_visible_on_public_profile(client: AsyncClient, db_session: AsyncSession):
    """After creating a review, it should appear on the reviewee's public profile."""
    host, host_token = await make_user(db_session, "rev_vis_h@example.com", "Visible Host")
    player, player_token = await make_user(db_session, "rev_vis_p@example.com", "Visible Player")

    await client.post(
        f"/api/v1/users/{player.id}/reviews",
        json={"rating": 4, "comment": "Good match!"},
        headers=auth(host_token),
    )

    response = await client.get(
        f"/api/v1/users/{player.id}",
        headers=auth(host_token),
    )
    assert response.status_code == 200
    data = response.json()
    reviews = data["reviews"]
    assert len(reviews) >= 1
    assert reviews[0]["rating"] == 4
    assert reviews[0]["comment"] == "Good match!"


async def test_review_comment_too_long(client: AsyncClient, db_session: AsyncSession):
    """Review comment over 500 characters should fail validation."""
    _, token = await make_user(db_session, "rev_long@example.com")
    other, _ = await make_user(db_session, "rev_long_o@example.com")

    response = await client.post(
        f"/api/v1/users/{other.id}/reviews",
        json={
            "rating": 3,
            "comment": "x" * 501,
        },
        headers=auth(token),
    )
    assert response.status_code == 422


# ─── Invitation Tests ─────────────────────────────────────────────────────────

async def test_invite_player_success(client: AsyncClient, db_session: AsyncSession):
    """Host should be able to invite a registered user."""
    host, host_token = await make_user(db_session, "inv_host@example.com", "Invite Host")
    invitee, _ = await make_user(db_session, "inv_invitee@example.com", "Invitee")

    match_resp = await client.post(
        "/api/v1/matches",
        json={
            "title": "Invite Test Match",
            "description": "Test",
            "sport": "Basketball",
            "facility_address": "Test Court",
            "scheduled_at": future_dt(24),
            "duration_minutes": 60,
            "max_players": 10,
            "skill_level": "Beginner",
        },
        headers=auth(host_token),
    )
    match_id = match_resp.json()["id"]

    response = await client.post(
        f"/api/v1/matches/{match_id}/invite?invited_user_id={invitee.id}",
        headers=auth(host_token),
    )
    assert response.status_code == 201
    assert "Invitation sent" in response.json()["message"]


async def test_invite_creates_notification(client: AsyncClient, db_session: AsyncSession):
    """Inviting a player should create a MATCH_INVITED notification for them."""
    from sqlalchemy import select

    host, host_token = await make_user(db_session, "inv_notif_h@example.com")
    invitee, _ = await make_user(db_session, "inv_notif_i@example.com")

    match_resp = await client.post(
        "/api/v1/matches",
        json={
            "title": "Notif Invite Match",
            "description": "Test",
            "sport": "Cricket",
            "facility_address": "Cricket Ground",
            "scheduled_at": future_dt(24),
            "duration_minutes": 120,
            "max_players": 11,
            "skill_level": "Advanced",
        },
        headers=auth(host_token),
    )
    match_id = match_resp.json()["id"]

    await client.post(
        f"/api/v1/matches/{match_id}/invite?invited_user_id={invitee.id}",
        headers=auth(host_token),
    )

    # Verify notification record in DB
    result = await db_session.execute(
        select(Notification).where(
            Notification.user_id == invitee.id,
            Notification.type == NotificationType.MATCH_INVITED,
        )
    )
    notifications = result.scalars().all()
    assert len(notifications) >= 1
    assert str(match_id) in str(notifications[0].payload)


async def test_invite_non_host_forbidden(client: AsyncClient, db_session: AsyncSession):
    """Non-host should not be able to invite players."""
    host, host_token = await make_user(db_session, "inv_guard_h@example.com")
    other, other_token = await make_user(db_session, "inv_guard_o@example.com")
    invitee, _ = await make_user(db_session, "inv_guard_i@example.com")

    match_resp = await client.post(
        "/api/v1/matches",
        json={
            "title": "Guard Match",
            "description": "Test",
            "sport": "Football",
            "facility_address": "City Stadium",
            "scheduled_at": future_dt(24),
            "duration_minutes": 90,
            "max_players": 10,
            "skill_level": "Intermediate",
        },
        headers=auth(host_token),
    )
    match_id = match_resp.json()["id"]

    response = await client.post(
        f"/api/v1/matches/{match_id}/invite?invited_user_id={invitee.id}",
        headers=auth(other_token),
    )
    assert response.status_code == 403


async def test_invite_nonexistent_user(client: AsyncClient, db_session: AsyncSession):
    """Inviting a non-existent user should return 404."""
    host, host_token = await make_user(db_session, "inv_404_h@example.com")

    match_resp = await client.post(
        "/api/v1/matches",
        json={
            "title": "404 Match",
            "description": "Test",
            "sport": "Volleyball",
            "facility_address": "Tennis Court",
            "scheduled_at": future_dt(24),
            "duration_minutes": 60,
            "max_players": 6,
            "skill_level": "Beginner",
        },
        headers=auth(host_token),
    )
    match_id = match_resp.json()["id"]

    response = await client.post(
        f"/api/v1/matches/{match_id}/invite?invited_user_id={uuid.uuid4()}",
        headers=auth(host_token),
    )
    assert response.status_code == 404


async def test_invite_self_rejected(client: AsyncClient, db_session: AsyncSession):
    """Host cannot invite themselves."""
    host, host_token = await make_user(db_session, "inv_self_h@example.com")

    match_resp = await client.post(
        "/api/v1/matches",
        json={
            "title": "Self Match",
            "description": "Test",
            "sport": "Tennis",
            "facility_address": "Tennis Court",
            "scheduled_at": future_dt(24),
            "duration_minutes": 60,
            "max_players": 4,
            "skill_level": "Advanced",
        },
        headers=auth(host_token),
    )
    match_id = match_resp.json()["id"]

    response = await client.post(
        f"/api/v1/matches/{match_id}/invite?invited_user_id={host.id}",
        headers=auth(host_token),
    )
    assert response.status_code == 400


async def test_invite_already_in_match_rejected(client: AsyncClient, db_session: AsyncSession):
    """Inviting someone already in the match should return 409."""
    host, host_token = await make_user(db_session, "inv_dup_h@example.com")
    player, player_token = await make_user(db_session, "inv_dup_p@example.com")

    match_resp = await client.post(
        "/api/v1/matches",
        json={
            "title": "Dup Invite Match",
            "description": "Test",
            "sport": "Badminton",
            "facility_address": "Sports Hall",
            "scheduled_at": future_dt(24),
            "duration_minutes": 60,
            "max_players": 4,
            "skill_level": "Intermediate",
        },
        headers=auth(host_token),
    )
    match_id = match_resp.json()["id"]

    # Player joins the match
    await client.post(f"/api/v1/matches/{match_id}/join", headers=auth(player_token))

    # Host tries to invite them — they are already in
    response = await client.post(
        f"/api/v1/matches/{match_id}/invite?invited_user_id={player.id}",
        headers=auth(host_token),
    )
    assert response.status_code == 409


async def test_invite_to_ongoing_match_rejected(client: AsyncClient, db_session: AsyncSession):
    """Cannot invite to an ONGOING match."""
    host, host_token = await make_user(db_session, "inv_ong_h@example.com")
    invitee, _ = await make_user(db_session, "inv_ong_i@example.com")

    match = await make_match_with_status(db_session, host, MatchStatus.ONGOING)

    response = await client.post(
        f"/api/v1/matches/{match.id}/invite?invited_user_id={invitee.id}",
        headers=auth(host_token),
    )
    assert response.status_code == 400


async def test_invite_to_completed_match_rejected(client: AsyncClient, db_session: AsyncSession):
    """Cannot invite to a COMPLETED match."""
    host, host_token = await make_user(db_session, "inv_comp_h@example.com")
    invitee, _ = await make_user(db_session, "inv_comp_i@example.com")

    match = await make_match_with_status(db_session, host, MatchStatus.COMPLETED)

    response = await client.post(
        f"/api/v1/matches/{match.id}/invite?invited_user_id={invitee.id}",
        headers=auth(host_token),
    )
    assert response.status_code == 400


# ─── Follow Notification Tests ────────────────────────────────────────────────

async def test_follow_creates_notification(client: AsyncClient, db_session: AsyncSession):
    """Following a user should create a NEW_FOLLOWER notification for the followed user."""
    from sqlalchemy import select

    follower, follower_token = await make_user(db_session, "fnotif_follower@example.com", "Follower")
    followee, followee_token = await make_user(db_session, "fnotif_followee@example.com", "Followee")

    response = await client.post(
        f"/api/v1/users/{followee.id}/follow",
        headers=auth(follower_token),
    )
    assert response.status_code == 201

    # Verify notification in DB
    result = await db_session.execute(
        select(Notification).where(
            Notification.user_id == followee.id,
            Notification.type == NotificationType.NEW_FOLLOWER,
        )
    )
    notifications = result.scalars().all()
    assert len(notifications) >= 1
    assert str(follower.id) in str(notifications[0].payload)


async def test_follow_notification_visible_via_api(
    client: AsyncClient, db_session: AsyncSession
):
    """The NEW_FOLLOWER notification should appear in the followed user's notifications list."""
    follower, follower_token = await make_user(db_session, "fnotif_api_f@example.com", "API Follower")
    followee, followee_token = await make_user(db_session, "fnotif_api_e@example.com", "API Followee")

    await client.post(
        f"/api/v1/users/{followee.id}/follow",
        headers=auth(follower_token),
    )

    response = await client.get(
        "/api/v1/notifications",
        headers=auth(followee_token),
    )
    assert response.status_code == 200
    types = [n["type"] for n in response.json()["items"]]
    assert "new_follower" in types


async def test_unfollow_does_not_create_notification(
    client: AsyncClient, db_session: AsyncSession
):
    """Unfollowing should NOT create a notification."""
    from sqlalchemy import select

    follower, follower_token = await make_user(db_session, "unfollow_notif_f@example.com")
    followee, _ = await make_user(db_session, "unfollow_notif_e@example.com")

    # Follow first
    await client.post(f"/api/v1/users/{followee.id}/follow", headers=auth(follower_token))

    # Count notifications before unfollow
    result_before = await db_session.execute(
        select(Notification).where(Notification.user_id == followee.id)
    )
    count_before = len(result_before.scalars().all())

    # Unfollow
    await client.delete(f"/api/v1/users/{followee.id}/follow", headers=auth(follower_token))

    # Count after — should be the same (no new notification)
    result_after = await db_session.execute(
        select(Notification).where(Notification.user_id == followee.id)
    )
    count_after = len(result_after.scalars().all())

    assert count_after == count_before
