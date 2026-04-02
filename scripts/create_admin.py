#!/usr/bin/env python3
"""
Admin Account Creation Utility
Creates an admin account directly in the database without going through
the normal signup flow.
"""

import asyncio
import argparse
import sys
import os
import logging
import re

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# --------------------------------------------------
# Logging Setup
# --------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger(__name__)


# --------------------------------------------------
# Validation Functions
# --------------------------------------------------

def validate_email(email: str) -> bool:
    """Validate email format."""
    pattern = r"^[\w\.-]+@[\w\.-]+\.\w+$"
    return re.match(pattern, email) is not None


def normalize_email(email: str) -> str:
    """Normalize email input for consistent lookup/storage."""
    return email.strip().lower()


def validate_password(password: str) -> str | None:
    """Validate password strength."""
    if len(password) < 8:
        return "Password must be at least 8 characters long."

    if not re.search(r"[A-Z]", password):
        return "Password must contain at least one uppercase letter."

    if not re.search(r"\d", password):
        return "Password must contain at least one number."

    return None


# --------------------------------------------------
# Input Helper
# --------------------------------------------------

def prompt_input(label: str, secret: bool = False) -> str:
    """Prompt user input."""
    if secret:
        import getpass
        return getpass.getpass(f"{label}: ").strip()

    return input(f"{label}: ").strip()


# --------------------------------------------------
# Admin Creation Logic
# --------------------------------------------------

async def create_admin(email: str, full_name: str, password: str) -> None:
    """Create or upgrade admin user, enforcing a single-admin rule."""

    from sqlalchemy import select
    from app.database import AsyncSessionLocal
    from app.models.user import User
    from app.models.enums import UserStatus
    from app.utils.security import hash_password

    email = normalize_email(email)
    full_name = full_name.strip()

    # Keep in sync with `app/models/user.py` SQLAlchemy model.
    if not (2 <= len(full_name) <= 100):
        raise ValueError("Full name must be between 2 and 100 characters.")

    async with AsyncSessionLocal() as db:

        try:
            # If there are multiple admins in the DB, fail loudly to avoid
            # silently changing state and leaving the system inconsistent.
            existing_admins = (
                await db.execute(select(User).where(User.is_admin.is_(True)))
            ).scalars().all()

            if len(existing_admins) > 1:
                admin_emails = [u.email for u in existing_admins if u.email]
                raise RuntimeError(
                    "Multiple admin accounts exist in the database. "
                    f"Admins: {admin_emails}"
                )

            existing_admin = existing_admins[0] if existing_admins else None

            # Check if email already exists
            result = await db.execute(select(User).where(User.email == email))
            existing = result.scalar_one_or_none()

            if existing:

                if existing.is_admin:
                    logger.warning(f"Admin account with '{email}' already exists.")
                    return

                if existing_admin and existing_admin.id != existing.id:
                    logger.error(
                        f"Admin account '{existing_admin.email}' already exists. "
                        "Only one admin account is allowed."
                    )
                    return

                # Upgrade user to admin
                existing.is_admin = True
                existing.status = UserStatus.ACTIVE
                existing.full_name = full_name
                existing.hashed_password = hash_password(password)
                # Clear verification OTP fields since admin accounts are
                # treated as ACTIVE and should not retain OTP secrets.
                existing.email_verification_otp = None
                existing.email_verification_otp_expires_at = None

                await db.commit()

                logger.info(f"User '{email}' upgraded to admin and password refreshed.")
                return

            if existing_admin:
                logger.error(
                    f"Admin account '{existing_admin.email}' already exists. "
                    "Only one admin account is allowed."
                )
                return

            # Create new admin user
            admin_user = User(
                email=email,
                hashed_password=hash_password(password),
                full_name=full_name,
                status=UserStatus.ACTIVE,  # Skip email verification
                is_admin=True,
            )

            db.add(admin_user)

            await db.commit()
            await db.refresh(admin_user)

            logger.info("Admin account created successfully")
            logger.info(f"ID: {admin_user.id}")
            logger.info(f"Name: {admin_user.full_name}")
            logger.info(f"Email: {admin_user.email}")

            print("\nAdmin login endpoint:")
            print("POST /api/v1/auth/login")
            print("Admin dashboard endpoint:")
            print("GET /api/v1/admin/dashboard/stats\n")

        except Exception as e:

            await db.rollback()

            logger.error("Admin creation failed")
            logger.error(str(e))

            raise


# --------------------------------------------------
# Main Script
# --------------------------------------------------

def main():

    parser = argparse.ArgumentParser(
        description="Create a Sports Platform admin account.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/create_admin.py
  python scripts/create_admin.py --email admin@sportsplatform.com --name "Super Admin"
        """,
    )

    parser.add_argument("--email", help="Admin email address")
    parser.add_argument("--name", help="Admin full name")
    parser.add_argument(
        "--password",
        help="Admin password. If omitted, the script prompts securely.",
    )

    args = parser.parse_args()

    print("\n" + "=" * 50)
    print(" Sports Platform — Admin Account Creator ")
    print("=" * 50 + "\n")

    # --------------------------------------------------
    # Collect Inputs
    # --------------------------------------------------

    email = normalize_email(args.email or prompt_input("Email"))

    if not validate_email(email):
        logger.error("Invalid email address.")
        sys.exit(1)

    full_name = (args.name or prompt_input("Full name")).strip()

    if not full_name or len(full_name) < 2:
        logger.error("Full name must be at least 2 characters.")
        sys.exit(1)
    if len(full_name) > 100:
        logger.error("Full name must be at most 100 characters.")
        sys.exit(1)

    # --------------------------------------------------
    # Password
    # --------------------------------------------------
    # Refuse passing passwords via CLI by default to avoid leaking secrets
    # through shell history and process listings. Opt-in via env var.
    allow_password_arg = os.getenv("ALLOW_PASSWORD_ARG", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    if args.password is not None and not allow_password_arg:
        logger.error(
            "Refusing to accept --password via command line. "
            "Use an interactive prompt instead, or set ALLOW_PASSWORD_ARG=1."
        )
        sys.exit(1)

    password = args.password if args.password is not None else prompt_input("Password", secret=True)

    error = validate_password(password)

    if error:
        logger.error(error)
        sys.exit(1)

    confirm = args.password if args.password is not None else prompt_input("Confirm password", secret=True)

    if password != confirm:
        logger.error("Passwords do not match.")
        sys.exit(1)

    # --------------------------------------------------
    # Create Admin
    # --------------------------------------------------

    logger.info(f"Creating admin account for '{email}'")

    try:
        asyncio.run(create_admin(email, full_name, password))

    except Exception:

        logger.error("Failed to create admin account.")
        logger.error("Check database connection and environment variables.")

        sys.exit(1)


# --------------------------------------------------

if __name__ == "__main__":
    main()
