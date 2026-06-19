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

## Research loop (Stage 2)

The `app/research/` module automates source gathering for a case plan. It uses
an LLM query planner to generate search queries, fetches results via
DuckDuckGo and article scraping, retrieves YouTube transcripts, extracts
claims, and synthesises citations.

Key components:

| Module | Purpose |
|---|---|
| `research/planner.py` | `LLMQueryPlanner` — generates search queries from a plan |
| `research/fetchers.py` | `WebSearchFetcher`, `ArticleReaderFetcher`, `YouTubeTranscriptFetcher` |
| `research/extractor.py` | `ClaimExtractor` — extracts claims from fetched content |
| `research/synthesiser.py` | `CitationSynthesiser` — produces cited summaries |
| `research/loop.py` | `runResearchLoop` — orchestrates the full pipeline |

Trigger via API:

```
POST /api/plans/{plan_id}/gather      # gather sources for one plan
POST /api/cases/{case_id}/gather      # gather sources for all plans in a case
GET  /api/plans/{plan_id}/gather-status
```

## API endpoints

```
GET  /api/cases                        # list all cases
GET  /api/cases/{case_id}              # get a single case with plans, probes, sources
POST /api/cases                        # create a case
POST /api/cases/sharpen                # LLM-sharpen a raw problem statement
POST /api/cases/{case_id}/bake-off     # generate competing plans (A/B/C)
POST /api/cases/{case_id}/rerank       # rerank plans after evidence gathering
POST /api/cases/{case_id}/probe        # design a next probe
POST /api/cases/{case_id}/verdict      # log a verdict for the active probe

GET  /api/sources?plan_id={id}         # list sources for a plan
POST /api/sources                      # manually add a source

POST /api/plans/{plan_id}/gather       # run research loop for a plan
POST /api/cases/{case_id}/gather       # run research loop for all plans
GET  /api/plans/{plan_id}/gather-status
```

## Running tests

```bash
make test
```
