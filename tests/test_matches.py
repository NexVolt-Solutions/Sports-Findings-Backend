"""
Phase 2 — Match Tests
Tests for: create, get, update, delete, join, leave, remove player,
           status transitions (Start Game, Complete, Cancel), my matches
"""
import uuid
import pytest
from datetime import datetime, timedelta, timezone
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.enums import UserStatus
from app.utils.security import create_access_token, hash_password


# ─── Helpers ──────────────────────────────────────────────────────────────────

def future_datetime(hours: int = 24) -> str:
    """Returns an ISO 8601 datetime in the future."""
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


async def make_user(db: AsyncSession, email: str, name: str = "Test User") -> tuple[User, str]:
    """Create an ACTIVE user and return (user, access_token)."""
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


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def match_payload(**overrides) -> dict:
    base = {
        "title": "Evening Football",
        "description": "Casual match at the park",
        "sport": "Football",
        "facility_address": "Nørrebrogade 285, 2200 Nørrebro",
        "scheduled_at": future_datetime(24),
        "duration_minutes": 90,
        "max_players": 10,
        "skill_level": "Intermediate",
    }
    base.update(overrides)
    return base


def match_payload_from_ui(**overrides) -> dict:
    base = {
        "title": "Final Tournament",
        "description": "Describe your match...",
        "sport": "Cricket",
        "location": "Peshawar Sports Complex",
        "date": "2026-06-16",
        "time": "18:30",
        "duration_minutes": 90,
        "max_players": 10,
    }
    base.update(overrides)
    return base


# ─── Create Match ─────────────────────────────────────────────────────────────

