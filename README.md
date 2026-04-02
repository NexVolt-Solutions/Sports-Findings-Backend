# Sports Platform — Backend API

A comprehensive, production-ready FastAPI async backend for discovering, creating, and joining local sports matches.

**Supports:** Football, Basketball, Cricket, Tennis, Volleyball, and Badminton.

---

## Overview

Sports Platform is a community-driven sports matching service that connects players, enables real-time collaboration, and provides comprehensive match discovery. The backend handles:

- **User Management** — Authentication with email verification, Google OAuth, and secure session handling
- **Match Discovery** — Nearby match search with Haversine-based geolocation and multi-filter discovery
- **Real-Time Features** — WebSocket-powered chat and in-app notifications
- **Social System** — Follow players, leave ratings and reviews, send match invitations
- **Admin Dashboard** — Complete administrative panel for user, match, review, and content management
- **Production Ready** — Docker containerization, comprehensive testing, background task handling, rate limiting

---

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | FastAPI 0.115.0 (Python 3.12) |
| Server | Uvicorn (ASGI) + Gunicorn (production) |
| Database | PostgreSQL 15+ with asyncpg driver |
| ORM | SQLAlchemy 2.0 (async) |
| Migrations | Alembic |
| Auth | JWT (python-jose) + bcrypt (passlib) |
| Real-Time | FastAPI WebSockets |
| Rate Limiting | slowapi |
| Geocoding | Google Maps Geocoding API |
| Email | FastAPI-Mail (SMTP) |
| Testing | pytest + pytest-asyncio + httpx |
| Containerization | Docker + docker-compose |

---

## Local Setup (Windows + Python 3.12)

### Prerequisites

- Python 3.12 installed — verify with: `python --version`
- PostgreSQL installed and running
- Git installed

---

### Step 1 — Clone the Repository

```bash
git clone https://github.com/your-org/sports-platform.git
cd sports-platform
```

---

### Step 2 — Create a Virtual Environment

```bash
python -m venv venv
```

Activate it on Windows:

```bash
venv\Scripts\activate
```

You should see `(venv)` at the start of your terminal prompt.

---

### Step 3 — Install Dependencies

```bash
pip install -r requirements.txt
```

---

### Step 4 — Set Up the Database

Open **pgAdmin** or **psql** and create two databases:
- `sports_platform` — development database
- `sports_platform_test` — test database (used by pytest)

```sql
CREATE DATABASE sports_platform;
CREATE DATABASE sports_platform_test;
```

---

### Step 5 — Configure Environment Variables

Copy the example file and fill in your values:

```bash
copy .env.example .env
```

Open `.env` and update the following required fields:

```env
DATABASE_URL=postgresql+asyncpg://postgres:YOUR_PASSWORD@localhost:5432/sports_platform
SECRET_KEY=your_super_secret_key_change_this
```

Generate a secure SECRET_KEY:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

> Optional fields (Google OAuth, Maps, Email, Firebase, Cloudinary)
> can be left blank for Phase 1 development. Features using those
> services will be skipped until configured.

---

### Step 6 — Run Database Migrations

Generate and apply the initial migration:

```bash
alembic revision --autogenerate -m "initial_schema"
alembic upgrade head
```

To check current migration status:

```bash
alembic current
```

To roll back one migration:

```bash
alembic downgrade -1
```

---

### Step 7 — Start the Development Server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API is now running at: **http://localhost:8000**

---

## API Documentation

Once the server is running, visit:

| URL | Description |
|---|---|
| http://localhost:8000/docs | Swagger UI (interactive API explorer) |
| http://localhost:8000/redoc | ReDoc (readable API documentation) |
| http://localhost:8000/openapi.json | OpenAPI schema |
| http://localhost:8000/health | Health check endpoint (load balancer friendly) |

### REST API Endpoints

All REST endpoints are versioned under `/api/v1`:

#### **Authentication** (`/api/v1/auth`)
- `POST /register` — Register with email and password
- `POST /login` — Login (returns access + refresh tokens)
- `POST /google` — Google OAuth authentication
- `POST /refresh` — Refresh access token using refresh token
- `POST /logout` — Logout (invalidate tokens)
- `POST /verify-email` — Verify email with OTP
- `POST /resend-verification-otp` — Resend verification OTP
- `POST /forgot-password` — Request password reset email
- `POST /reset-password` — Reset password with token

