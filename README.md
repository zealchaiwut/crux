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

## Running tests

```bash
make test
```