async def test_create_match_success(client: AsyncClient, db_session: AsyncSession):
    """Host should be able to create a match."""
    host, token = await make_user(db_session, "host_create@example.com", "Host User")
    response = await client.post(
        "/api/v1/matches",
        json=match_payload(),
        headers=auth(token),
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Evening Football"
    assert data["status"] == "Open"
    assert data["current_players"] == 1          # Host auto-joined
    assert data["host"]["id"] == str(host.id)


async def test_create_match_host_auto_joined(client: AsyncClient, db_session: AsyncSession):
    """Host should appear in the match player list after creation."""
    host, token = await make_user(db_session, "host_autojoin@example.com", "AutoJoin Host")
    create_resp = await client.post(
        "/api/v1/matches",
        json=match_payload(),
        headers=auth(token),
    )
    match_id = create_resp.json()["id"]

    players_resp = await client.get(
        f"/api/v1/matches/{match_id}/players",
        headers=auth(token),
    )
    assert players_resp.status_code == 200
    player_ids = [p["user"]["id"] for p in players_resp.json()["items"]]
    assert str(host.id) in player_ids


async def test_create_match_host_role_in_players(client: AsyncClient, db_session: AsyncSession):
    """Host player record should have role=Host."""
    host, token = await make_user(db_session, "host_role@example.com", "Role Host")
    create_resp = await client.post(
        "/api/v1/matches",
        json=match_payload(),
        headers=auth(token),
    )
    match_id = create_resp.json()["id"]

    players_resp = await client.get(
        f"/api/v1/matches/{match_id}/players",
        headers=auth(token),
    )
    players = players_resp.json()["items"]
    host_entry = next(p for p in players if p["user"]["id"] == str(host.id))
    assert host_entry["role"] == "Host"


async def test_create_match_appears_in_my_matches(client: AsyncClient, db_session: AsyncSession):
    """Newly created match should appear in host's My Matches."""
    host, token = await make_user(db_session, "host_mymatches@example.com", "My Matches Host")
    create_resp = await client.post(
        "/api/v1/matches",
        json=match_payload(),
        headers=auth(token),
    )
    match_id = create_resp.json()["id"]

    my_resp = await client.get("/api/v1/matches?type=my", headers=auth(token))
    assert my_resp.status_code == 200
    ids = [m["id"] for m in my_resp.json()["items"]]
    assert match_id in ids


async def test_create_match_missing_required_field(client: AsyncClient, db_session: AsyncSession):
    """Missing required field should return 422."""
    _, token = await make_user(db_session, "miss_field@example.com")
    payload = match_payload()
    del payload["title"]
    response = await client.post("/api/v1/matches", json=payload, headers=auth(token))
    assert response.status_code == 422


async def test_create_match_invalid_max_players(client: AsyncClient, db_session: AsyncSession):
    """max_players < 2 should fail validation."""
    _, token = await make_user(db_session, "invalid_players@example.com")
    response = await client.post(
        "/api/v1/matches",
        json=match_payload(max_players=1),
        headers=auth(token),
    )
    assert response.status_code == 422


async def test_create_match_accepts_ui_payload_shape(client: AsyncClient, db_session: AsyncSession):
    """Create Match should accept date/time/location fields from the UI form."""
    host, token = await make_user(db_session, "host_ui_create@example.com", "UI Host")
    response = await client.post(
        "/api/v1/matches",
        json=match_payload_from_ui(),
        headers=auth(token),
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Final Tournament"
    assert data["sport"] == "Cricket"
    assert data["location"] == "Peshawar Sports Complex"
    assert data["facility_address"] == "Peshawar Sports Complex"
    assert data["scheduled_date"] == "2026-06-16"
    assert data["scheduled_time"] == "18:30"
    assert data["skill_level"] == "Intermediate"


async def test_create_match_accepts_frontend_place_coordinates(client: AsyncClient, db_session: AsyncSession):
    """Frontend-selected location coordinates should be persisted directly."""
    host, token = await make_user(db_session, "coords_create@example.com", "Coords Host")
    response = await client.post(
        "/api/v1/matches",
        json=match_payload(
            facility_address="Peshawar Sports Complex",
            location_name="Peshawar Sports Complex",
            latitude=34.0151,
            longitude=71.5249,
        ),
        headers=auth(token),
    )
    assert response.status_code == 201
    data = response.json()
    assert data["location_name"] == "Peshawar Sports Complex"
    assert data["latitude"] == 34.0151
    assert data["longitude"] == 71.5249


async def test_create_match_unauthenticated(client: AsyncClient):
    """Unauthenticated request should be rejected."""
    response = await client.post("/api/v1/matches", json=match_payload())
    assert response.status_code == 403


# ─── Get Match ────────────────────────────────────────────────────────────────

async def test_get_match_by_id(client: AsyncClient, db_session: AsyncSession):
    """Should return full match details."""
    host, token = await make_user(db_session, "get_match@example.com")
    create_resp = await client.post("/api/v1/matches", json=match_payload(), headers=auth(token))
    match_id = create_resp.json()["id"]

    response = await client.get(f"/api/v1/matches/{match_id}", headers=auth(token))
    assert response.status_code == 200
    assert response.json()["id"] == match_id


async def test_get_match_includes_host_games_played(client: AsyncClient, db_session: AsyncSession):
    """Match details should expose the host's played-match count consistently."""
    host, token = await make_user(db_session, "get_match_host_stats@example.com", "Stats Host")
    host.total_games_played = 14
    await db_session.commit()
    await db_session.refresh(host)

    create_resp = await client.post("/api/v1/matches", json=match_payload(), headers=auth(token))
    match_id = create_resp.json()["id"]

    response = await client.get(f"/api/v1/matches/{match_id}", headers=auth(token))
    assert response.status_code == 200
    data = response.json()
    assert data["host_games_played"] == 14
    assert data["host"]["total_games_played"] == 14


async def test_get_match_returns_all_participants(client: AsyncClient, db_session: AsyncSession):
    """Match details should return a complete participant list including the host."""
    host, host_token = await make_user(db_session, "get_match_participants_host@example.com", "Participants Host")
    player_one, player_one_token = await make_user(db_session, "get_match_participants_p1@example.com", "Player One")
    player_two, player_two_token = await make_user(db_session, "get_match_participants_p2@example.com", "Player Two")

    create_resp = await client.post("/api/v1/matches", json=match_payload(), headers=auth(host_token))
    match_id = create_resp.json()["id"]

    await client.post(f"/api/v1/matches/{match_id}/join", headers=auth(player_one_token))
    await client.post(f"/api/v1/matches/{match_id}/join", headers=auth(player_two_token))

    response = await client.get(f"/api/v1/matches/{match_id}", headers=auth(host_token))
    assert response.status_code == 200
    data = response.json()

    participant_ids = {participant["user"]["id"] for participant in data["participants"]}
    assert participant_ids == {str(host.id), str(player_one.id), str(player_two.id)}
    assert data["current_players"] == 3


async def test_get_match_not_found(client: AsyncClient, db_session: AsyncSession):
    """Non-existent match ID should return 404."""
    _, token = await make_user(db_session, "notfound_match@example.com")
    response = await client.get(f"/api/v1/matches/{uuid.uuid4()}", headers=auth(token))
    assert response.status_code == 404


# ─── Update Match ─────────────────────────────────────────────────────────────

async def test_update_match_title(client: AsyncClient, db_session: AsyncSession):
    """Host should be able to update match title."""
    host, token = await make_user(db_session, "update_title@example.com")
    create_resp = await client.post("/api/v1/matches", json=match_payload(), headers=auth(token))
    match_id = create_resp.json()["id"]

    response = await client.put(
        f"/api/v1/matches/{match_id}",
        json={"title": "Updated Football Match"},
        headers=auth(token),
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Updated Football Match"


async def test_update_match_non_host_forbidden(client: AsyncClient, db_session: AsyncSession):
    """Non-host should not be able to update match."""
    host, host_token = await make_user(db_session, "upd_host@example.com")
    other, other_token = await make_user(db_session, "upd_other@example.com")

    create_resp = await client.post("/api/v1/matches", json=match_payload(), headers=auth(host_token))
    match_id = create_resp.json()["id"]

    response = await client.put(
        f"/api/v1/matches/{match_id}",
        json={"title": "Hijacked Title"},
        headers=auth(other_token),
    )
    assert response.status_code == 403


async def test_update_match_accepts_frontend_place_coordinates(client: AsyncClient, db_session: AsyncSession):
    """Match edit should accept frontend-selected place data without relying on backend geocoding."""
    host, token = await make_user(db_session, "coords_update@example.com")
    create_resp = await client.post("/api/v1/matches", json=match_payload(), headers=auth(token))
    match_id = create_resp.json()["id"]

    response = await client.put(
        f"/api/v1/matches/{match_id}",
        json={
            "facility_address": "Islamabad Sports Arena",
            "location_name": "Islamabad Sports Arena",
            "latitude": 33.6844,
            "longitude": 73.0479,
        },
        headers=auth(token),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["facility_address"] == "Islamabad Sports Arena"
    assert data["location_name"] == "Islamabad Sports Arena"
    assert data["latitude"] == 33.6844
    assert data["longitude"] == 73.0479


# ─── Delete Match ─────────────────────────────────────────────────────────────

async def test_delete_match_host_only(client: AsyncClient, db_session: AsyncSession):
    """Host should be able to delete their match."""
    host, token = await make_user(db_session, "del_match@example.com")
    create_resp = await client.post("/api/v1/matches", json=match_payload(), headers=auth(token))
    match_id = create_resp.json()["id"]

    del_resp = await client.delete(f"/api/v1/matches/{match_id}", headers=auth(token))
    assert del_resp.status_code == 204

    get_resp = await client.get(f"/api/v1/matches/{match_id}", headers=auth(token))
    assert get_resp.status_code == 404


async def test_delete_match_non_host_forbidden(client: AsyncClient, db_session: AsyncSession):
    """Non-host should not be able to delete a match."""
    host, host_token = await make_user(db_session, "del_host2@example.com")
    other, other_token = await make_user(db_session, "del_other2@example.com")

    create_resp = await client.post("/api/v1/matches", json=match_payload(), headers=auth(host_token))
    match_id = create_resp.json()["id"]

    response = await client.delete(f"/api/v1/matches/{match_id}", headers=auth(other_token))
    assert response.status_code == 403


# ─── Join Match ───────────────────────────────────────────────────────────────

async def test_join_match_success(client: AsyncClient, db_session: AsyncSession):
    """Player should be able to join an open match."""
    host, host_token = await make_user(db_session, "join_host@example.com")
    player, player_token = await make_user(db_session, "join_player@example.com")

    create_resp = await client.post("/api/v1/matches", json=match_payload(), headers=auth(host_token))
    match_id = create_resp.json()["id"]

    response = await client.post(f"/api/v1/matches/{match_id}/join", headers=auth(player_token))
    assert response.status_code == 201

    # Player should now appear in player list
    players_resp = await client.get(f"/api/v1/matches/{match_id}/players", headers=auth(host_token))
    player_ids = [p["user"]["id"] for p in players_resp.json()["items"]]
    assert str(player.id) in player_ids


async def test_join_match_current_players_increments(client: AsyncClient, db_session: AsyncSession):
    """current_players count should increase after a player joins."""
    host, host_token = await make_user(db_session, "count_host@example.com")
    player, player_token = await make_user(db_session, "count_player@example.com")

    create_resp = await client.post("/api/v1/matches", json=match_payload(), headers=auth(host_token))
    match_id = create_resp.json()["id"]
    assert create_resp.json()["current_players"] == 1

    await client.post(f"/api/v1/matches/{match_id}/join", headers=auth(player_token))

    get_resp = await client.get(f"/api/v1/matches/{match_id}", headers=auth(host_token))
    assert get_resp.json()["current_players"] == 2


async def test_join_match_already_joined(client: AsyncClient, db_session: AsyncSession):
    """Joining a match twice should return 409."""
    host, host_token = await make_user(db_session, "dbl_host@example.com")
    player, player_token = await make_user(db_session, "dbl_player@example.com")

    create_resp = await client.post("/api/v1/matches", json=match_payload(), headers=auth(host_token))
    match_id = create_resp.json()["id"]

    await client.post(f"/api/v1/matches/{match_id}/join", headers=auth(player_token))
    response = await client.post(f"/api/v1/matches/{match_id}/join", headers=auth(player_token))
    assert response.status_code == 409


async def test_join_match_becomes_full(client: AsyncClient, db_session: AsyncSession):
    """Match status should become FULL when last slot is filled."""
    host, host_token = await make_user(db_session, "full_host@example.com")
    player, player_token = await make_user(db_session, "full_player@example.com")

    # Create match with max 2 players (host fills 1)
    create_resp = await client.post(
        "/api/v1/matches",
        json=match_payload(max_players=2),
        headers=auth(host_token),
    )
    match_id = create_resp.json()["id"]

    await client.post(f"/api/v1/matches/{match_id}/join", headers=auth(player_token))

    get_resp = await client.get(f"/api/v1/matches/{match_id}", headers=auth(host_token))
    assert get_resp.json()["status"] == "Full"


async def test_join_full_match_rejected(client: AsyncClient, db_session: AsyncSession):
    """Joining a full match should return 409."""
    host, host_token = await make_user(db_session, "full2_host@example.com")
    p1, p1_token = await make_user(db_session, "full2_p1@example.com")
    p2, p2_token = await make_user(db_session, "full2_p2@example.com")

    create_resp = await client.post(
        "/api/v1/matches",
        json=match_payload(max_players=2),
        headers=auth(host_token),
    )
    match_id = create_resp.json()["id"]

    await client.post(f"/api/v1/matches/{match_id}/join", headers=auth(p1_token))
    response = await client.post(f"/api/v1/matches/{match_id}/join", headers=auth(p2_token))
    assert response.status_code == 409


# ─── Leave Match ──────────────────────────────────────────────────────────────

async def test_leave_match_success(client: AsyncClient, db_session: AsyncSession):
    """Player should be able to leave a match they joined."""
    host, host_token = await make_user(db_session, "leave_host@example.com")
    player, player_token = await make_user(db_session, "leave_player@example.com")

    create_resp = await client.post("/api/v1/matches", json=match_payload(), headers=auth(host_token))
    match_id = create_resp.json()["id"]

    await client.post(f"/api/v1/matches/{match_id}/join", headers=auth(player_token))
    response = await client.delete(f"/api/v1/matches/{match_id}/leave", headers=auth(player_token))
    assert response.status_code == 200


async def test_leave_reopens_full_match(client: AsyncClient, db_session: AsyncSession):
    """Leaving a full match should reopen a slot (FULL → OPEN)."""
    host, host_token = await make_user(db_session, "reopen_host@example.com")
    player, player_token = await make_user(db_session, "reopen_player@example.com")

    create_resp = await client.post(
        "/api/v1/matches",
        json=match_payload(max_players=2),
        headers=auth(host_token),
    )
    match_id = create_resp.json()["id"]

    await client.post(f"/api/v1/matches/{match_id}/join", headers=auth(player_token))
    assert (await client.get(f"/api/v1/matches/{match_id}", headers=auth(host_token))).json()["status"] == "Full"

    await client.delete(f"/api/v1/matches/{match_id}/leave", headers=auth(player_token))
    assert (await client.get(f"/api/v1/matches/{match_id}", headers=auth(host_token))).json()["status"] == "Open"


async def test_host_cannot_leave(client: AsyncClient, db_session: AsyncSession):
    """Host trying to leave their own match should return 403."""
    host, host_token = await make_user(db_session, "host_leave@example.com")
    create_resp = await client.post("/api/v1/matches", json=match_payload(), headers=auth(host_token))
    match_id = create_resp.json()["id"]

    response = await client.delete(f"/api/v1/matches/{match_id}/leave", headers=auth(host_token))
    assert response.status_code == 403


# ─── Remove Player ────────────────────────────────────────────────────────────

async def test_remove_player_success(client: AsyncClient, db_session: AsyncSession):
    """Host should be able to remove a player."""
    host, host_token = await make_user(db_session, "rm_host@example.com")
    player, player_token = await make_user(db_session, "rm_player@example.com")

    create_resp = await client.post("/api/v1/matches", json=match_payload(), headers=auth(host_token))
    match_id = create_resp.json()["id"]

    await client.post(f"/api/v1/matches/{match_id}/join", headers=auth(player_token))

    response = await client.delete(
        f"/api/v1/matches/{match_id}/players/{player.id}",
        headers=auth(host_token),
    )
    assert response.status_code == 200

    # Player should no longer appear in player list
    players_resp = await client.get(f"/api/v1/matches/{match_id}/players", headers=auth(host_token))
    player_ids = [p["user"]["id"] for p in players_resp.json()["items"]]
    assert str(player.id) not in player_ids


async def test_remove_player_reopens_full_slot(client: AsyncClient, db_session: AsyncSession):
    """Removing a player from a full match should reopen a slot."""
    host, host_token = await make_user(db_session, "rmfull_host@example.com")
    player, player_token = await make_user(db_session, "rmfull_player@example.com")

    create_resp = await client.post(
        "/api/v1/matches",
        json=match_payload(max_players=2),
        headers=auth(host_token),
    )
    match_id = create_resp.json()["id"]

    await client.post(f"/api/v1/matches/{match_id}/join", headers=auth(player_token))
    assert (await client.get(f"/api/v1/matches/{match_id}", headers=auth(host_token))).json()["status"] == "Full"

    await client.delete(f"/api/v1/matches/{match_id}/players/{player.id}", headers=auth(host_token))
    assert (await client.get(f"/api/v1/matches/{match_id}", headers=auth(host_token))).json()["status"] == "Open"


async def test_non_host_cannot_remove_player(client: AsyncClient, db_session: AsyncSession):
    """Non-host trying to remove a player should return 403."""
    host, host_token = await make_user(db_session, "rmguard_host@example.com")
    other, other_token = await make_user(db_session, "rmguard_other@example.com")
    player, player_token = await make_user(db_session, "rmguard_player@example.com")

    create_resp = await client.post("/api/v1/matches", json=match_payload(), headers=auth(host_token))
    match_id = create_resp.json()["id"]
    await client.post(f"/api/v1/matches/{match_id}/join", headers=auth(player_token))

    response = await client.delete(
        f"/api/v1/matches/{match_id}/players/{player.id}",
        headers=auth(other_token),
    )
    assert response.status_code == 403


async def test_host_cannot_remove_self(client: AsyncClient, db_session: AsyncSession):
    """Host trying to remove themselves should return 400."""
    host, host_token = await make_user(db_session, "rmself_host@example.com")
    create_resp = await client.post("/api/v1/matches", json=match_payload(), headers=auth(host_token))
    match_id = create_resp.json()["id"]

    response = await client.delete(
        f"/api/v1/matches/{match_id}/players/{host.id}",
        headers=auth(host_token),
    )
    assert response.status_code == 400


# ─── Match Status Transitions ─────────────────────────────────────────────────

async def test_start_game_open_match(client: AsyncClient, db_session: AsyncSession):
    """Host should be able to start a match that is OPEN (slots not full)."""
    host, token = await make_user(db_session, "start_open@example.com")
    create_resp = await client.post("/api/v1/matches", json=match_payload(), headers=auth(token))
    match_id = create_resp.json()["id"]

    response = await client.patch(
        f"/api/v1/matches/{match_id}/status",
        json={"status": "Ongoing"},
        headers=auth(token),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "Ongoing"


async def test_start_game_full_match(client: AsyncClient, db_session: AsyncSession):
    """Host should be able to start a match even when it is FULL."""
    host, host_token = await make_user(db_session, "start_full_host@example.com")
    player, player_token = await make_user(db_session, "start_full_player@example.com")

    create_resp = await client.post(
        "/api/v1/matches",
        json=match_payload(max_players=2),
        headers=auth(host_token),
    )
    match_id = create_resp.json()["id"]
    await client.post(f"/api/v1/matches/{match_id}/join", headers=auth(player_token))

    response = await client.patch(
        f"/api/v1/matches/{match_id}/status",
        json={"status": "Ongoing"},
        headers=auth(host_token),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "Ongoing"


async def test_complete_ongoing_match(client: AsyncClient, db_session: AsyncSession):
    """Host should be able to mark an ONGOING match as COMPLETED."""
    host, token = await make_user(db_session, "complete_host@example.com")
    create_resp = await client.post("/api/v1/matches", json=match_payload(), headers=auth(token))
    match_id = create_resp.json()["id"]

    await client.patch(f"/api/v1/matches/{match_id}/status", json={"status": "Ongoing"}, headers=auth(token))
    response = await client.patch(
        f"/api/v1/matches/{match_id}/status",
        json={"status": "Completed"},
        headers=auth(token),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "Completed"


async def test_cancel_open_match(client: AsyncClient, db_session: AsyncSession):
    """Host should be able to cancel an OPEN match."""
    host, token = await make_user(db_session, "cancel_host@example.com")
    create_resp = await client.post("/api/v1/matches", json=match_payload(), headers=auth(token))
    match_id = create_resp.json()["id"]

    response = await client.patch(
        f"/api/v1/matches/{match_id}/status",
        json={"status": "Cancelled"},
        headers=auth(token),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "Cancelled"


async def test_invalid_status_transition(client: AsyncClient, db_session: AsyncSession):
    """Invalid status transition should return 400."""
    host, token = await make_user(db_session, "invalid_trans@example.com")
    create_resp = await client.post("/api/v1/matches", json=match_payload(), headers=auth(token))
    match_id = create_resp.json()["id"]

    # Cannot go directly from OPEN → COMPLETED
    response = await client.patch(
        f"/api/v1/matches/{match_id}/status",
        json={"status": "Completed"},
        headers=auth(token),
    )
    assert response.status_code == 400


async def test_non_host_cannot_start_game(client: AsyncClient, db_session: AsyncSession):
    """Non-host trying to start a game should return 403."""
    host, host_token = await make_user(db_session, "start_guard_host@example.com")
    other, other_token = await make_user(db_session, "start_guard_other@example.com")

    create_resp = await client.post("/api/v1/matches", json=match_payload(), headers=auth(host_token))
    match_id = create_resp.json()["id"]

    response = await client.patch(
        f"/api/v1/matches/{match_id}/status",
        json={"status": "Ongoing"},
        headers=auth(other_token),
    )
    assert response.status_code == 403


async def test_join_ongoing_match_rejected(client: AsyncClient, db_session: AsyncSession):
    """Joining a match that has already started should be rejected."""
    host, host_token = await make_user(db_session, "ongoing_join_host@example.com")
    late, late_token = await make_user(db_session, "ongoing_join_late@example.com")

    create_resp = await client.post("/api/v1/matches", json=match_payload(), headers=auth(host_token))
    match_id = create_resp.json()["id"]

    await client.patch(
        f"/api/v1/matches/{match_id}/status",
        json={"status": "Ongoing"},
        headers=auth(host_token),
    )

    response = await client.post(f"/api/v1/matches/{match_id}/join", headers=auth(late_token))
    assert response.status_code == 409


# ─── My Matches ───────────────────────────────────────────────────────────────

async def test_my_matches_includes_joined(client: AsyncClient, db_session: AsyncSession):
    """My Matches should include matches where the user is a participant."""
    host, host_token = await make_user(db_session, "mymatches_host@example.com")
    player, player_token = await make_user(db_session, "mymatches_player@example.com")

    create_resp = await client.post("/api/v1/matches", json=match_payload(), headers=auth(host_token))
    match_id = create_resp.json()["id"]
    await client.post(f"/api/v1/matches/{match_id}/join", headers=auth(player_token))

    response = await client.get("/api/v1/matches?type=my", headers=auth(player_token))
    assert response.status_code == 200
    ids = [m["id"] for m in response.json()["items"]]
    assert match_id in ids


async def test_my_matches_excludes_left(client: AsyncClient, db_session: AsyncSession):
    """Matches the user has left should not appear in My Matches."""
    host, host_token = await make_user(db_session, "exleft_host@example.com")
    player, player_token = await make_user(db_session, "exleft_player@example.com")

    create_resp = await client.post("/api/v1/matches", json=match_payload(), headers=auth(host_token))
    match_id = create_resp.json()["id"]

    await client.post(f"/api/v1/matches/{match_id}/join", headers=auth(player_token))
    await client.delete(f"/api/v1/matches/{match_id}/leave", headers=auth(player_token))

    response = await client.get("/api/v1/matches?type=my", headers=auth(player_token))
    ids = [m["id"] for m in response.json()["items"]]
    assert match_id not in ids


# ─── List Matches ─────────────────────────────────────────────────────────────

async def test_list_matches_returns_open(client: AsyncClient, db_session: AsyncSession):
    """List endpoint should return at least the match just created."""
    host, token = await make_user(db_session, "list_host@example.com")
    create_resp = await client.post("/api/v1/matches", json=match_payload(), headers=auth(token))
    match_id = create_resp.json()["id"]

    response = await client.get("/api/v1/matches", headers=auth(token))
    assert response.status_code == 200
    ids = [m["id"] for m in response.json()["items"]]
    assert match_id in ids


async def test_list_matches_sport_filter(client: AsyncClient, db_session: AsyncSession):
    """Sport filter should exclude non-matching matches."""
    host, token = await make_user(db_session, "filter_host@example.com")
    await client.post("/api/v1/matches", json=match_payload(sport="Basketball"), headers=auth(token))

    response = await client.get("/api/v1/matches?sport=Cricket", headers=auth(token))
    assert response.status_code == 200
    for match in response.json()["items"]:
        assert match["sport"] == "Cricket"
