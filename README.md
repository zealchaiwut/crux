# crux

A personal research-and-diagnosis tool. It sharpens a messy problem into a falsifiable statement, generates competing root-cause hypotheses (A/B/C), researches each with cited sources, re-ranks them against your own data, designs the single cheapest experiment that settles it — then refuses to show an action plan until you log a test result.

Companion to [commander](https://github.com/zealchaiwut/commander) (which builds the probe prototypes) and perf-coach (where winning prototypes graduate).

## Docs

- [Quick Start](docs/quickstart.md) — run it locally in 10 minutes
- [Architecture](docs/architecture.md) — how the system is built
- [Milestones](docs/milestones.md) — sprint history
- [PRODUCT.md](PRODUCT.md) — what crux is and why
- [DESIGN.md](DESIGN.md) — design system and component specs
- [SCHEMA.md](SCHEMA.md) — full database schema reference

## Status

Five sprints complete. All five pipeline stages are live:

| Stage | Status |
|---|---|
| 0 — Sharpen | ✓ |
| 1 — Bake-off (Plans A/B/C) | ✓ |
| 2 — Gather (custom research loop) | ✓ |
| 3 — Weigh (re-rank against your data) | ✓ |
| 4 — Probe design + Commander spec | ✓ |
| 5 — Verdict gate + action plan | ✓ |
| Prior learnings (related-case recall) | ✓ |

## Local development

```bash
# 1. Clone and create venv
git clone git@github.com:zealchaiwut/crux.git && cd crux
python3 -m venv .venv && source .venv/bin/activate

# 2. Install
pip install -r requirements.txt

# 3. Configure — copy .env.example, fill in DATABASE_URL, AUTH_SECRET, ANTHROPIC_API_KEY
cp .env.example .env

# 4. Migrate
alembic upgrade head

# 5. Run
make dev
```

See [docs/quickstart.md](docs/quickstart.md) for the full setup guide including troubleshooting.

## Health check

```
GET /healthz  →  {"status": "ok", "env": "development"}
```

## Authentication

All routes except `/login` require a valid session cookie. The login password is the value of `AUTH_SECRET`.

```bash
# Generate a strong secret
python3 -c "import secrets; print(secrets.token_hex(32))"
```

```bash
# Required env vars
AUTH_SECRET=<min 16 chars — server exits at startup if missing>
DATABASE_URL=<Neon Postgres connection string>
ANTHROPIC_API_KEY=<Claude API key>
```

See `.env.example` for all variables.

## API endpoints

```
GET  /api/cases                        # list all cases; ?q=<keyword> ?stage=<stage> ?verdict=confirmed|killed|inconclusive|open
GET  /api/cases/{case_id}              # full case with plans, sources, probe, verdict
PATCH /api/cases/{case_id}            # edit sharpened statement and/or not-investigating list (locked at verdict stage)
POST /api/cases                        # create a case
POST /api/cases/sharpen                # sharpen a raw problem statement
POST /api/cases/{case_id}/bake-off     # generate competing plans A/B/C
POST /api/cases/{case_id}/rerank       # re-rank plans against user context
POST /api/cases/{case_id}/probe        # design the cheapest decisive test
POST /api/cases/{case_id}/verdict      # log a verdict for the active probe

GET  /api/sources?plan_id={id}         # list sources for a plan
POST /api/sources                      # manually add a source

POST /api/plans/{plan_id}/gather       # run research loop for a plan
POST /api/cases/{case_id}/gather       # run research loop for all plans
GET  /api/plans/{plan_id}/gather-status

GET  /api/cases/{case_id}/related          # list prior cases ranked by similarity
POST /api/cases/related-text               # find related cases by raw text (pre-case-creation)
POST /api/cases/{case_id}/probe/commander-spec  # generate/cache commander spec; ?force=true regenerates

PATCH /api/probes/{probe_id}/status        # update probe status; only designed→running is supported

GET  /api/verdicts                         # list all verdicts; ?outcome=confirmed|killed|inconclusive  ?q=keyword
```

## Running tests

```bash
make test
```

Tests use SQLite in-memory — no Postgres connection required.
