from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ─── Application ──────────────────────────────────────────────────────────
    app_name: str = "Sports Platform"
    app_version: str = "1.0.0"
    debug: bool = False
    environment: str = "development"
    app_base_url: str = "http://localhost:8000"

    # ─── Database ─────────────────────────────────────────────────────────────
    database_url: str

    # ─── JWT ──────────────────────────────────────────────────────────────────
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30

    # ─── Google OAuth ─────────────────────────────────────────────────────────
    google_client_id: str = ""
    google_client_secret: str = ""

    # ─── Google Maps ──────────────────────────────────────────────────────────
    google_maps_api_key: str = ""

    # ─── Email ────────────────────────────────────────────────────────────────
    mail_username: str = ""
    mail_password: str = ""
    mail_from: str = ""
    mail_port: int = 587
    mail_server: str = "smtp.gmail.com"
    mail_starttls: bool = True
    mail_ssl_tls: bool = False

    # ─── Firebase ─────────────────────────────────────────────────────────────
    firebase_credentials_path: str = "firebase_credentials.json"

    # ─── Cloudinary ───────────────────────────────────────────────────────────
    cloudinary_cloud_name: str = ""
    cloudinary_api_key: str = ""
    cloudinary_api_secret: str = ""

    # ─── Rate Limiting ────────────────────────────────────────────────────────
    rate_limit_auth: str = "5/minute"
    rate_limit_general: str = "60/minute"

    # ─── Pagination ───────────────────────────────────────────────────────────
    default_page_size: int = 20
    max_page_size: int = 100


@lru_cache()
def get_settings() -> Settings:
    """
    Returns a cached Settings instance.
    Using lru_cache ensures the .env file is only read once.
    """
    return Settings()


settings = get_settings()