#### **Users** (`/api/v1/users`)
- `GET /me` — Get authenticated user's profile
- `PUT /me` — Update profile (bio, location, sports, skill levels)
- `POST /me/avatar` — Upload profile avatar
- `GET /{user_id}` — Get user's public profile
- `GET /{user_id}/stats` — Get user's match statistics
- `GET /{user_id}/reviews` — Get reviews left on a user
- `POST /{user_id}/reviews` — Leave a review and rating
- `POST /{user_id}/follow` — Follow a user
- `DELETE /{user_id}/follow` — Unfollow a user
- `GET /{user_id}/followers` — List user's followers
- `GET /{user_id}/following` — List users being followed

#### **Matches** (`/api/v1/matches`)
- `POST /` — Create a new match (creator auto-joins as host)
- `GET /my` — List matches the current user is participating in
- `GET /nearby` — Discover nearby matches (with filters)
- `GET /` — List all matches with filters (sport, date, status)
- `GET /{match_id}` — Get match details
- `PUT /{match_id}` — Update match details (host only)
- `DELETE /{match_id}` — Delete match (host only)
- `POST /{match_id}/join` — Join an active match
- `DELETE /{match_id}/leave` — Leave a match
- `GET /{match_id}/players` — List match participants
- `DELETE /{match_id}/players/{user_id}` — Remove player (host only)
- `PATCH /{match_id}/status` — Update match status (host only)
- `POST /{match_id}/invite` — Send match invitation to a user
- `GET /{match_id}/messages` — Retrieve match chat history

#### **Notifications** (`/api/v1/notifications`)
- `GET /` — Get user's notifications (paginated)
- `PATCH /{notification_id}/read` — Mark notification as read
- `PATCH /read-all` — Mark all notifications as read

#### **Admin** (`/api/v1/admin`)
- `GET /dashboard` — Dashboard statistics (total users, matches, etc.)
- `GET /users` — List all users (searchable, filterable)
- `POST /users` — Create user manually
- `GET /users/{user_id}` — Get user details (admin view)
- `PATCH /users/{user_id}/block` — Block/unblock user
- `DELETE /users/{user_id}` — Delete user
- `GET /matches` — List all matches
- `GET /matches/{match_id}` — Get match details
- `PUT /matches/{match_id}` — Update match
- `DELETE /matches/{match_id}` — Delete match
- `GET /reviews/users` — List users with reviews
- `GET /reviews/users/{user_id}` — Get user's reviews for moderation
- `DELETE /reviews/{review_id}` — Delete a review
- `GET /content/{section}` — Get CMS content (terms, privacy, etc.)
- `PUT /content/{section}` — Update CMS content
- `GET /support-requests` — List support requests
- `GET /support-requests/{request_id}` — Get support request details
- `PATCH /support-requests/{request_id}/resolve` — Mark resolved
- `DELETE /support-requests/{request_id}` — Delete support request
- `GET /account` — Admin's account details
- `PUT /account` — Update admin profile
- `PATCH /account/password` — Change admin password

### WebSocket Endpoints

WebSocket endpoints enable real-time communication:

#### **Match Chat** (`/ws/matches/{match_id}/chat`)
- Real-time bidirectional chat for match participants
- Automatic message persistence to database
- Connection validation via JWT token

#### **Notifications** (`/ws/notifications`)
- Real-time in-app notifications (NEW_FOLLOWER, MATCH_INVITED, etc.)
- Server-to-client push (async updates)
- Connection validation via JWT token

---

## Running Tests

```bash
pytest
```

Run with verbose output:

```bash
pytest -v
```

Run a specific test file:

```bash
pytest tests/test_auth.py -v
```

---

## Project Structure

