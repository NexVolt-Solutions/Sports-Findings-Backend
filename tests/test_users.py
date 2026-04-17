"""
Phase 1 - User Profile Tests
Tests for: get profile, update profile, follow/unfollow
"""
from io import BytesIO

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import UserStatus
from app.models.user import User
from app.utils.security import create_access_token


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


async def test_get_my_profile_authenticated(client: AsyncClient, db_session: AsyncSession):
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
    response = await client.get("/api/v1/users/me")
    assert response.status_code == 403


async def test_list_users_returns_public_users(client: AsyncClient, db_session: AsyncSession):
    requester, token = await create_active_user(db_session, "browse@example.com", "Requester")
    target_one, _ = await create_active_user(db_session, "player1@example.com", "Player One")
    target_two, _ = await create_active_user(db_session, "player2@example.com", "Player Two")

    response = await client.get(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    ids = [item["id"] for item in data["items"]]
    assert str(requester.id) not in ids
    assert str(target_one.id) in ids
    assert str(target_two.id) in ids
    assert all("email" not in item for item in data["items"])


async def test_list_users_search_filters_results(client: AsyncClient, db_session: AsyncSession):
    requester, token = await create_active_user(db_session, "searcher@example.com", "Searcher")
    await create_active_user(db_session, "ali@example.com", "Ali Khan")
    await create_active_user(db_session, "sara@example.com", "Sara Noor")

    response = await client.get(
        "/api/v1/users?search=Ali",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["full_name"] == "Ali Khan"


async def test_update_profile_name(client: AsyncClient, db_session: AsyncSession):
    user, token = await create_active_user(db_session, "update@example.com", "Old Name")
    response = await client.put(
        "/api/v1/users/me",
        data={"full_name": "New Name"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["full_name"] == "New Name"


async def test_update_profile_sports(client: AsyncClient, db_session: AsyncSession):
    user, token = await create_active_user(db_session, "sports@example.com", "Sports User")
    response = await client.put(
        "/api/v1/users/me",
        data={
            "sports": '[{"sport": "BASKETBALL", "skill_level": "INTERMEDIATE"}, {"sport": "FOOTBALL", "skill_level": "BEGINNER"}]'
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    sports = response.json()["sports"]
    assert len(sports) == 2
    sport_names = [s["sport"] for s in sports]
    assert "BASKETBALL" in sport_names
    assert "FOOTBALL" in sport_names


async def test_update_bio(client: AsyncClient, db_session: AsyncSession):
    user, token = await create_active_user(db_session, "bio@example.com", "Bio User")
    response = await client.put(
        "/api/v1/users/me",
        data={"bio": "Love playing sports!"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["bio"] == "Love playing sports!"


async def test_update_profile_with_avatar_in_single_request(client: AsyncClient, db_session: AsyncSession):
    user, token = await create_active_user(db_session, "avatar@example.com", "Avatar User")
    response = await client.put(
        "/api/v1/users/me",
        data={
            "full_name": "Updated Avatar User",
            "bio": "Ready to play",
        },
        files={"avatar": ("avatar.png", BytesIO(b"\x89PNG\r\n\x1a\nfakepng"), "image/png")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["full_name"] == "Updated Avatar User"
    assert data["bio"] == "Ready to play"
    assert data["avatar_url"] is not None
    assert "/uploads/avatars/" in data["avatar_url"]


async def test_get_other_user_profile(client: AsyncClient, db_session: AsyncSession):
    viewer, viewer_token = await create_active_user(db_session, "viewer@example.com", "Viewer")
    target, _ = await create_active_user(db_session, "target@example.com", "Target User")

    response = await client.get(
        f"/api/v1/users/{target.id}",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["full_name"] == "Target User"
    assert "total_games_played" in data
    assert "avg_rating" in data
    assert "total_reviews" in data
    assert "reviews" in data
    assert isinstance(data["reviews"], list)
    assert "email" not in data


async def test_get_nonexistent_user_profile(client: AsyncClient, db_session: AsyncSession):
    user, token = await create_active_user(db_session, "requester@example.com", "Requester")
    import uuid

    fake_id = uuid.uuid4()
    response = await client.get(
        f"/api/v1/users/{fake_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


async def test_follow_user(client: AsyncClient, db_session: AsyncSession):
    follower, follower_token = await create_active_user(db_session, "follower@example.com", "Follower")
    followee, _ = await create_active_user(db_session, "followee@example.com", "Followee")

    response = await client.post(
        f"/api/v1/users/{followee.id}/follow",
        headers={"Authorization": f"Bearer {follower_token}"},
    )
    assert response.status_code == 201


async def test_follow_self_should_fail(client: AsyncClient, db_session: AsyncSession):
    user, token = await create_active_user(db_session, "selffollow@example.com", "Self")
    response = await client.post(
        f"/api/v1/users/{user.id}/follow",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400


async def test_follow_duplicate_should_fail(client: AsyncClient, db_session: AsyncSession):
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
    user, token = await create_active_user(db_session, "notfollowing@example.com", "NotFollowing")
    other, _ = await create_active_user(db_session, "notfollowed@example.com", "NotFollowed")

    response = await client.delete(
        f"/api/v1/users/{other.id}/follow",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400


async def test_update_profile_rejects_json_format(client: AsyncClient, db_session: AsyncSession):
    user, token = await create_active_user(db_session, "json@example.com", "JSON User")
    response = await client.put(
        "/api/v1/users/me",
        json={"full_name": "New Name"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
    assert "Unsupported content type" in response.json()["detail"]


async def test_update_profile_field_validation(client: AsyncClient, db_session: AsyncSession):
    user, token = await create_active_user(db_session, "validation@example.com", "Validation User")
    
    # Test full_name too long
    response = await client.put(
        "/api/v1/users/me",
        data={"full_name": "A" * 101},  # 101 chars, exceeds limit
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422  # Validation error
    
    # Test bio too long
    response = await client.put(
        "/api/v1/users/me",
        data={"bio": "A" * 501},  # 501 chars, exceeds limit
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422  # Validation error
