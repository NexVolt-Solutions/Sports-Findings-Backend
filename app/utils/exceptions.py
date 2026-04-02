from fastapi import HTTPException, status


# ─── 400 Bad Request ──────────────────────────────────────────────────────────
def bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


# ─── 401 Unauthorized ─────────────────────────────────────────────────────────
def unauthorized(detail: str = "Authentication required") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


# ─── 403 Forbidden ────────────────────────────────────────────────────────────
def forbidden(detail: str = "You do not have permission to perform this action") -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


# ─── 404 Not Found ────────────────────────────────────────────────────────────
def not_found(resource: str = "Resource") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"{resource} not found",
    )


# ─── 409 Conflict ─────────────────────────────────────────────────────────────
def conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


# ─── 422 Unprocessable ────────────────────────────────────────────────────────
def unprocessable(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=detail,
    )


# ─── 429 Too Many Requests ────────────────────────────────────────────────────
def rate_limited(detail: str = "Too many requests. Please try again later.") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=detail,
    )


# ─── 502 Bad Gateway ──────────────────────────────────────────────────────────
def external_service_error(service: str = "External service") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"{service} is currently unavailable. Please try again.",
    )


# ─── Common Domain Exceptions ─────────────────────────────────────────────────
class UserNotFound(HTTPException):
    def __init__(self):
        super().__init__(status_code=404, detail="User not found")


class MatchNotFound(HTTPException):
    def __init__(self):
        super().__init__(status_code=404, detail="Match not found")


class MatchFull(HTTPException):
    def __init__(self):
        super().__init__(status_code=409, detail="This match is already full")


class MatchNotOpen(HTTPException):
    def __init__(self):
        super().__init__(status_code=409, detail="This match is no longer open for joining")


class AlreadyJoined(HTTPException):
    def __init__(self):
        super().__init__(status_code=409, detail="You have already joined this match")


class NotMatchHost(HTTPException):
    def __init__(self):
        super().__init__(status_code=403, detail="Only the match host can perform this action")


class EmailAlreadyRegistered(HTTPException):
    def __init__(self):
        super().__init__(status_code=409, detail="An account with this email already exists")


class InvalidCredentials(HTTPException):
    def __init__(self):
        super().__init__(status_code=401, detail="Invalid email or password")


class AccountNotVerified(HTTPException):
    def __init__(self):
        super().__init__(status_code=403, detail="Please verify your email address before logging in")


class AccountBlocked(HTTPException):
    def __init__(self):
        super().__init__(status_code=403, detail="Your account has been blocked. Contact support.")