```
sports_platform/
│
├── app/
│   ├── main.py                   # FastAPI app initialization, middleware, routers, lifespan
│   ├── config.py                 # Settings from .env (pydantic-settings)
│   ├── database.py               # Async SQLAlchemy engine, session, Base model
│   ├── middleware.py             # Custom middleware (logging, security headers)
│   │
│   ├── models/                   # SQLAlchemy ORM models
│   │   ├── base.py               # Base model with common fields
│   │   ├── enums.py              # All Enum types (Sport, SkillLevel, MatchStatus, etc.)
│   │   ├── user.py               # User, UserSport models
│   │   ├── follow.py             # Follow relationships
│   │   ├── match.py              # Match model with location, datetime
│   │   ├── match_player.py       # MatchPlayer junction table
│   │   ├── message.py            # Chat messages with timestamps
│   │   ├── review.py             # Review and ratings model
│   │   ├── notification.py       # In-app notifications
│   │   ├── content_page.py       # CMS content (terms, privacy, etc.)
│   │   └── support_request.py    # Support tickets
│   │
│   ├── schemas/                  # Pydantic request/response schemas (validation, serialization)
│   │   ├── common.py             # PaginatedResponse, MessageResponse, ErrorResponse
│   │   ├── auth.py               # Register, Login, Token, OAuth schemas
│   │   ├── user.py               # UserResponse, ProfileResponse, StatsResponse
│   │   ├── match.py              # MatchRequest, MatchResponse, MatchPlayerResponse
│   │   ├── review.py             # ReviewRequest, ReviewResponse
│   │   ├── notification.py       # NotificationResponse
│   │   └── message.py            # MessageRequest, MessageResponse
│   │
│   ├── routes/                   # API endpoint definitions (thin layer, business logic in services)
│   │   ├── auth.py               # /api/v1/auth/* endpoints
│   │   ├── users.py              # /api/v1/users/* endpoints
│   │   ├── matches.py            # /api/v1/matches/* endpoints
│   │   ├── notifications.py      # /api/v1/notifications/* + /ws/notifications
│   │   ├── chat.py               # /api/v1/matches/{id}/messages + /ws/matches/{id}/chat
│   │   └── admin.py              # /api/v1/admin/* endpoints (protected by admin role)
│   │
│   ├── services/                 # Business logic layer (all domain rules and operations)
│   │   ├── auth_service.py       # Registration, login, OAuth, password reset, token management
│   │   ├── user_service.py       # Profile CRUD, stats, followers, following
│   │   ├── match_service.py      # Match CRUD, discovery, geolocation, player management
│   │   ├── notification_service.py # Notification creation and queries
│   │   ├── chat_service.py       # Message storage and retrieval
│   │   ├── review_service.py     # Review creation and validation
│   │   └── admin_service.py      # Admin operations on users, matches, reviews, content
│   │
│   ├── dependencies/             # FastAPI Depends() dependency injection
│   │   └── auth.py               # get_current_user, get_current_admin, get_ws_user
│   │
│   ├── websockets/               # WebSocket connection management
│   │   └── connection_manager.py # Broadcast, connection tracking, message queuing
│   │
│   ├── background/               # Background task definitions (async, non-blocking)
│   │   └── tasks.py              # Email tasks (verification, password reset), logging
│   │
│   └── utils/                    # Shared utility functions
│       ├── security.py           # Password hashing, JWT token creation/verification
│       ├── pagination.py         # PaginationParams, paginate() function
│       ├── exceptions.py         # Reusable HTTP exceptions
│       └── geocoding.py          # Google Maps Geocoding API wrapper
│
├── alembic/                      # Database migration system
│   ├── env.py                    # Alembic configuration
│   ├── script.py.mako            # Migration script template
│   └── versions/                 # Generated migration files
│       ├── initial_schema.py
│       ├── add_email_verification_otp.py
│       └── add_admin_content_and_support_requests.py
│
├── tests/                        # Comprehensive async test suite
│   ├── conftest.py               # Pytest fixtures and test database setup
│   ├── test_auth.py              # Authentication endpoint tests
│   ├── test_users.py             # User profile and stats tests
│   ├── test_matches.py           # Match CRUD and join/leave tests
│   ├── test_discovery.py         # Nearby match search and filter tests
│   ├── test_social.py            # Follow system, reviews, ratings tests
│   ├── test_chat.py              # WebSocket chat tests
│   ├── test_admin.py             # Admin dashboard and management tests
│   └── test_hardening.py         # Security, rate limiting, error handling tests
│
├── scripts/                      # Utility scripts
│   └── create_admin.py           # Create admin user from CLI
│
├── postman/                      # Postman API collections for manual testing
│
├── Dockerfile                    # Docker image definition (Python 3.12 + Gunicorn)
├── docker-compose.yml            # Docker Compose for API + PostgreSQL
├── nginx.conf                    # Nginx reverse proxy configuration
├── alembic.ini                   # Alembic configuration file
├── pytest.ini                    # Pytest configuration
├── requirements.txt              # Python dependencies
├── .env.example                  # Environment variable template
├── .gitignore                    # Git ignore rules
└── README.md                     # This file
```

