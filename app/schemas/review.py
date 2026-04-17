import uuid
from datetime import datetime
from pydantic import BaseModel, field_validator


class UserSummaryResponse(BaseModel):
    """
    Lightweight user object used inside nested responses.
    Never exposes sensitive fields.
    """
    id: uuid.UUID
    full_name: str
    avatar_url: str | None
    avg_rating: float
    model_config = {"from_attributes": True}


class CreateReviewRequest(BaseModel):
    match_id: uuid.UUID
    rating: int
    comment: str | None = None

    @field_validator("rating")
    @classmethod
    def validate_rating(cls, v: int) -> int:
        if v < 1 or v > 5:
            raise ValueError("Rating must be between 1 and 5")
        return v

    @field_validator("comment")
    @classmethod
    def validate_comment(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            if len(v) > 500:
                raise ValueError("Review comment must be at most 500 characters")
        return v


class ReviewResponse(BaseModel):
    id: uuid.UUID
    reviewer: UserSummaryResponse
    rating: int
    comment: str | None
    created_at: datetime
    model_config = {"from_attributes": True}

