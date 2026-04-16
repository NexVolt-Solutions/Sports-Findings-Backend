"""Auth tests."""

from httpx import AsyncClient
from sqlalchemy import select

from app.models.enums import UserStatus
from app.models.user import User


def register_payload(
    *,
    full_name: str = "Ali Khan",
    email: str = "ali@example.com",
    password: str = "Secure123",
):
    return {
        "full_name": full_name,
        "email": email,
        "password": password,
        "confirm_password": password,
        "accept_terms": True,
    }


async def test_register_success(client: AsyncClient):
    response = await client.post("/api/v1/auth/register", data=register_payload())
    assert response.status_code == 201
    assert "otp" in response.json()["message"].lower()


async def test_register_duplicate_email(client: AsyncClient):
    payload = register_payload(
        email="duplicate@example.com",
    )
    await client.post("/api/v1/auth/register", data=payload)
    response = await client.post("/api/v1/auth/register", data=payload)
    assert response.status_code == 201
    assert "new 6-digit verification otp" in response.json()["message"].lower()


async def test_register_weak_password(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/register",
        data=register_payload(
            email="weak@example.com",
            password="abc",
        ),
    )
    assert response.status_code == 422


async def test_register_missing_uppercase(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/register",
        data=register_payload(
            email="noup@example.com",
            password="lowercase1",
        ),
    )
    assert response.status_code == 422


async def test_register_invalid_email(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/register",
        data=register_payload(
            email="not-an-email",
        ),
    )
    assert response.status_code == 422


async def test_login_unverified_user(client: AsyncClient):
    await client.post(
        "/api/v1/auth/register",
        data=register_payload(
            full_name="Unverified User",
            email="unverified@example.com",
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
        data=register_payload(
            full_name="Test User",
            email="wrongpass@example.com",
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
        data=register_payload(
            full_name="Verify User",
            email=email,
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


async def test_resend_verification_otp_generates_new_code(client: AsyncClient, db_session):
    email = "resend_verify@example.com"
    await client.post(
        "/api/v1/auth/register",
        data=register_payload(full_name="Resend Verify", email=email),
    )

    result = await db_session.execute(select(User).where(User.email == email))
    user = result.scalar_one()
    first_otp = user.email_verification_otp

    response = await client.post(
        "/api/v1/auth/resend-verification-otp",
        json={"email": email},
    )
    assert response.status_code == 200

    result = await db_session.execute(select(User).where(User.email == email))
    user = result.scalar_one()
    assert user.email_verification_otp is not None
    assert user.email_verification_otp != first_otp


async def test_register_verified_duplicate_email_conflict(client: AsyncClient, db_session):
    email = "verified-duplicate@example.com"
    payload = register_payload(
        full_name="Verified User",
        email=email,
    )
    await client.post("/api/v1/auth/register", data=payload)

    result = await db_session.execute(select(User).where(User.email == email))
    user = result.scalar_one()
    user.status = UserStatus.ACTIVE
    user.email_verification_otp = None
    user.email_verification_otp_expires_at = None
    await db_session.commit()

    response = await client.post("/api/v1/auth/register", data=payload)
    assert response.status_code == 409


async def test_register_duplicate_email_is_case_insensitive(client: AsyncClient):
    payload = register_payload(
        full_name="Case User",
        email="CaseSensitive@example.com",
    )
    await client.post("/api/v1/auth/register", data=payload)

    response = await client.post(
        "/api/v1/auth/register",
        data=register_payload(
            full_name="Case User",
            email="casesensitive@example.com",
        ),
    )
    assert response.status_code == 201
    assert "new 6-digit verification otp" in response.json()["message"].lower()


async def test_login_email_is_case_insensitive(client: AsyncClient, db_session):
    email = "CaseLogin@example.com"
    await client.post(
        "/api/v1/auth/register",
        data=register_payload(full_name="Case Login", email=email),
    )

    result = await db_session.execute(select(User).where(User.email == email.lower()))
    user = result.scalar_one()
    user.status = UserStatus.ACTIVE
    user.email_verification_otp = None
    user.email_verification_otp_expires_at = None
    await db_session.commit()

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "CASELOGIN@example.com", "password": "Secure123"},
    )
    assert response.status_code == 200
    assert response.json()["access_token"]


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
        data=register_payload(
            full_name="Forgot User",
            email="forgot@example.com",
        ),
    )
    response = await client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "forgot@example.com"},
    )
    assert response.status_code == 200


async def test_verify_reset_password_otp_success(client: AsyncClient, db_session):
    email = "verify_reset_otp@example.com"
    await client.post(
        "/api/v1/auth/register",
        data=register_payload(full_name="Verify Reset OTP", email=email),
    )

    result = await db_session.execute(select(User).where(User.email == email))
    user = result.scalar_one()
    user.status = UserStatus.ACTIVE
    user.email_verification_otp = None
    user.email_verification_otp_expires_at = None
    await db_session.commit()

    await client.post("/api/v1/auth/forgot-password", json={"email": email})

    result = await db_session.execute(select(User).where(User.email == email))
    user = result.scalar_one()

    response = await client.post(
        "/api/v1/auth/verify-reset-password-otp",
        json={"email": email, "otp": user.password_reset_otp},
    )
    assert response.status_code == 200
    assert "otp verified" in response.json()["message"].lower()
    assert response.json()["reset_token"]


