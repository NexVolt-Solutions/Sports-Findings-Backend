# Sports Platform API

## Project Overview

Sports Platform is a backend API for a mobile/web app that connects players, hosts and matches. It provides user accounts, match discovery and management, reviews, support requests, and admin tools for managing site content such as Terms of Service, Privacy Policy, and Help & Support pages.

This repository contains the FastAPI-based server, database migrations (Alembic), and Docker files for local development and production deployment.

## Key Features

- User registration, authentication, and profile management
- Match creation, discovery, joining, and moderation
- Review system for participants
- Support request handling
- Admin dashboard: user, match, review moderation, support requests
- Admin-managed content pages: Terms of Service, Privacy Policy, Help & Support

## Technology Stack

- Python 3.10+
- FastAPI
- SQLAlchemy (async) + Alembic
- PostgreSQL (recommended)
- Docker & docker-compose

## Getting Started — Local Development

Prerequisites
- Python 3.10+
- pip
- Docker (optional, recommended for DB)

Clone the repo

  git clone <repo-url>
  cd sports_platform

Create a virtual environment

  python -m venv .venv
  .\.venv\Scripts\activate

Install dependencies

  pip install -r requirements.txt

Create environment variables

Copy `.env.example` (if provided) or create `.env` with the variables listed below.

Common environment variables

- DATABASE_URL — SQLAlchemy database URL (e.g. postgresql+asyncpg://user:pass@localhost:5432/dbname)
- SECRET_KEY — application secret for tokens and security
- API_V1_STR — API prefix (default: /api/v1)
- SMTP_* — mail settings if email features are used

Note: This project expects an async PostgreSQL driver (asyncpg) when using PostgreSQL.

Run database migrations

  alembic upgrade head

Start the app

  uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

Or using Docker Compose (recommended for local dev)

  docker-compose up --build

Run tests

  pytest

## API Overview

Base URL: /api/v1 (check `API_V1_STR` in configuration)

Authentication
- Uses JWT bearer tokens. Obtain token via the auth endpoints (see project-specific auth routes).

Admin endpoints (examples)
- GET /admin/content/terms-of-service — Fetch Terms of Service content
- PUT /admin/content/terms-of-service — Update Terms of Service (admin only)
- GET /admin/content/privacy-policy — Fetch Privacy Policy content
- PUT /admin/content/privacy-policy — Update Privacy Policy (admin only)
- GET /admin/content/help-support — Fetch Help & Support content
- PUT /admin/content/help-support — Update Help & Support (admin only)

Other notable admin endpoints
- GET /admin/dashboard — Dashboard metrics
- GET /admin/users — List users (supports filters)
- POST /admin/users — Create user (admin)
- PUT /admin/matches/{match_id} — Edit match
- GET /admin/support-requests — List support requests

API responses follow pydantic schemas defined in `app/schemas`.

For full API contract, consult the route definitions in `app/routes` and the pydantic models in `app/schemas`.

## Environment & Configuration

- Configuration is read from environment variables and settings modules in `app`.
- Keep sensitive keys out of source control. Use a secrets manager for production.

## Database Migrations

- Migrations are managed with Alembic. The migration scripts are in the `alembic/versions` directory.
- To create a new migration after model changes:

  alembic revision --autogenerate -m "describe change"
  alembic upgrade head

## Deployment

Production deployment options

- Docker: build image using the provided `Dockerfile` and deploy to your container platform.
- Docker Compose (production): `docker-compose.prod.yml` provides a sample stack.
- ECS / Kubernetes: use the included task definition or create manifests adapted to your environment.

Typical production steps
- Build and push Docker image
- Provision managed PostgreSQL instance
- Set production environment variables and secrets
- Run Alembic migrations against the production database
- Start service behind a reverse proxy (Nginx, ALB, etc.) and use HTTPS

## Developer Notes

- Code layout: routes in `app/routes`, services in `app/services`, models in `app/models`, and pydantic schemas in `app/schemas`.
- Tests live in `tests/` and use pytest and an async test client.
- Follow existing code patterns for DI (FastAPI Depends) and async DB sessions.

Adding Admin Content Pages
- Content pages are stored in `content_pages` (model `ContentPage`) and are keyed by `section`. Valid sections include:
  - `terms-of-service`
  - `privacy-policy`
  - `help-support`

- Frontend manages the content; backend provides GET/PUT endpoints for retrieving and saving content. When updating, ensure the admin user has the appropriate privileges.

## Contributing

- Fork the repository and create a feature branch.
- Ensure tests pass locally before opening a PR.
- Provide clear commit messages and include `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>` in automated commits (if present).

## Troubleshooting & Tips

- If migrations fail, check that `DATABASE_URL` is correct and reachable.
- Run the test suite after environment changes: `pytest -q`.
- Use logging configuration to increase verbosity when debugging server behavior.

## License & Acknowledgements

Add the appropriate license and acknowledgements for third-party libraries and contributors.


---

If anything specific should be added (detailed API examples, Postman collection usage, or CI/CD instructions), indicate what to include and a short example will be added to this README.

Badges

[![Build Status](https://img.shields.io/badge/build-passing-brightgreen)](https://example.com) [![Coverage](https://img.shields.io/badge/coverage-unknown-blue)](https://example.com) [![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Example cURL requests

Fetch Terms of Service

curl -H "Authorization: Bearer <ADMIN_TOKEN>" "{{API_BASE}}/admin/content/terms-of-service"

Update Privacy Policy

curl -X PUT -H "Authorization: Bearer <ADMIN_TOKEN>" -H "Content-Type: application/json" -d '{"title":"Privacy Policy","content":"New content"}' "{{API_BASE}}/admin/content/privacy-policy"

Update Help & Support

curl -X PUT -H "Authorization: Bearer <ADMIN_TOKEN>" -H "Content-Type: application/json" -d '{"title":"Help & Support","content":"Help content"}' "{{API_BASE}}/admin/content/help-support"

Notes

- Replace {{API_BASE}} with your base API URL (e.g., https://api.example.com/api/v1)
- Use an admin JWT token; /admin endpoints require admin privileges.

---
