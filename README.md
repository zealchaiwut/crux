# crux

FastAPI backend service.

## Local development

```bash
pip install -r requirements.txt

# Start with auto-reload
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Or via Make
make dev
```

## Health check

```
GET /healthz  →  {"status": "ok", "env": "development"}
```

## Authentication

All routes except `/login` require a valid session cookie. Set the password via environment variable:

```bash
export AUTH_PASSWORD=your-password
export AUTH_SECRET=your-secret-key   # used to sign session cookies
```

See `.env.example` for all required variables.

## Database (Neon Postgres + Alembic)

```bash
# Apply migrations
alembic upgrade head

# Create a new migration
alembic revision --autogenerate -m "description"
```

## API routes

```
GET  /api/cases                       — list all cases (with plans, stage, verdict state)
GET  /api/cases/{id}                  — case detail including plans
POST /api/cases/sharpen               — call Claude to sharpen a raw problem statement
POST /api/cases                       — create a case at Stage 0 (sharpened)
POST /api/cases/{id}/bake-off         — generate Plan A/B/C via Claude and advance to Stage 1
POST /api/cases/{id}/rerank           — re-rank plans with user context, advance to Stage 3
POST /api/cases/{id}/probe            — design a probe via Claude, advance to Stage 4
POST /api/cases/{id}/verdict          — record verdict outcome, advance to Stage 5

GET  /api/sources?plan_id=<id>        — list sources for a plan
POST /api/sources                     — add a source to a plan
```

## Running tests

```bash
make test
```
