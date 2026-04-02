"""
Phase 1 — User Profile Tests
Tests for: get profile, update profile, follow/unfollow, get stats
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.enums import UserStatus
from app.utils.security import create_access_token


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def create_active_user(db: AsyncSession, email: str, name: str) -> tuple[User, str]:
    """Creates an ACTIVE user directly in the DB and returns (user, access_token)."""
    from app.utils.security import hash_password
    user = User(
        email=email,
        hashed_password=hash_password("Secure123"),
        full_name=name,
        status=UserStatus.ACTIVE,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    token = create_access_token(str(user.id))
    return user, token


# ─── Get My Profile ───────────────────────────────────────────────────────────

async def test_get_my_profile_authenticated(client: AsyncClient, db_session: AsyncSession):
    """Authenticated user should get their own profile."""
    user, token = await create_active_user(db_session, "profile@example.com", "Profile User")
    response = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "profile@example.com"
    assert data["full_name"] == "Profile User"


async def test_get_my_profile_unauthenticated(client: AsyncClient):
    """Unauthenticated request should return 403."""
    response = await client.get("/api/v1/users/me")
    assert response.status_code == 403


# ─── Update Profile ───────────────────────────────────────────────────────────

async def test_update_profile_name(client: AsyncClient, db_session: AsyncSession):
    """User should be able to update their full name."""
    user, token = await create_active_user(db_session, "update@example.com", "Old Name")
    response = await client.put(
        "/api/v1/users/me",
        json={"full_name": "New Name"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["full_name"] == "New Name"


async def test_update_profile_sports(client: AsyncClient, db_session: AsyncSession):
    """User should be able to add sport skill levels to their profile."""
    user, token = await create_active_user(db_session, "sports@example.com", "Sports User")
    response = await client.put(
        "/api/v1/users/me",
        json={
            "sports": [
                {"sport": "Basketball", "skill_level": "Intermediate"},
                {"sport": "Football", "skill_level": "Beginner"},
            ]
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    sports = response.json()["sports"]
    assert len(sports) == 2
    sport_names = [s["sport"] for s in sports]
    assert "Basketball" in sport_names
    assert "Football" in sport_names


async def test_update_bio_and_location(client: AsyncClient, db_session: AsyncSession):
    """User should be able to update bio and location."""
    user, token = await create_active_user(db_session, "bio@example.com", "Bio User")
    response = await client.put(
        "/api/v1/users/me",
        json={"bio": "Love playing sports!", "location": "Copenhagen"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["bio"] == "Love playing sports!"
    assert data["location"] == "Copenhagen"


# ─── Public Profile ───────────────────────────────────────────────────────────

async def test_get_other_user_profile(client: AsyncClient, db_session: AsyncSession):
    """Authenticated user should be able to view another user's public profile."""
    viewer, viewer_token = await create_active_user(db_session, "viewer@example.com", "Viewer")
    target, _ = await create_active_user(db_session, "target@example.com", "Target User")

    response = await client.get(
        f"/api/v1/users/{target.id}",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["full_name"] == "Target User"
    # Email should NOT be in public profile
    assert "email" not in data


async def test_get_nonexistent_user_profile(client: AsyncClient, db_session: AsyncSession):
    """Requesting a non-existent user profile should return 404."""
    user, token = await create_active_user(db_session, "requester@example.com", "Requester")
    import uuid
    fake_id = uuid.uuid4()
    response = await client.get(
        f"/api/v1/users/{fake_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


# ─── Follow / Unfollow ────────────────────────────────────────────────────────

async def test_follow_user(client: AsyncClient, db_session: AsyncSession):
    """User should be able to follow another user."""
    follower, follower_token = await create_active_user(db_session, "follower@example.com", "Follower")
    followee, _ = await create_active_user(db_session, "followee@example.com", "Followee")

    response = await client.post(
        f"/api/v1/users/{followee.id}/follow",
        headers={"Authorization": f"Bearer {follower_token}"},
    )
    assert response.status_code == 201


async def test_follow_self_should_fail(client: AsyncClient, db_session: AsyncSession):
    """User should not be able to follow themselves."""
    user, token = await create_active_user(db_session, "selffollow@example.com", "Self")
    response = await client.post(
        f"/api/v1/users/{user.id}/follow",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400


async def test_follow_duplicate_should_fail(client: AsyncClient, db_session: AsyncSession):
    """Following an already-followed user should return 409."""
    follower, follower_token = await create_active_user(db_session, "dup_follower@example.com", "Dup Follower")
    followee, _ = await create_active_user(db_session, "dup_followee@example.com", "Dup Followee")

    await client.post(
        f"/api/v1/users/{followee.id}/follow",
        headers={"Authorization": f"Bearer {follower_token}"},
    )
    response = await client.post(
        f"/api/v1/users/{followee.id}/follow",
        headers={"Authorization": f"Bearer {follower_token}"},
    )
    assert response.status_code == 409


async def test_unfollow_user(client: AsyncClient, db_session: AsyncSession):
    """User should be able to unfollow someone they follow."""
    follower, follower_token = await create_active_user(db_session, "unf_follower@example.com", "UnfFollower")
    followee, _ = await create_active_user(db_session, "unf_followee@example.com", "UnfFollowee")

    await client.post(
        f"/api/v1/users/{followee.id}/follow",
        headers={"Authorization": f"Bearer {follower_token}"},
    )
    response = await client.delete(
        f"/api/v1/users/{followee.id}/follow",
        headers={"Authorization": f"Bearer {follower_token}"},
    )
    assert response.status_code == 200


async def test_unfollow_not_following_should_fail(client: AsyncClient, db_session: AsyncSession):
    """Unfollowing someone you don't follow should return 400."""
    user, token = await create_active_user(db_session, "notfollowing@example.com", "NotFollowing")
    other, _ = await create_active_user(db_session, "notfollowed@example.com", "NotFollowed")

    response = await client.delete(
        f"/api/v1/users/{other.id}/follow",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400


# ─── User Stats ───────────────────────────────────────────────────────────────

async def test_get_user_stats(client: AsyncClient, db_session: AsyncSession):
    """Should return games played, avg rating, and total reviews."""
    requester, token = await create_active_user(db_session, "statsreq@example.com", "Requester")
    target, _ = await create_active_user(db_session, "statstarget@example.com", "Target")

    response = await client.get(
        f"/api/v1/users/{target.id}/stats",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "total_games_played" in data
    assert "avg_rating" in data
    assert "total_reviews" in data
    assert data["total_games_played"] == 0
    assert data["avg_rating"] == 0.0
