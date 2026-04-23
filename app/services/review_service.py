import uuid
import logging

from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.models.review import Review
from app.models.user import User
from app.schemas.review import CreateReviewRequest, ReviewResponse
from app.schemas.user import UserSummaryResponse
from app.utils.exceptions import (
    UserNotFound,
    bad_request,
    conflict,
)
from app.background.tasks import update_user_avg_rating

logger = logging.getLogger(__name__)


async def create_review(
    reviewee_id: uuid.UUID,
    payload: CreateReviewRequest,
    reviewer: User,
    db: AsyncSession,
    background_tasks: BackgroundTasks,
) -> ReviewResponse:
    """
    Submit a star rating and review for another user.
    Rules:
    - Cannot review yourself
    - Reviews are not tied to matches
    - One profile review per reviewer per reviewee
    """
    if reviewee_id == reviewer.id:
        raise bad_request("You cannot review yourself.")

    reviewee_result = await db.execute(select(User).where(User.id == reviewee_id))
    reviewee = reviewee_result.scalar_one_or_none()
    if not reviewee:
        raise UserNotFound()

    existing_review = await db.execute(
        select(Review).where(
            and_(
                Review.reviewer_id == reviewer.id,
                Review.reviewee_id == reviewee_id,
                Review.match_id.is_(None),
            )
        )
    )
    if existing_review.scalar_one_or_none():
        raise conflict(
            "You have already submitted a profile review for this user."
        )

    review = Review(
        reviewer_id=reviewer.id,
        reviewee_id=reviewee_id,
        match_id=None,
        rating=payload.rating,
        comment=payload.comment,
    )
    db.add(review)
    await db.commit()
    await db.refresh(review)

    background_tasks.add_task(update_user_avg_rating, reviewee_id)

    logger.info(
        f"Review created: reviewer={reviewer.id} reviewee={reviewee_id} "
        f"match=profile rating={payload.rating}"
    )

    return ReviewResponse(
        id=review.id,
        reviewer=UserSummaryResponse(
            id=reviewer.id,
            full_name=reviewer.full_name,
            avatar_url=reviewer.avatar_url,
            avg_rating=reviewer.avg_rating,
        ),
        rating=review.rating,
        comment=review.comment,
        created_at=review.created_at,
    )
