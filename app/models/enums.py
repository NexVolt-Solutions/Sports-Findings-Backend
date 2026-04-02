import enum


class SportType(str, enum.Enum):
    FOOTBALL = "Football"
    BASKETBALL = "Basketball"
    CRICKET = "Cricket"
    TENNIS = "Tennis"
    VOLLEYBALL = "Volleyball"
    BADMINTON = "Badminton"


class SkillLevel(str, enum.Enum):
    BEGINNER = "Beginner"
    INTERMEDIATE = "Intermediate"
    ADVANCED = "Advanced"


class MatchStatus(str, enum.Enum):
    OPEN = "Open"
    FULL = "Full"
    ONGOING = "Ongoing"
    COMPLETED = "Completed"
    CANCELLED = "Cancelled"


class UserStatus(str, enum.Enum):
    PENDING_VERIFICATION = "Pending_Verification"
    ACTIVE = "Active"
    BLOCKED = "Blocked"


class MatchPlayerRole(str, enum.Enum):
    HOST = "Host"
    PLAYER = "Player"


class MatchPlayerStatus(str, enum.Enum):
    ACTIVE = "Active"
    LEFT = "Left"
    REMOVED = "Removed"


class NotificationType(str, enum.Enum):
    MATCH_JOINED = "match_joined"
    MATCH_INVITED = "match_invited"
    MATCH_STATUS_CHANGED = "match_status_changed"
    NEW_FOLLOWER = "new_follower"
    NEW_REVIEW = "new_review"
    MATCH_STARTED = "match_started"
    PLAYER_REMOVED = "player_removed"


class SupportRequestStatus(str, enum.Enum):
    OPEN = "Open"
    RESOLVED = "Resolved"
