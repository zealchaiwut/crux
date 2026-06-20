# Quick Start

Get crux running locally on macOS in about 10 minutes.

## Prerequisites

- Python 3.9+ (`python3 --version`)
- A [Neon](https://neon.tech) Postgres database (free tier works)
- An [Anthropic API key](https://console.anthropic.com)
- Git

---

## 1. Clone

```bash
git clone git@github.com:zealchaiwut/crux.git
cd crux
```

## 2. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

## 3. Install dependencies

```bash
pip install -r requirements.txt
```

## 4. Configure environment

```bash
cp .env.example .env
```

Open `.env` and fill in the three required values:

```bash
# Neon Postgres — copy from neon.tech → your project → Connection Details
DATABASE_URL=postgresql://user:password@ep-xxxx-xxxx.region.neon.tech/neondb?sslmode=require

# Auth secret — must be at least 16 chars (the server exits at startup if this is missing or short)
# Generate one: python3 -c "import secrets; print(secrets.token_hex(32))"
AUTH_SECRET=your-generated-secret-here

# Anthropic API key — from console.anthropic.com
ANTHROPIC_API_KEY=sk-ant-...
```

> The server hard-exits if `AUTH_SECRET` is missing or under 16 characters. That is intentional — there is no insecure default on a public URL.

## 5. Run migrations

```bash
alembic upgrade head
```

This creates all five tables (`case`, `plan`, `source`, `probe`, `verdict`) in your Neon database.

## 6. Start the server

```bash
make dev
```

Or directly:

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
