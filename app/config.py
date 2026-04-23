from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

SPORTFINDING_GOOGLE_WEB_CLIENT_ID = (
    "147032468406-cj792ti9lqaldlonhl93p04vuui6rufv.apps.googleusercontent.com"
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    app_name: str = "Sports Platform"
    app_version: str = "1.0.0"
    debug: bool = False
    environment: str = "development"
    app_base_url: str = "http://localhost:8000"

    database_url: str

    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30

    google_client_id: str = Field(
        default=SPORTFINDING_GOOGLE_WEB_CLIENT_ID,
        validation_alias=AliasChoices(
            "GOOGLE_CLIENT_ID",
            "GOOGLE_OAUTH_CLIENT_ID",
            "GOOGLE_AUDIENCE",
            "AUDIENCE",
        ),
    )
    google_allowed_client_ids: str = Field(
        default="",
        validation_alias=AliasChoices(
            "GOOGLE_ALLOWED_CLIENT_IDS",
            "GOOGLE_OAUTH_ALLOWED_CLIENT_IDS",
        ),
    )
    google_client_secret: str = ""

    google_maps_api_key: str = ""
    geocoding_api_enabled: bool = True
    places_api_enabled: bool = True
    directions_api_enabled: bool = True
    places_search_radius: int = 5000
    directions_api_mode: str = "driving"

    mail_username: str = ""
    mail_password: str = ""
    mail_from: str = ""
    mail_port: int = 587
    mail_server: str = "smtp.gmail.com"
    mail_starttls: bool = True
    mail_ssl_tls: bool = False

    firebase_credentials_path: str = "firebase_credentials.json"

    cloudinary_cloud_name: str = ""
    cloudinary_api_key: str = ""
    cloudinary_api_secret: str = ""

    uploads_dir: str = "uploads"
    max_avatar_size_mb: int = 5

    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_s3_bucket_name: str = ""
    aws_region: str = "us-east-1"
    cloudfront_domain: str = ""

    rate_limit_auth: str = "5/minute"
    rate_limit_general: str = "60/minute"

    default_page_size: int = 20
    max_page_size: int = 100

    allow_secret_logging: bool = False

    @property
    def accepted_google_client_ids(self) -> tuple[str, ...]:
        values: list[str] = []

        if self.google_client_id.strip():
            values.append(self.google_client_id.strip())

        if self.google_allowed_client_ids.strip():
            values.extend(
                client_id.strip()
                for client_id in self.google_allowed_client_ids.split(",")
                if client_id.strip()
            )

        # Preserve order while removing duplicates.
        return tuple(dict.fromkeys(values))


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