### Key Design Patterns

- **Service Layer Pattern** — All business logic isolated in `services/`, routes are thin controllers
- **Dependency Injection** — FastAPI `Depends()` for authentication, database, pagination
- **Async Throughout** — Pure async/await, asyncpg driver, asyncio-compatible tests
- **Pydantic Validation** — Request/response validation with clear error messages
- **Middleware Stack** — CORS, security headers, request logging, rate limiting
- **Background Tasks** — Non-blocking operations (email, notifications)
- **WebSocket Connection Manager** — Safe, efficient broadcast to multiple clients

---

## Development Workflow & Implementation Status

The project follows a phased development approach:

### Phase 1 — Foundation ✅ Complete
- [x] Project skeleton and folder structure
- [x] Database models (all core tables: users, matches, reviews, notifications, messages)
- [x] Pydantic schemas for all endpoints
- [x] Authentication dependencies and JWT flow
- [x] WebSocket connection manager
- [x] Route definitions with proper request/response models
- [x] Service layer with business logic
- [x] User registration with email verification (OTP-based)
- [x] Login with email/password and JWT tokens
- [x] Password reset flow with email tokens
- [x] Google OAuth authentication integration
- [x] Token refresh mechanism
- [x] Alembic database migrations setup
- [x] Comprehensive test fixtures and async testing infrastructure

