# Import all models here so Alembic can autodiscover them
# during migration generation (alembic revision --autogenerate)

from app.models.user import User, UserSport
from app.models.follow import Follow
from app.models.match import Match
from app.models.match_player import MatchPlayer
from app.models.message import Message
from app.models.review import Review
from app.models.notification import Notification
from app.models.content_page import ContentPage
from app.models.support_request import SupportRequest

__all__ = [
    "User",
    "UserSport",
    "Follow",
    "Match",
    "MatchPlayer",
    "Message",
    "Review",
    "Notification",
    "ContentPage",
    "SupportRequest",
]
