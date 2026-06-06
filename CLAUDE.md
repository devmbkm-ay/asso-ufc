# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**Assos-UFC** — REST API for managing a martial arts association. FastAPI + PostgreSQL backend, deployed on Hetzner via Coolify. Frontend lives in a sibling repo (`assos-ufc-frontend`).

- Production API: `https://api.assos.ricardomboukou.online`
- Frontend (Vercel): `https://asso-ufc-frontend.vercel.app`

## Commands

### Local development

```bash
# Start everything (DB + API) with hot-reload
docker compose up

# API only (requires a running PostgreSQL)
DATABASE_URL=postgresql://user:pass@localhost/asso_db uvicorn app.main:app --reload

# Run smoke tests (no DB required)
pytest tests/

# Run a single test
pytest tests/test_smoke.py::test_health
```

### Database / Migrations

```bash
# Apply all pending migrations
alembic upgrade head

# Check current migration state
alembic current

# Create a new migration after editing models.py
alembic revision --autogenerate -m "description"

# Rollback one step
alembic downgrade -1
```

`DATABASE_URL` env var takes priority over `alembic.ini`. Migrations run automatically at container startup via `entrypoint.sh`.

## Architecture

### Entry point

`app/main.py` — creates the FastAPI app, adds CORSMiddleware, starts the APScheduler via the lifespan context manager, and registers the global 500 handler (which manually injects CORS headers because unhandled exceptions bypass CORSMiddleware).

### Request lifecycle

```
Request → CORSMiddleware → ExceptionMiddleware → APIRouter (/api/v1)
                                                  ├── /auth
                                                  ├── /members
                                                  ├── /cotisation-plans + /payments
                                                  ├── /events
                                                  └── /notifications
```

All routes live under `app/api/v1/routes/`. The router aggregator is `app/api/v1/__init__.py`.

### Authentication & RBAC

`app/core/deps.py` is central to every protected route:
- `CurrentMember` — type alias that injects the authenticated `Member` ORM object (decodes JWT, queries DB, blocks suspended accounts)
- `RequireAdmin` / `RequireTreasurer` / `RequireSecretary` — `Depends(...)` values added as default parameters (`_=RequireAdmin`) to enforce role checks before the route body runs

JWT is stateless: roles are embedded in the access token at login time. `bcrypt` is used directly (not via passlib) to avoid a passlib/bcrypt>=4.0 compatibility bug.

### ORM ↔ Pydantic conversion

**Known pitfall**: `Member.roles` is a SQLAlchemy relationship (`list[MemberRole]`) that collides with `MemberRead.roles: list[str]`. Never pass a `Member` ORM object directly to `MemberRead.model_validate()`. Use the `_member_to_read(member, roles)` helper defined in both `auth.py` and `members.py`, which reads only column attributes via `sa_inspect(member.__class__).mapper.column_attrs` before validating.

### Data model key points

- All PKs are UUIDs.
- `Member.password_hash` stores the bcrypt hash. The field exists in both the SQLAlchemy model (`models.py`) and was added via migration `0003`.
- `Payment` has a `UniqueConstraint` on `(member_id, plan_id, period_month, period_year)` — one payment per member per period.
- `AuditLog` is append-only. Every write to `members` records a `{"before": {}, "after": {}}` diff.

### Background scheduler

`app/core/tasks.py` runs an APScheduler cron job (`send_overdue_reminders`) on `REMINDER_DAY`/`REMINDER_HOUR` (UTC). It opens its own DB session independently from the request lifecycle.

### Deployment

Coolify auto-deploys on push to `main`. The Docker build is multi-stage (deps → final). `entrypoint.sh` waits for PostgreSQL, runs `alembic upgrade head`, then starts uvicorn. Environment variables are set in Coolify (not in `.env` on the server).

Key env vars: `DATABASE_URL`, `SECRET_KEY`, `ALLOWED_ORIGINS` (JSON array), `BREVO_API_KEY`, `REMINDER_DAY`, `REMINDER_HOUR`.