async def test_resend_reset_password_otp_generates_new_code(client: AsyncClient, db_session):
    email = "resend_reset@example.com"
    await client.post(
        "/api/v1/auth/register",
        data=register_payload(full_name="Resend Reset", email=email),
    )

    result = await db_session.execute(select(User).where(User.email == email))
    user = result.scalar_one()
    user.status = UserStatus.ACTIVE
    user.email_verification_otp = None
    user.email_verification_otp_expires_at = None
    await db_session.commit()

    await client.post("/api/v1/auth/forgot-password", json={"email": email})

    result = await db_session.execute(select(User).where(User.email == email))
    user = result.scalar_one()
    first_otp = user.password_reset_otp

    response = await client.post(
        "/api/v1/auth/resend-reset-password-otp",
        json={"email": email},
    )
    assert response.status_code == 200

    result = await db_session.execute(select(User).where(User.email == email))
    user = result.scalar_one()
    assert user.password_reset_otp is not None
    assert user.password_reset_otp != first_otp


async def test_reset_password_with_otp_success(client: AsyncClient, db_session):
    # Register and verify a user first
    email = "reset@example.com"
    await client.post(
        "/api/v1/auth/register",
        data=register_payload(
            full_name="Reset User",
            email=email,
        ),
    )

    # Manually verify the user
    result = await db_session.execute(select(User).where(User.email == email))
    user = result.scalar_one()
    user.status = UserStatus.ACTIVE
    user.email_verification_otp = None
    user.email_verification_otp_expires_at = None
    await db_session.commit()

    # Request password reset
    await client.post(
        "/api/v1/auth/forgot-password",
        json={"email": email},
    )

    # Get the OTP from database
    result = await db_session.execute(select(User).where(User.email == email))
    user = result.scalar_one()
    otp = user.password_reset_otp

    verify_response = await client.post(
        "/api/v1/auth/verify-reset-password-otp",
        json={"email": email, "otp": otp},
    )
    reset_token = verify_response.json()["reset_token"]

    response = await client.post(
        "/api/v1/auth/reset-password",
        json={
            "reset_token": reset_token,
            "new_password": "NewSecure123",
            "confirm_password": "NewSecure123",
        },
    )
    assert response.status_code == 200
    assert "reset successfully" in response.json()["message"].lower()


async def test_reset_password_allows_login_with_new_password(client: AsyncClient, db_session):
    email = "reset_login@example.com"
    await client.post(
        "/api/v1/auth/register",
        data=register_payload(full_name="Reset Login User", email=email),
    )

    result = await db_session.execute(select(User).where(User.email == email))
    user = result.scalar_one()
    user.status = UserStatus.ACTIVE
    user.email_verification_otp = None
    user.email_verification_otp_expires_at = None
    await db_session.commit()

    await client.post(
        "/api/v1/auth/forgot-password",
        json={"email": email.upper()},
    )

    result = await db_session.execute(select(User).where(User.email == email))
    user = result.scalar_one()
    otp = user.password_reset_otp

    verify_response = await client.post(
        "/api/v1/auth/verify-reset-password-otp",
        json={"email": email.upper(), "otp": otp},
    )
    reset_token = verify_response.json()["reset_token"]

    reset_response = await client.post(
        "/api/v1/auth/reset-password",
        json={
            "reset_token": reset_token,
            "new_password": "UpdatedSecure123",
            "confirm_password": "UpdatedSecure123",
        },
    )
    assert reset_response.status_code == 200

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": email.upper(), "password": "UpdatedSecure123"},
    )
    assert login_response.status_code == 200
    assert login_response.json()["access_token"]


async def test_verify_reset_password_invalid_otp(client: AsyncClient, db_session):
    # Register and verify a user first
    email = "reset_invalid@example.com"
    await client.post(
        "/api/v1/auth/register",
        data=register_payload(
            full_name="Reset Invalid User",
            email=email,
        ),
    )

    # Manually verify the user
    result = await db_session.execute(select(User).where(User.email == email))
    user = result.scalar_one()
    user.status = UserStatus.ACTIVE
    user.email_verification_otp = None
    user.email_verification_otp_expires_at = None
    await db_session.commit()

    # Try to verify reset OTP with invalid OTP
    response = await client.post(
        "/api/v1/auth/verify-reset-password-otp",
        json={
            "email": email,
            "otp": "000000",
        },
    )
    assert response.status_code == 400


async def test_reset_password_requires_confirm_password_match(client: AsyncClient, db_session):
    email = "reset_mismatch@example.com"
    await client.post(
        "/api/v1/auth/register",
        data=register_payload(full_name="Reset Mismatch User", email=email),
    )

    result = await db_session.execute(select(User).where(User.email == email))
    user = result.scalar_one()
    user.status = UserStatus.ACTIVE
    user.email_verification_otp = None
    user.email_verification_otp_expires_at = None
    await db_session.commit()

    await client.post("/api/v1/auth/forgot-password", json={"email": email})

    result = await db_session.execute(select(User).where(User.email == email))
    user = result.scalar_one()

    verify_response = await client.post(
        "/api/v1/auth/verify-reset-password-otp",
        json={"email": email, "otp": user.password_reset_otp},
    )
    reset_token = verify_response.json()["reset_token"]

    response = await client.post(
        "/api/v1/auth/reset-password",
        json={
            "reset_token": reset_token,
            "new_password": "NewSecure123",
            "confirm_password": "Different123",
        },
    )
    assert response.status_code == 422


async def test_health_check(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
