# AGENTS.md

## Cursor Cloud specific instructions

`crux` is a single-process FastAPI web app (Python). It serves a static SPA plus a
JSON API and is backed by PostgreSQL. There is no Node/build step — the frontend is
hand-written HTML/CSS/JS under `app/static/`. Standard commands live in the `Makefile`,
`README.md`, and `docs/quickstart.md`; the notes below only cover non-obvious caveats
for running it in this environment.

### Python env / running commands
- Dependencies are installed into a virtualenv at `.venv` (the startup update script
  refreshes it). Use `.venv/bin/...` or `source .venv/bin/activate` — the bare
  `uvicorn`/`pytest`/`alembic` binaries are **not** on the system `PATH`, so `make dev`
  fails unless the venv is on `PATH` first.

### Environment variables (`.env` is NOT auto-loaded by the app)
- The app reads `os.environ` directly; it does **not** call `load_dotenv()`. So `make dev`
  will hard-exit with `FATAL: AUTH_SECRET ...` unless you export the vars first. Run the
  server like:
  ```bash
  source .venv/bin/activate
  set -a && . ./.env && set +a
  make dev          # uvicorn --reload on 0.0.0.0:8000
  ```
- `.env` already exists in this environment (gitignored) with `AUTH_SECRET`,
  `DATABASE_URL` (local Postgres), and `RESEARCH_ENGINE=fallback`.
- `AUTH_SECRET` doubles as the **login password** (the login form takes the raw secret).
  In this env it is `local_dev_secret_change_me_0123456789`.
- Alembic (`alembic/env.py`) **does** call `load_dotenv()`, so alembic commands pick up
  `.env` without exporting.

### PostgreSQL
- Postgres 16 is installed locally; the `crux` database and schema persist in the VM
  snapshot. It is **not** auto-started — start it each session with:
  ```bash
  sudo pg_ctlcluster 16 main start
  ```
- Connection: `postgresql://postgres:postgres@localhost:5432/crux`.

### Schema provisioning (alembic migration caveat)
- `alembic upgrade head` is **broken on a fresh DB** with the pinned `SQLAlchemy==2.0.51`:
  the initial migration pre-creates the Postgres ENUM types and then `op.create_table`
  re-emits an empty `CREATE TYPE` for the same `sa.Enum(..., create_type=False)` columns,
  failing with `type "stage_enum" already exists`. Do not rely on alembic to build the DB.
- The schema in this environment was created from the ORM models (the same mechanism the
  test suite uses), which works cleanly on Postgres:
  ```bash
  set -a && . ./.env && set +a
  .venv/bin/python -c "from sqlalchemy import create_engine; import os; from app.models import Base; Base.metadata.create_all(create_engine(os.environ['DATABASE_URL']))"
  ```
  `models.py` is the source of truth and already includes every column from all 5
  migrations. This only needs to be re-run if the DB is wiped.

### Auth gotchas
- Every route except `/login` (including `/healthz`) is behind the auth middleware and
  returns `302 -> /login` without a valid `session` cookie.
- Login is rate-limited to 10 attempts / 15 min **per IP, in-memory**. Running the auth
  UAT tests (which make many failed logins) can trip this and cause later logins to
  return `429`. Restart the uvicorn process to clear the limiter.

### Tests
- `make test` (`pytest tests/`) runs ~617 tests. The unit tests use in-memory SQLite and
  need no Postgres/Anthropic. Expect ~40 pre-existing failures unrelated to environment
  setup:
  - `test_issue_2.py`: reads `alembic/versions/*.py` via `glob()[0]`, which is
    filesystem-order dependent and now picks the wrong migration file.
  - `test_case_detail__7.py`, `test_new_case_modal__6.py`: assert on static JS content
    that has since evolved.
- The `*_uat.py` and `test_manual_source_attachment__9.py` files are **acceptance tests
  that require a running server**. They pass when the server is up and `UAT_BASE_URL` is
  exported:
  ```bash
  set -a && . ./.env && set +a
  export UAT_BASE_URL=http://localhost:8000
  .venv/bin/pytest tests/test_issue_3_uat.py tests/test_manual_source_attachment__9.py
  ```
- Do **not** export `DATABASE_URL` in the shell when running the full `make test`, or the
  live-DB alembic tests in `test_issue_2.py` (skipped by default) will run and fail due to
  the alembic caveat above.

### LLM-backed stages
- The AI pipeline stages (sharpen, bake-off, weigh, probe, commander-spec, research
  synthesis) require `ANTHROPIC_API_KEY`, which is not set here. The app still boots and
  all CRUD/DB flows work; those endpoints return `502` without the key. Case creation
  (`POST /api/cases`) does not need the key. `RESEARCH_ENGINE=fallback` disables the
  external research fetchers.

### No linter configured
- There is no flake8/ruff/black/mypy config in the repo, so there is no lint step to run.
