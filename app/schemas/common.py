from typing import TypeVar, Generic, Sequence
from pydantic import BaseModel

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """
    Standard pagination envelope for all list endpoints.
    All paginated endpoints return this structure.
    """
    items: Sequence[T]
    total: int
    page: int
    limit: int
    has_next: bool
    has_prev: bool

    model_config = {"arbitrary_types_allowed": True}


class MessageResponse(BaseModel):
    """Generic message response for simple confirmations."""
    message: str
