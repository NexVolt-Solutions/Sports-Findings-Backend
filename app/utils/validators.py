"""
app/utils/validators.py
-----------------------
Shared validation helpers used across services.
Centralises common checks so they are not duplicated.
"""
from datetime import datetime, timezone
from app.utils.exceptions import bad_request


def require_future_datetime(dt: datetime, field_name: str = "scheduled_at") -> datetime:
    """
    Validate that a datetime is in the future.
    Raises HTTP 400 if the datetime is in the past or present.
    Makes naive datetimes timezone-aware (UTC).
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    if dt <= datetime.now(timezone.utc):
        raise bad_request(
            f"'{field_name}' must be a future date and time. "
            f"Received: {dt.isoformat()}"
        )
    return dt


def sanitize_string(value: str, max_length: int = 500) -> str:
    """
    Strip leading/trailing whitespace and enforce max length.
    Returns cleaned string or raises HTTP 400.
    """
    value = value.strip()
    if len(value) > max_length:
        raise bad_request(f"Input too long — maximum {max_length} characters allowed.")
    return value


def validate_pagination_limit(limit: int, max_limit: int = 100) -> int:
    """
    Clamp pagination limit to max_limit.
    Returns clamped value without raising — API spec says clamp silently.
    """
    return min(limit, max_limit)
