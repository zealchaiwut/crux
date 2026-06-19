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

## Running tests

```bash
make test
```
