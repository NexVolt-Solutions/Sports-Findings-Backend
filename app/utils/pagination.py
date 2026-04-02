from typing import TypeVar, Generic, Sequence
from pydantic import BaseModel
from fastapi import Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings

T = TypeVar("T")


# ─── Pagination Query Params (Dependency) ────────────────────────────────────
class PaginationParams:
    """
    FastAPI dependency to extract and validate page & limit from query params.

    Usage in routes:
        async def list_matches(pagination: PaginationParams = Depends()):
            skip = pagination.skip
            limit = pagination.limit
    """
    def __init__(
        self,
        page: int = Query(default=1, ge=1, description="Page number starting at 1"),
        limit: int = Query(
            default=20,
            ge=1,
            le=100,
            description="Number of items per page (max 100)",
        ),
    ):
        self.page = page
        self.limit = limit

    @property
    def skip(self) -> int:
        """Returns the OFFSET value for the SQL query."""
        return (self.page - 1) * self.limit


# ─── Paginated Response Schema (Generic) ─────────────────────────────────────
class PaginatedResponse(BaseModel, Generic[T]):
    """
    Generic pagination envelope returned by all paginated endpoints.

    Example:
        PaginatedResponse[MatchSummaryResponse]
    """
    items: Sequence[T]
    total: int
    page: int
    limit: int
    has_next: bool
    has_prev: bool

    model_config = {"arbitrary_types_allowed": True}


# ─── Paginate Utility ─────────────────────────────────────────────────────────
async def paginate(
    session: AsyncSession,
    query,
    pagination: PaginationParams,
) -> PaginatedResponse:
    """
    Executes a SQLAlchemy async query with pagination and returns
    the standard PaginatedResponse envelope.

    Args:
        session:    AsyncSession — the active DB session
        query:      A SQLAlchemy select() statement (without limit/offset)
        pagination: PaginationParams — page and limit values

    Returns:
        PaginatedResponse with items, total, page, limit, has_next, has_prev
    """
    # Count total matching records
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await session.execute(count_query)
    total = total_result.scalar_one()

    # Fetch the paginated data
    paginated_query = query.offset(pagination.skip).limit(pagination.limit)
    result = await session.execute(paginated_query)
    items = result.scalars().all()

    return PaginatedResponse(
        items=items,
        total=total,
        page=pagination.page,
        limit=pagination.limit,
        has_next=(pagination.skip + pagination.limit) < total,
        has_prev=pagination.page > 1,
    )
