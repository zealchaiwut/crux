# Quick Start

Get crux running locally on macOS in about 10 minutes.

## Prerequisites

- Python 3.9+ (`python3 --version`)
- A [Neon](https://neon.tech) Postgres database (free tier works)
- [Claude Code](https://docs.claude.com/claude-code) — the `claude` CLI, logged in. By default crux runs its Claude prompts through `claude -p`, so usage bills against your Claude subscription. **No Anthropic API key is needed** unless you switch the provider to the Anthropic API in Settings (optional).
- Git

---

## 1. Clone

```bash
git clone git@github.com:zealchaiwut/crux.git
cd crux
```

## 2. Authenticate the Claude CLI

```bash
claude        # run once, log in, then quit (Ctrl+C)
claude -p "say ok"   # should print: ok
```

If `claude` is not found, install Claude Code first. The app shells out to this
binary for every Claude stage (sharpen, bake-off, weigh, probe, commander spec,
research synthesis).

## 3. Configure environment

```bash
cp .env.example .env
```

Open `.env` and fill in the two required values:

```bash
# Neon Postgres — copy from neon.tech → your project → Connection Details
DATABASE_URL=postgresql://user:password@ep-xxxx-xxxx.region.neon.tech/neondb?sslmode=require

# Auth secret — must be at least 16 chars (the server exits at startup if this is missing or short)
# Generate one: python3 -c "import secrets; print(secrets.token_hex(32))"
AUTH_SECRET=your-generated-secret-here
```

> The server hard-exits if `AUTH_SECRET` is missing or under 16 characters. That is intentional — there is no insecure default on a public URL.
>
> No `ANTHROPIC_API_KEY` is required — Claude calls go through the `claude` CLI.

## 4. Run setup (venv + deps + migrations)

One command does the rest — creates `.venv`, installs requirements, checks the
`claude` CLI, and runs `alembic upgrade head`:

```bash
./scripts/setup.sh
```

It is idempotent (safe to re-run) and stops early with instructions if `.env`
is missing. Prefer to do it by hand? The manual equivalent:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head        # creates case, plan, source, probe, verdict tables
```

## 5. Start the server

```bash
source .venv/bin/activate
make dev
```

`.env` is loaded automatically (via `python-dotenv`). Or run uvicorn directly:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open [http://localhost:8000](http://localhost:8000). You'll land on the login page. The password is whatever you set `AUTH_SECRET` to.

---

## Verify it's working

```bash
curl http://localhost:8000/healthz
# → {"status":"ok","env":"development"}
```

---

## Run the test suite

Tests use SQLite in-memory — no Neon connection required.

```bash
make test
```

---

## Choosing the Claude provider (CLI vs API)

crux can call Claude two ways, switchable at runtime from the in-app **Settings**
modal (gear icon, bottom-left of the sidebar):

- **CLI (default)** — runs `claude -p` against your Claude subscription. Unmetered,
  no API key.
- **Anthropic API** — uses `ANTHROPIC_API_KEY` (set it in `.env`) up to a **USD
  budget** you set in the modal. When spend reaches the budget, the API key is
  missing, or an API call fails, crux automatically **falls back to the CLI** so
  the pipeline keeps working. The modal shows spend vs. budget and a **Reset spend**
  button.

Settings persist to a gitignored `settings.local.json` in the repo root (provider
choice + budget + accumulated spend). Secrets stay in `.env` — that file never
holds the API key. Pricing used for the budget meter: Haiku 4.5 $1/$5 per MTok
(input/output), Sonnet 4.6 $3/$15.

---

## Optional: disable the research loop

If you want to skip external fetching (DuckDuckGo, YouTube, article scraping), set:

```bash
RESEARCH_ENGINE=fallback
```

in your `.env`. Gather calls return empty sources immediately. Everything else (Claude stages) still works normally.

---

## Troubleshooting

**`FATAL: AUTH_SECRET environment variable is required`**
The server reads `.env` via `python-dotenv`. Make sure you have `source .venv/bin/activate` active and that `.env` exists in the repo root.

**`claude CLI not found on PATH` / Claude stages return 502**
Install [Claude Code](https://docs.claude.com/claude-code) and run `claude` once to log in. Verify with `claude -p "say ok"`. Override the binary or model via `CLAUDE_CLI_BIN`, `CLAUDE_CLI_MODEL`, or `CLAUDE_CLI_TIMEOUT` if needed.

**`alembic upgrade head` fails with connection error**
Double-check `DATABASE_URL` in `.env`. The Neon connection string must include `?sslmode=require`.

**Login fails immediately**
The login password is the value of `AUTH_SECRET` in your `.env` — not a separate password field. Paste the raw secret value into the login form.

**Research loop returns empty sources**
The loop hits DuckDuckGo Lite scraping and YouTube transcripts. Both can rate-limit or block depending on network conditions. Set `RESEARCH_ENGINE=fallback` to skip and add sources manually instead.

---

## Next steps

- [tutorial.md](tutorial.md) — full walkthrough of creating a case end-to-end
- [architecture.md](architecture.md) — how the system is built
- [workflow.md](workflow.md) — how work flows from idea to shipped
