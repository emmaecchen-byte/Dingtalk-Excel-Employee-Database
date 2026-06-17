# DingTalk Attendance Management System v1.0

Demo web application for HR attendance management with DingTalk integration (planned).

## Quick Start

### Backend (FastAPI)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

API docs: http://127.0.0.1:8000/docs

### Frontend (React)

```bash
cd frontend
npm install
npm run dev
```

Open: http://localhost:5173

## v1.0 Features

- HR dashboard with monthly attendance overview
- Demo employee data (May 2026)
- Sync button (demo mode, no DingTalk credentials required)
- Excel download (four-sheet workbook: 签字, 情况说明, 月度汇总, 加班结算加班工资)
- REST API matching spec endpoints (partial)

## Demo Mode

Set `DEMO_MODE=true` in `backend/.env`. DingTalk OAuth and webhooks are not configured in v1.

## PostgreSQL Setup

### 1. Start PostgreSQL

```bash
docker compose up -d postgres
```

### 2. Configure environment

```bash
cd backend
cp .env.example .env
```

Set `DATABASE_URL` in `.env`:

```
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/dingtalk_attendance
```

### 3. Run migrations

```bash
source .venv/bin/activate
pip install -r requirements.txt
python scripts/run_migrations.py up
```

Rollback:

```bash
python scripts/run_migrations.py down
```

### 4. Start backend

```bash
.venv/bin/uvicorn app.main:app --reload --port 8000
```

## Database Schema

Migration files live in `backend/migrations/`:

- `001_initial_schema.up.sql` — creates all 8 tables
- `001_initial_schema.down.sql` — drops all tables

SQLAlchemy models: `backend/app/models.py`

CRUD layer: `backend/app/crud/` (generic base + entity-specific queries)

Connection pooling is enabled automatically when `DATABASE_URL` uses `postgresql://`.

## Authentication

JWT-based auth with refresh tokens, bcrypt password hashing, and role-based access control.

### Demo login

| Email | Password | Role |
|-------|----------|------|
| `admin@demo.com` | `Admin123!` | `hr_admin` |

### API endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/login` | Email/password login |
| POST | `/api/auth/refresh` | Refresh access token |
| POST | `/api/auth/logout` | Revoke refresh token session |
| POST | `/api/auth/logout-all` | Revoke all sessions (requires auth) |
| GET | `/api/auth/me` | Current user profile |
| POST | `/api/auth/register` | Create user (`hr_admin` only) |
| GET | `/api/auth/dingtalk` | Redirect to DingTalk OAuth authorization |
| GET | `/api/auth/dingtalk/callback` | OAuth callback, link/create user, issue JWT |

### DingTalk OAuth setup

1. Create an app in the [DingTalk Open Platform](https://open.dingtalk.com/).
2. Enable **OAuth login** and add this redirect URI:
   `http://127.0.0.1:8000/api/auth/dingtalk/callback`
3. Set environment variables in `backend/.env`:

```
DINGTALK_CLIENT_ID=your_app_key
DINGTALK_CLIENT_SECRET=your_app_secret
DINGTALK_CORP_ID=your_corp_id
DINGTALK_REDIRECT_URI=http://127.0.0.1:8000/api/auth/dingtalk/callback
FRONTEND_URL=http://localhost:5173
```

On successful DingTalk login, the app stores `dingtalk_user_id` and `dingtalk_corp_id`, links an existing user by email when possible, or creates a new `hr_viewer` account. DingTalk tokens are stored in `users.preferences.dingtalk` for later API calls.


- `hr_admin` — full access + user registration
- `hr_viewer` — view/sync attendance, download Excel
- `manager` — read-only attendance access
- `employee` — limited (future use)

Protected API routes return `401` without a valid Bearer token and `403` for insufficient role.

### Employee sync

`POST /api/sync/employees` (`hr_admin` only) pulls employees from DingTalk:

1. Obtains corp access token (`api.dingtalk.com/v1.1/oauth2/accessToken`)
2. Walks all departments from root dept ID (default `1`)
3. Calls `topapi/v2/user/list` per department (paginated) — DingTalk `contact/user/list`
4. Calls `topapi/v2/user/get` per employee for full profile — DingTalk `contact/user/get`
5. Upserts `employees` table; deactivates records missing from DingTalk

Response includes `added`, `updated`, `deactivated`, and `total_from_dingtalk`.

Requires `DINGTALK_CLIENT_ID` and `DINGTALK_CLIENT_SECRET` with **通讯录只读** permissions.

### Leave and overtime sync

`POST /api/sync/leaves` and `POST /api/sync/overtime` (`hr_admin` / `hr_viewer`) accept:

```json
{ "year": 2026, "month": 5 }
```

Leave sync uses DingTalk `getleaveapproveduration` per approved leave record (from `getupdatedata`), updating `total_personal_leave`, `total_sick_leave`, `total_annual_leave`, and `total_compensatory_leave` (调休). Overtime sync uses `getovertimeapproveduration` with fallback to approval/report data for `total_overtime_hours`.

Run auth migration on PostgreSQL:

```bash
python scripts/run_migrations.py up --file 002_auth_tokens
```
