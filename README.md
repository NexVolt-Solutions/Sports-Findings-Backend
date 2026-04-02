# Sports Platform — Backend API

FastAPI async backend for the Sports Platform.
Supports Football, Basketball, Cricket, Tennis, Volleyball, and Badminton.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | FastAPI (Python 3.12) |
| Server | Uvicorn (ASGI) |
| Database | PostgreSQL 15+ |
| ORM | SQLAlchemy 2.x (async) |
| DB Driver | asyncpg |
| Migrations | Alembic |
| Auth | JWT (python-jose) + bcrypt (passlib) |
| Real-Time | FastAPI WebSockets |
| Rate Limiting | slowapi |
| Maps | Google Maps Geocoding API |
| Testing | pytest + pytest-asyncio + httpx |

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
| http://localhost:8000/docs | Swagger UI (interactive) |
| http://localhost:8000/redoc | ReDoc (readable) |
| http://localhost:8000/health | Health check endpoint |

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
│   ├── main.py               # FastAPI app, middleware, routers
│   ├── config.py             # Settings from .env (pydantic-settings)
│   ├── database.py           # Async engine, session, Base
│   │
│   ├── models/               # SQLAlchemy ORM models
│   │   ├── enums.py          # All Enum types
│   │   ├── user.py           # User, UserSport
│   │   ├── follow.py         # Follow
│   │   ├── match.py          # Match
│   │   ├── match_player.py   # MatchPlayer (junction)
│   │   ├── message.py        # Message (chat)
│   │   ├── review.py         # Review
│   │   └── notification.py   # Notification
│   │
│   ├── schemas/              # Pydantic request/response schemas
│   │   ├── common.py         # PaginatedResponse, MessageResponse
│   │   ├── auth.py           # Register, Login, Token schemas
│   │   ├── user.py           # User profile schemas
│   │   ├── match.py          # Match schemas
│   │   ├── review.py         # Review schemas
│   │   ├── notification.py   # Notification schema
│   │   └── message.py        # Chat message schemas
│   │
│   ├── routes/               # API route definitions (thin layer)
│   │   ├── auth.py           # /auth/*
│   │   ├── users.py          # /users/*
│   │   ├── matches.py        # /matches/*
│   │   ├── notifications.py  # /notifications/*
│   │   ├── chat.py           # /ws/matches/{id}/chat
│   │   └── admin.py          # /admin/*
│   │
│   ├── services/             # Business logic (all domain rules live here)
│   │   ├── auth_service.py
│   │   ├── user_service.py
│   │   └── match_service.py
│   │
│   ├── dependencies/         # FastAPI Depends() functions
│   │   └── auth.py           # get_current_user, get_current_admin, get_ws_user
│   │
│   ├── websockets/           # WebSocket connection management
│   │   └── connection_manager.py
│   │
│   ├── background/           # Background task definitions
│   │   └── tasks.py
│   │
│   └── utils/                # Shared utilities
│       ├── security.py       # Password hashing, JWT tokens
│       ├── pagination.py     # PaginationParams, paginate(), PaginatedResponse
│       ├── exceptions.py     # Reusable HTTP exceptions
│       └── geocoding.py      # Google Maps geocoding wrapper
│
├── alembic/                  # Database migrations
│   ├── env.py
│   ├── script.py.mako
│   └── versions/             # Generated migration files
│
├── tests/                    # Async test suite
│   └── conftest.py           # Shared fixtures
│
├── alembic.ini               # Alembic configuration
├── pytest.ini                # Pytest configuration
├── requirements.txt          # Python dependencies
├── .env.example              # Environment variable template
├── .gitignore
└── README.md
```

---

## Development Workflow

### Phase 1 — Foundation ✅ Complete
- [x] Project skeleton and folder structure
- [x] Database models (all tables)
- [x] Pydantic schemas
- [x] Auth dependencies
- [x] WebSocket connection manager
- [x] Route stubs with TODO markers
- [x] Service stubs with step-by-step implementation notes
- [x] Auth service implementation (register, login, Google OAuth)
- [x] User service implementation (profile CRUD)
- [x] Alembic initial migration

### Phase 2 — Core Match Features ✅ Complete
- [x] Match CRUD (create, update, delete)
- [x] Join / leave / remove player
- [x] Host controls (Start Game, status transitions)
- [x] My Matches list

### Phase 3 — Discovery & Maps ✅ Complete
- [x] Nearby match search with Haversine formula
- [x] Discovery filters (sport, distance, skill, date)
- [x] Google Maps geocoding for match addresses

### Phase 4 — Real-Time
- [x] WebSocket chat with message persistence
- [x] In-app notifications via WebSocket
- [x] Push notifications (FCM + APNs stub — Phase 4)

### Phase 5 — Social
- [x] Follow / unfollow system + NEW_FOLLOWER notification
- [x] Player ratings and reviews (post-match, validated, avg recomputed)
- [x] Match invitations (MATCH_INVITED notification)

### Phase 6 — Admin Panel ✅ Complete
- [x] Admin dashboard API (stats, user mgmt, match mgmt)
- [x] User management (list, search, filter, block/unblock, delete)
- [x] Match management (list, filter, delete any match)

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
```

---

## Environment Variables Reference

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL async connection string |
| `SECRET_KEY` | Yes | JWT signing secret — keep private |
| `ALGORITHM` | No | JWT algorithm (default: HS256) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | Access token TTL (default: 15) |
| `REFRESH_TOKEN_EXPIRE_DAYS` | No | Refresh token TTL (default: 30) |
| `GOOGLE_CLIENT_ID` | Phase 1 | Google OAuth client ID |
| `GOOGLE_MAPS_API_KEY` | Phase 3 | Google Maps Geocoding API key |
| `MAIL_USERNAME` | Phase 1 | SMTP email address |
| `MAIL_PASSWORD` | Phase 1 | SMTP email password |
| `CLOUDINARY_CLOUD_NAME` | Phase 1 | Cloudinary cloud name |
| `FIREBASE_CREDENTIALS_PATH` | Phase 4 | Path to Firebase credentials JSON |
