"""Auth tests."""

from httpx import AsyncClient
from sqlalchemy import select

from app.models.enums import UserStatus
from app.models.user import User


def register_payload(
    *,
    full_name: str = "Ali Khan",
    email: str = "ali@example.com",
    phone_number: str = "+923001110000",
    password: str = "Secure123",
):
    return {
        "full_name": full_name,
        "email": email,
        "phone_number": phone_number,
        "password": password,
        "confirm_password": password,
        "avatar_url": "https://example.com/avatar.jpg",
        "accept_terms": True,
    }


async def test_register_success(client: AsyncClient):
    response = await client.post("/api/v1/auth/register", json=register_payload())
    assert response.status_code == 201
    assert "otp" in response.json()["message"].lower()


async def test_register_duplicate_email(client: AsyncClient):
    payload = register_payload(
        email="duplicate@example.com",
        phone_number="+923001110001",
    )
    await client.post("/api/v1/auth/register", json=payload)
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    assert "new 6-digit verification otp" in response.json()["message"].lower()


async def test_register_weak_password(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/register",
        json=register_payload(
            email="weak@example.com",
            phone_number="+923001110002",
            password="abc",
        ),
    )
    assert response.status_code == 422


async def test_register_missing_uppercase(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/register",
        json=register_payload(
            email="noup@example.com",
            phone_number="+923001110003",
            password="lowercase1",
        ),
    )
    assert response.status_code == 422


async def test_register_invalid_email(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/register",
        json=register_payload(
            email="not-an-email",
            phone_number="+923001110004",
        ),
    )
    assert response.status_code == 422


async def test_login_unverified_user(client: AsyncClient):
    await client.post(
        "/api/v1/auth/register",
        json=register_payload(
            full_name="Unverified User",
            email="unverified@example.com",
            phone_number="+923001110005",
        ),
    )
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "unverified@example.com", "password": "Secure123"},
    )
    assert response.status_code == 403


async def test_login_wrong_password(client: AsyncClient):
    await client.post(
        "/api/v1/auth/register",
        json=register_payload(
            full_name="Test User",
            email="wrongpass@example.com",
            phone_number="+923001110006",
        ),
    )
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "wrongpass@example.com", "password": "WrongPass999"},
    )
    assert response.status_code == 401


async def test_login_nonexistent_user(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "Secure123"},
    )
    assert response.status_code == 401


async def test_verify_email_invalid_otp(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/verify-email",
        json={"email": "missing@example.com", "otp": "123456"},
    )
    assert response.status_code == 400


async def test_verify_email_success(client: AsyncClient, db_session):
    email = "verify@example.com"
    await client.post(
        "/api/v1/auth/register",
        json=register_payload(
            full_name="Verify User",
            email=email,
            phone_number="+923001110007",
        ),
    )
    result = await db_session.execute(select(User).where(User.email == email))
    user = result.scalar_one()

    response = await client.post(
        "/api/v1/auth/verify-email",
        json={"email": email, "otp": user.email_verification_otp},
    )
    assert response.status_code == 200
    assert "verified" in response.json()["message"].lower()


async def test_register_verified_duplicate_email_conflict(client: AsyncClient, db_session):
    email = "verified-duplicate@example.com"
    payload = register_payload(
        full_name="Verified User",
        email=email,
        phone_number="+923001110009",
    )
    await client.post("/api/v1/auth/register", json=payload)

    result = await db_session.execute(select(User).where(User.email == email))
    user = result.scalar_one()
    user.status = UserStatus.ACTIVE
    user.email_verification_otp = None
    user.email_verification_otp_expires_at = None
    await db_session.commit()

    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 409


async def test_refresh_invalid_token(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "invalid.token.here"},
    )
    assert response.status_code == 401


async def test_logout_success(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": "any-token-value"},
    )
    assert response.status_code == 200
    assert "logged out" in response.json()["message"].lower()


async def test_forgot_password_unknown_email(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "unknown@example.com"},
    )
    assert response.status_code == 200


async def test_forgot_password_known_email(client: AsyncClient):
    await client.post(
        "/api/v1/auth/register",
        json=register_payload(
            full_name="Forgot User",
            email="forgot@example.com",
            phone_number="+923001110008",
        ),
    )
    response = await client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "forgot@example.com"},
    )
    assert response.status_code == 200


async def test_health_check(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
