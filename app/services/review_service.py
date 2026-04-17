import uuid
import logging

from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.models.review import Review
from app.models.match import Match
from app.models.match_player import MatchPlayer
from app.models.user import User
from app.models.enums import MatchStatus, MatchPlayerStatus
from app.schemas.review import CreateReviewRequest, ReviewResponse
from app.schemas.user import UserSummaryResponse
from app.utils.exceptions import (
    UserNotFound,
    MatchNotFound,
    forbidden,
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
    Submit a star rating and review for another player.
    Rules:
    - Cannot review yourself
    - Match must be COMPLETED
    - Both reviewer and reviewee must have participated
    - One review per reviewer per reviewee per match
    """
    if reviewee_id == reviewer.id:
        raise bad_request("You cannot review yourself.")

    reviewee_result = await db.execute(select(User).where(User.id == reviewee_id))
    reviewee = reviewee_result.scalar_one_or_none()
    if not reviewee:
        raise UserNotFound()

    match_result = await db.execute(
        select(Match).where(Match.id == payload.match_id)
    )
    match = match_result.scalar_one_or_none()
    if not match:
        raise MatchNotFound()

    if match.status != MatchStatus.COMPLETED:
        raise bad_request(
            "Reviews can only be submitted for completed matches. "
            f"This match is currently '{match.status.value}'."
        )

    reviewer_participation = await db.execute(
        select(MatchPlayer).where(
            and_(
                MatchPlayer.match_id == payload.match_id,
                MatchPlayer.user_id == reviewer.id,
                MatchPlayer.status == MatchPlayerStatus.ACTIVE,
            )
        )
    )
    if not reviewer_participation.scalar_one_or_none():
        raise forbidden(
            "You can only review players from matches you participated in."
        )

    reviewee_participation = await db.execute(
        select(MatchPlayer).where(
            and_(
                MatchPlayer.match_id == payload.match_id,
                MatchPlayer.user_id == reviewee_id,
                MatchPlayer.status == MatchPlayerStatus.ACTIVE,
            )
        )
    )
    if not reviewee_participation.scalar_one_or_none():
        raise bad_request(
            "The player you are reviewing did not participate in this match."
        )

    existing_review = await db.execute(
        select(Review).where(
            and_(
                Review.reviewer_id == reviewer.id,
                Review.reviewee_id == reviewee_id,
                Review.match_id == payload.match_id,
            )
        )
    )
    if existing_review.scalar_one_or_none():
        raise conflict(
            "You have already submitted a review for this player for this match."
        )

    review = Review(
        reviewer_id=reviewer.id,
        reviewee_id=reviewee_id,
        match_id=payload.match_id,
        rating=payload.rating,
        comment=payload.comment,
    )
    db.add(review)
    await db.commit()
    await db.refresh(review)

    background_tasks.add_task(update_user_avg_rating, reviewee_id)

    logger.info(
        f"Review created: reviewer={reviewer.id} reviewee={reviewee_id} "
        f"match={payload.match_id} rating={payload.rating}"
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