### Phase 2 — Core Match Features ✅ Complete
- [x] Create match (auto-join creator as host)
- [x] Update match details and location
- [x] Delete match (host only)
- [x] Join active match
- [x] Leave match
- [x] View match participants
- [x] Remove player from match (host only)
- [x] Match status transitions (ACTIVE, ONGOING, COMPLETED, CANCELLED)
- [x] My Matches list (paginated, user's participations)
- [x] Match invitation system with notifications

### Phase 3 — Discovery & Maps ✅ Complete
- [x] Nearby match search (Haversine distance formula)
- [x] Multi-filter discovery (sport, distance, skill level, date range)
- [x] Google Maps Geocoding for address to coordinates
- [x] Sort by distance, date, availability
- [x] Pagination support for all list endpoints

### Phase 4 — Real-Time Features ✅ Complete
- [x] WebSocket chat for match discussions
- [x] Message persistence (stored in database)
- [x] Real-time notifications via WebSocket
- [x] Notification types: NEW_FOLLOWER, MATCH_INVITED, MATCH_STARTED, PLAYER_JOINED
- [x] Mark notifications as read (individual and bulk)
- [x] Push notification infrastructure (Firebase stub)

### Phase 5 — Social Features ✅ Complete
- [x] Follow / Unfollow system
- [x] NEW_FOLLOWER notification
- [x] Player reviews and ratings (1-5 stars)
- [x] Post-match reviews (validated against match participation)
- [x] Average rating calculation and updates
- [x] Reviews can be viewed on user profiles
- [x] Admin review moderation and deletion

### Phase 6 — Admin Panel ✅ Complete
- [x] Admin dashboard with key statistics
- [x] User management (list, search, filter, view details)
- [x] User blocking/unblocking
- [x] User deletion with cascade cleanup
- [x] Manual user creation
- [x] Match management (list, view, edit, delete)
- [x] Review moderation (list, view, delete)
- [x] CMS content management (terms, privacy policy, about, FAQ)
- [x] Support request tracking and resolution
- [x] Admin account management (profile, password change)

### Phase 7 — Production Features (In Progress)
- [x] Rate limiting (slowapi middleware)
- [x] Security headers (CORS, CSP, X-Frame-Options, etc.)
- [x] Docker containerization (Dockerfile + docker-compose)
- [x] Request logging and monitoring
- [x] Comprehensive error handling with custom exceptions
- [ ] Image upload to Cloudinary (avatar, match photos)
- [ ] Push notifications (FCM for Android, APNs for iOS)
- [ ] Cache layer (Redis for frequently accessed data)
- [ ] Background task queue (Celery for async jobs with retry)

---

## Admin Account Creation

Run this from the project root to create an admin account:

```bash
python scripts/create_admin.py
```

Or with arguments:

```bash
python scripts/create_admin.py --email admin@example.com --name "Admin User"
```

---

## Common Commands

```bash
# Start dev server with auto-reload
uvicorn app.main:app --reload

# Generate a new migration after model changes
alembic revision --autogenerate -m "describe_your_change"

# Apply all pending migrations
alembic upgrade head

# Roll back last migration
alembic downgrade -1

# Run all tests
pytest

# Run tests with coverage
pytest --cov=app tests/

# Run tests for a specific module
pytest tests/test_auth.py -v

# Run tests matching a pattern
pytest tests/ -k "test_login" -v
```

---

## Docker & Deployment

### Running with Docker Compose

The easiest way to run the application locally with all dependencies:

```bash
# Build and start the API + PostgreSQL containers
docker-compose up -d

# View logs
docker-compose logs -f api

# Stop services
docker-compose down

# Stop and remove volumes (WARNING: deletes database)
docker-compose down -v
```

The API will be available at `http://localhost:8000`.

**Note:** Ensure `.env.production` is configured with the correct `DB_PASSWORD` before running docker-compose.

### Building Docker Image

To manually build the Docker image:

```bash
# Build
docker build -t sports-platform:latest .

# Run with environment variables
docker run -d \
  -p 8000:8000 \
  -e DATABASE_URL="postgresql+asyncpg://postgres:password@db:5432/sports_platform" \
  -e SECRET_KEY="your-secret-key" \
  sports-platform:latest
```

### Production Deployment

#### Environment Setup

1. Create `.env.production` with production values:

```env
DEBUG=False
ENVIRONMENT=production
APP_BASE_URL=https://api.sportsplatform.com
DATABASE_URL=postgresql+asyncpg://user:password@db-host:5432/sports_platform
SECRET_KEY=<strong-secret-key>
GOOGLE_MAPS_API_KEY=<key>
MAIL_USERNAME=<email>
MAIL_PASSWORD=<password>
```

2. Generate a strong SECRET_KEY:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

#### Application Server

The Dockerfile uses **Gunicorn** with **Uvicorn workers** for production:

```dockerfile
CMD ["gunicorn", "app.main:app", \
     "--workers", "4", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000"]
```

Adjust `--workers` based on CPU cores: typically `(2 × CPU_count) + 1`.

#### Reverse Proxy (Nginx)

Use `nginx.conf` to proxy requests to Gunicorn:

```bash
upstream api {
    server localhost:8000;
}

server {
    listen 80;
    server_name api.sportsplatform.com;

    location / {
        proxy_pass http://api;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # WebSocket support
    location /ws {
        proxy_pass http://api;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

#### Database Migrations in Production

Before deploying new code, run migrations on the production database:

```bash
# Inside container
alembic upgrade head

# Or from host (if database is accessible)
DATABASE_URL="<prod-url>" alembic upgrade head
```

#### Health Checks

The application exposes a health check endpoint for load balancers:

```bash
GET /health

Response:
{
  "status": "healthy",
  "app": "Sports Platform",
  "version": "1.0.0",
  "environment": "production"
}
```

Configure load balancers to periodically check this endpoint.

#### Monitoring & Logging

- **Request Logs:** All HTTP requests are logged with method, path, duration, status
- **Error Logs:** Unhandled exceptions are logged with full tracebacks
- **Debug Logs:** Enabled via `DEBUG=True` environment variable

Configure log aggregation (ELK, Datadog, CloudWatch) to ship logs to your monitoring system.

---

## Environment Variables Reference

### Required Variables

| Variable | Description | Example |
|---|---|---|
| `DATABASE_URL` | PostgreSQL async connection string | `postgresql+asyncpg://postgres:password@localhost:5432/sports_platform` |
| `SECRET_KEY` | JWT signing secret — keep private and secure | Generated via `openssl rand -hex 32` |

### Optional Variables (Feature Flags)

| Variable | Description | Default |
|---|---|---|
| `DEBUG` | Enable debug mode and verbose logging | `False` |
| `ENVIRONMENT` | Deployment environment | `development` |
| `APP_BASE_URL` | Application base URL for links | `http://localhost:8000` |
| `ALGORITHM` | JWT signing algorithm | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access token TTL | `15` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Refresh token TTL | `30` |

### Google OAuth

| Variable | Description |
|---|---|
| `GOOGLE_CLIENT_ID` | Google OAuth client ID (Phase 1) |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret (Phase 1) |

### Google Maps

| Variable | Description |
|---|---|
| `GOOGLE_MAPS_API_KEY` | Google Maps Geocoding API key (Phase 3) |

### Email (SMTP)

| Variable | Description | Default |
|---|---|---|
| `MAIL_USERNAME` | SMTP email address | Empty (disabled) |
| `MAIL_PASSWORD` | SMTP email password | Empty (disabled) |
| `MAIL_FROM` | Email sender address | Empty (uses MAIL_USERNAME) |
| `MAIL_SERVER` | SMTP server | `smtp.gmail.com` |
| `MAIL_PORT` | SMTP port | `587` |
| `MAIL_STARTTLS` | Enable STARTTLS | `True` |
| `MAIL_SSL_TLS` | Enable SSL/TLS | `False` |

### Firebase (Push Notifications)

| Variable | Description |
|---|---|
| `FIREBASE_CREDENTIALS_PATH` | Path to Firebase credentials JSON file (Phase 4) |

### Cloudinary (File Storage)

| Variable | Description |
|---|---|
| `CLOUDINARY_CLOUD_NAME` | Cloudinary cloud name (Phase 1) |
| `CLOUDINARY_API_KEY` | Cloudinary API key (Phase 1) |
| `CLOUDINARY_API_SECRET` | Cloudinary API secret (Phase 1) |

### Rate Limiting

| Variable | Description | Default |
|---|---|---|
| `RATE_LIMIT_AUTH` | Auth endpoints rate limit | `5/minute` |
| `RATE_LIMIT_GENERAL` | General endpoints rate limit | `60/minute` |

### Pagination

| Variable | Description | Default |
|---|---|---|
| `DEFAULT_PAGE_SIZE` | Default page size for paginated responses | `20` |
| `MAX_PAGE_SIZE` | Maximum allowed page size | `100` |

**Note:** Features requiring unconfigured services (Google OAuth, Maps, Email, Firebase, Cloudinary) will gracefully degrade or show placeholder responses. Start with `DATABASE_URL` and `SECRET_KEY` only for basic development.

---

## Testing

### Test Structure

The test suite includes 9 comprehensive test modules covering all features:

| Module | Coverage |
|---|---|
| `test_auth.py` | Registration, login, Google OAuth, password reset, email verification |
| `test_users.py` | Profile CRUD, user stats, reviews, followers/following |
| `test_matches.py` | Match CRUD, join/leave, player management, status transitions |
| `test_discovery.py` | Nearby match search, filters, geolocation, pagination |
| `test_social.py` | Follow/unfollow, reviews and ratings, match invitations |
| `test_chat.py` | WebSocket chat, message persistence, real-time delivery |
| `test_admin.py` | Dashboard, user/match/review management, content moderation |
| `test_hardening.py` | Security, rate limiting, error handling, edge cases |
| `conftest.py` | Shared fixtures, database setup, async test utilities |

### Running Tests

```bash
# Run all tests
pytest

# Run with verbose output and print statements
pytest -v -s

# Run specific test file
pytest tests/test_auth.py -v

# Run tests matching a pattern
pytest -k "login" -v

# Run with coverage report
pytest --cov=app --cov-report=html tests/

# Run in parallel (faster)
pip install pytest-xdist
pytest -n auto
```

### Test Database

Tests use a dedicated test database (`sports_platform_test`). The test session:
1. **Setup:** Drops all tables and recreates them clean
2. **Tests:** Run against fresh database
3. **Teardown:** Drops all tables

After testing, restore the development database:

```bash
alembic upgrade head
```

### Test Fixtures

Common fixtures available in `conftest.py`:

```python
@pytest.fixture
async def client() -> AsyncClient:
    """FastAPI test client with test database"""

@pytest.fixture
async def test_user(db: AsyncSession) -> User:
    """Sample user for testing"""

@pytest.fixture
async def test_match(test_user: User, db: AsyncSession) -> Match:
    """Sample match for testing"""

@pytest.fixture
async def auth_token(test_user: User) -> str:
    """JWT token for authenticated requests"""
```

---

## Quick-Start Checklist

### First Time Setup (5 minutes)

- [ ] Clone repository: `git clone <repo>`
- [ ] Create virtual environment: `python -m venv venv && source venv/Scripts/activate`
- [ ] Install dependencies: `pip install -r requirements.txt`
- [ ] Create PostgreSQL databases:
  ```sql
  CREATE DATABASE sports_platform;
  CREATE DATABASE sports_platform_test;
  ```
- [ ] Copy `.env.example` to `.env` and update `DATABASE_URL` and `SECRET_KEY`
- [ ] Run migrations: `alembic upgrade head`
- [ ] Start server: `uvicorn app.main:app --reload`
- [ ] Visit `http://localhost:8000/docs` to test API

### Create Admin Account (1 minute)

```bash
python scripts/create_admin.py --email admin@example.com --name "Admin User"
```

### Run Tests (2 minutes)

```bash
pytest -v
```

### Try the API (3 minutes)

1. **Register user:**
   ```bash
   curl -X POST http://localhost:8000/api/v1/auth/register \
     -H "Content-Type: application/json" \
     -d '{"email":"user@example.com","password":"securepass123"}'
   ```

2. **Login:**
   ```bash
   curl -X POST http://localhost:8000/api/v1/auth/login \
     -H "Content-Type: application/json" \
     -d '{"email":"user@example.com","password":"securepass123"}'
   ```

3. **Get profile:**
   ```bash
   curl -X GET http://localhost:8000/api/v1/users/me \
     -H "Authorization: Bearer <your_access_token>"
   ```

4. **Explore with Swagger:** Open `http://localhost:8000/docs` and try endpoints interactively

---

## Architecture Decisions

### Why Async/Await?
- Non-blocking I/O for database, HTTP, and WebSocket operations
- Better resource utilization with high concurrency
- Native WebSocket support via Starlette

### Why Service Layer?
- Separation of concerns (routes are thin, services contain logic)
- Easy to test business logic in isolation
- Reusable business logic across multiple endpoints

### Why WebSockets?
- Real-time chat without polling
- Low-latency notifications
- Persistent connection reduces overhead for multiple messages

### Why Alembic?
- Database-agnostic migration framework
- Version control for schema changes
- Automatic migration generation from models

### Rate Limiting
- Protection against abuse and DoS
- Configurable per endpoint
- Graceful 429 responses with Retry-After header

---

## Troubleshooting

### Database Connection Error
```
Error: could not translate host name "localhost" to address
```
**Solution:** Ensure PostgreSQL is running and `DATABASE_URL` is correct

### "Another operation is in progress" (asyncpg)
```
asyncpg.exceptions._DriverError: another operation is in progress
```
**Solution:** Tests use `NullPool` to prevent connection sharing. Check if you're reusing connections across async contexts.

### WebSocket Connection Refused
```
WebSocket error: connection refused at ws://localhost:8000/ws/...
```
**Solution:** Ensure server is running and JWT token is valid. WebSocket connections require authentication.

### Alembic Migration Conflicts
```
FAILED target database is not up to date
```
**Solution:** Run `alembic upgrade head` to apply all pending migrations before running tests.

### Port Already in Use
```
Address already in use (:8000)
```
**Solution:** Change port with `--port 8001` or kill the process: `lsof -i :8000 | grep LISTEN | awk '{print $2}' | xargs kill -9`

---

## Contributing

### Code Style
- Follow PEP 8
- Use type hints on all functions
- Keep functions focused (single responsibility)
- Add docstrings to public APIs

### Commit Convention
```
type(scope): description

Longer explanation if needed.

Fixes #123
```

Types: `feat`, `fix`, `docs`, `test`, `refactor`, `style`, `chore`

### Before Submitting PR
- [ ] Tests pass: `pytest -v`
- [ ] Code formatted: `black .` (if configured)
- [ ] No linting errors: `flake8 app/ tests/` (if configured)
- [ ] Database migrations work: `alembic upgrade head && alembic downgrade -1 && alembic upgrade head`

---

## Support

For issues, questions, or suggestions:
- Open an issue on GitHub
- Contact the development team
- Check the [Documentation](#api-documentation)


