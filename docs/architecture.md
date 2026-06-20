# crux — Architecture

> How the system is built. Pair with PRODUCT.md (what and why) and DESIGN.md (how it looks).

---

## Overview

crux is a single-user FastAPI backend serving a React SPA. There is no build step — the frontend is plain JSX compiled in the browser via Babel. All state lives in Neon Postgres; all LLM calls go through the Anthropic Claude API (Haiku 4.5).

```
Browser (React SPA)
      │  fetch /api/*
      ▼
FastAPI (app/main.py)
  ├── _AuthMiddleware (session cookie gate — blocks all except /login)
  ├── /api/cases            → routers/cases.py
  ├── /api/cases/related    → routers/related_cases.py
  ├── /api/plans/gather     → routers/gather.py
  ├── /api/sources          → routers/sources.py
  ├── /static               → app/static/ (SPA files served directly)
  └── / /cases /probes      → index.html (client-side routing)
        │
        ├── SQLAlchemy ORM ──► Neon Postgres (production)
        │                      SQLite in-memory (tests)
        └── Anthropic SDK  ──► Claude API (Haiku 4.5)
```

---

## Tech Stack

| Layer | Choice | Version |
|---|---|---|
| Backend framework | FastAPI | 0.136.3 |
| ASGI server | Uvicorn | 0.49.0 |
| ORM | SQLAlchemy | 2.0.51 |
| Migrations | Alembic | 1.18.4 |
| Database (prod) | Neon Postgres | — |
| Database (tests) | SQLite in-memory | — |
| Auth | itsdangerous | 2.2.0 |
| LLM | Anthropic Claude Haiku 4.5 | SDK 0.111.0 |
| HTTP client (async) | httpx | 0.28.1 |
| Frontend | React 18 (CDN) + Babel (CDN) | 18.3.1 |
| Icons | Tabler Icons web font | 3.7.0 |
| Styling | Plain CSS custom properties | — |

---

## Module Map

```
app/
├── main.py                   FastAPI app, middleware, static routes, SPA catch-all
├── config.py                 ENV var loading; exits on missing/short AUTH_SECRET
├── models.py                 SQLAlchemy ORM: Case, Plan, Source, Probe, Verdict
├── db.py                     get_db dependency (session factory)
├── auth.py                   Password check, cookie sign/verify, IP rate limiter
│
├── sharpen.py                Stage 0 — Claude makes the problem falsifiable
├── bake_off.py               Stage 1 — Claude generates Plans A/B/C
├── weigh.py                  Stage 3 — Claude re-ranks plans given user context
├── probe.py                  Stage 4 — Claude designs the cheapest decisive test
├── commander_spec.py         Sprint 4 — Claude generates copyable markdown spec for prototype probes
│
├── routers/
│   ├── __init__.py           Exports all four routers
│   ├── cases.py              /api/cases CRUD + all stage-progression endpoints
│   ├── gather.py             /api/plans/{id}/gather, /api/cases/{id}/gather, gather-status
│   ├── related_cases.py      /api/cases/{id}/related, /api/cases/related-text
│   └── sources.py            /api/sources GET + POST
│
├── services/
│   ├── research_orchestrator.py   Engine factory; in-memory gather_status_store
│   └── related_cases.py           TF cosine similarity matcher
│
├── research/                 Custom research loop (M2 / Sprint 3)
│   ├── config.py             ResearchConfig (max_fetches)
│   ├── types.py              Dataclasses: Plan, SearchQuery, SourceDocument, Source
│   ├── loop.py               runResearchLoop — orchestrates the full pipeline
│   ├── planner.py            LLMQueryPlanner — Claude generates search queries from a plan
│   ├── fetchers.py           WebSearchFetcher, ArticleReaderFetcher, YouTubeTranscriptFetcher
│   ├── extractor.py          ClaimExtractor — text → sentence-level factual claims
│   └── synthesiser.py        CitationSynthesiser — Claude selects and cites relevant claims
│
└── static/
    ├── index.html            SPA shell (CDN React + Babel + Tabler Icons)
    ├── styles.css            Design tokens + all component styles (light/dark)
    └── js/
        ├── shell.js          Sidebar, NavItem, Wordmark, theme toggle
        └── cases.js          All case screens, modals, and components
```

---

## Database Schema

Managed by Alembic. Five tables — one aggregate root (`case`) with cascading children.

```
case ──────────────────────────────────────────────────────┐
│ id (UUID PK)                                             │
│ raw_problem      text                                    │
│ sharpened        text                                    │
│ not_investigating text  (JSON array stored as string)    │
│ stage            stage_enum                              │
│ weigh_context    text                                    │
│ created_at       timestamptz                             │
└──┬─────────────────────────────────────────┬─────────────┘
   │ 1:many (CASCADE)                        │ 1:many (CASCADE)
   ▼                                         ▼
plan                                       probe
│ id (UUID PK)                            │ id (UUID PK)
│ case_id  FK → case                      │ case_id  FK → case
│ label    plan_label_enum (A/B/C)        │ type     probe_type_enum
│ name     text                           │ target_metric  text
│ mechanism  text                         │ cost / time / note  text
│ prior    text (float as string)         │ status   probe_status_enum
│ current_rank  integer                   │ due_date  date
│ standing  text (ruled-in/out/null)      │ commander_spec  text
└──┬──────────────────────────────────── └──┬──────────────────
   │ 1:many (CASCADE)                       │ 1:many (RESTRICT)
   ▼                                        ▼
source                                    verdict
│ id (UUID PK)                           │ id (UUID PK)
│ plan_id  FK → plan                     │ probe_id  FK → probe
│ kind     source_kind_enum              │ outcome   verdict_outcome_enum
│ title / url / claim / citation  text   │ notes     text
└──────────────────────────────────────  │ decided_at  timestamptz
                                          └──────────────────────
```

**Delete semantics:** cascade propagates from `case → plan → source` and `case → probe`. Verdicts use `RESTRICT` — you cannot delete a probe that has a logged verdict.

### Enums

| Name | Values |
|---|---|
| `stage_enum` | `sharpened`, `bake_off`, `gather`, `weigh`, `probe`, `verdict` |
| `plan_label_enum` | `A`, `B`, `C` |
| `source_kind_enum` | `book`, `article`, `youtube` |
| `probe_type_enum` | `measurement`, `lab-test`, `behaviour-experiment`, `prototype` |
| `probe_status_enum` | `designed`, `running`, `confirmed`, `killed`, `inconclusive` |
| `verdict_outcome_enum` | `confirmed`, `killed`, `inconclusive` |

---

## The Five Stages

`case.stage` is the single source of truth for where a case is in the pipeline. Transitions are server-side only.

| Stage | Value | What happened | Unlocks |
|---|---|---|---|
| 0 | `sharpened` | Problem made falsifiable | Bake-off |
| 1 | `bake_off` | Plans A/B/C generated | Gather (auto-triggers) |
| 2 | `gather` | Sources researched per plan | Weigh |
| 3 | `weigh` | Plans re-ranked against user data | Probe design (auto-triggers) |
| 4 | `probe` | Cheapest test designed | Log verdict |
| 5 | `verdict` | Probe outcome logged | Action plan (hard gate) |

---

## API Endpoints

### Auth & Health

| Method | Path | Notes |
|---|---|---|
| `GET` | `/healthz` | `{status, env}` — no auth required |
| `GET/POST` | `/login` | HTML form; sets signed session cookie |
| `GET/POST` | `/logout` | Clears session cookie |

### Cases + Stage Progression

| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/cases` | List all cases, newest first |
| `GET` | `/api/cases/{id}` | Full case with nested plans, sources, probe, verdict |
| `POST` | `/api/cases` | Create case (post-sharpening) |
| `POST` | `/api/cases/sharpen` | Claude → `{sharpened, not_investigating}` |
| `POST` | `/api/cases/{id}/bake-off` | Claude generates A/B/C; stage → `gather` |
| `POST` | `/api/cases/{id}/rerank` | Claude re-ranks given `{context}`; stage → `weigh` |
| `POST` | `/api/cases/{id}/probe` | Claude designs test; stage → `probe` |
| `POST` | `/api/cases/{id}/verdict` | Log `{outcome, notes}`; stage → `verdict` |
| `GET` | `/api/cases/{id}/related` | Cosine similarity against closed cases |
| `POST` | `/api/cases/related-text` | Same search by raw text (pre-case-creation) |
| `POST` | `/api/cases/{id}/probe/commander-spec` | Generate/cache markdown spec; `?force=true` regenerates |

### Sources

| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/sources?plan_id={id}` | List sources for a plan |
| `POST` | `/api/sources` | Manually add a source |

### Research / Gather

| Method | Path | Notes |
|---|---|---|
| `POST` | `/api/plans/{id}/gather` | Run full research loop for one plan (synchronous) |
| `POST` | `/api/cases/{id}/gather` | Run for all plans in a case |
| `GET` | `/api/plans/{id}/gather-status` | Poll: `{gather_status, error, sources}` |

---

## Research Loop (M2 / Sprint 3)

The custom research engine lives entirely in `app/research/`. Runs synchronously from the gather router.

```
LLMQueryPlanner
  └─ Claude generates 1–N search queries for the plan's mechanism
        │
        ▼
  Fetchers (budget-limited to RESEARCH_MAX_FETCHES)
  ├── WebSearchFetcher       DuckDuckGo Lite HTML scrape — no API key
  ├── ArticleReaderFetcher   Fetch URL, extract body text
  └── YouTubeTranscriptFetcher  YouTube captions API
        │
        ▼
  ClaimExtractor
  └─ Splits text into sentences; filters for factual claims (≥20 chars, not questions)
        │
        ▼
  CitationSynthesiser
  └─ Claude picks relevant claims and adds verbatim citations → list[Source]
        │
        ▼
  Persisted to `source` table; plan status updated in gather_status_store
```

**Engine toggle:** `RESEARCH_ENGINE=fallback` disables fetching entirely — returns empty sources with no API calls. Useful for testing and for stages that don't need research.

---

## Related Cases (Sprint 4)

`services/related_cases.py` runs TF cosine similarity in-process — no vector database, no embeddings.

- **Query:** tokenised `sharpened + plan mechanisms` of the new case
- **Candidates:** all cases with a logged verdict
- **Threshold:** `RELATED_CASE_SIMILARITY_THRESHOLD` (default `0.1`)
- **Output:** ranked `{case_id, sharpened_snippet, verdict_outcome, similarity_score}`

Results surface as the **Prior Learnings** section in both the Case Detail screen and the New Case confirm step. Swap `_compute_similarity` for an embedding-based approach if recall becomes important at scale.

---

## Commander Spec (Sprint 4)

`app/commander_spec.py` generates a structured markdown handoff spec for `prototype`-type probes.

- Claude prompted to write: build objective, target metric, acceptance criteria, constraints
- Cached in `probe.commander_spec`; returns cache on subsequent calls
- `?force=true` bypasses cache and regenerates
- Returns `422 Unprocessable Entity` if probe type is not `prototype`

---

## Authentication

```
Login POST /login
  │
  ├── check_password(password, AUTH_SECRET)
  │     hmac comparison against stored hash
  │
  ├── is_rate_limited(ip)
  │     10 failed attempts per 15-minute window (in-memory, resets on restart)
  │
  └── create_session_cookie(AUTH_SECRET)
        itsdangerous TimestampSigner → set as HTTP-only, SameSite=strict cookie
```

`AUTH_SECRET` must be at least 16 characters. The server hard-exits at startup if it's missing or too short — there is no insecure default.

---

## Frontend Architecture

No build step. The browser compiles JSX via Babel CDN.

```
index.html
  ├── <script> React 18 (CDN)
  ├── <script> ReactDOM (CDN)
  ├── <script> Babel standalone (CDN, JSX transform)
  ├── <link>   Tabler Icons web font (CDN)
  ├── <link>   styles.css  (tokens + components)
  ├── <script> shell.js    (sidebar, nav, theme toggle)
  └── <script> cases.js    (all case screens + modals)
```

Client routing is managed by React state (`currentView`, `selectedCaseId`). No router library.

**Component tree (cases.js):**
```
App
├── Sidebar (shell.js)
└── CaseListScreen
    ├── CaseCard
    └── NewCaseModal (step: input → sharpen → confirm)
        └── PriorLearnings (related closed cases shown at confirm)

CaseDetailScreen
├── StageBar
├── PriorLearnings (prior learnings from related closed cases)
├── BakeOffStrip
├── PlanCard × 3
│   └── SourceChip × n
├── WeighPanel
├── ProbeCard
│   └── CommanderSpecModal (prototype only)
├── LogVerdictModal
└── LockedPlan / ActionPlan (gated by verdict)
```

---

## Environment Variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `AUTH_SECRET` | **yes** | — | Minimum 16 chars. Server exits at startup if absent. |
| `DATABASE_URL` | **yes** | — | Postgres connection string (Neon format) |
| `ANTHROPIC_API_KEY` | yes (for LLM stages) | — | Sharpen, bake-off, weigh, probe, research loop, commander spec |
| `PORT` | no | `8000` | Uvicorn listen port |
| `ENV` | no | `development` | Surfaced in `/healthz` response |
| `RESEARCH_ENGINE` | no | `custom` | Set `fallback` to disable the research loop |
| `RESEARCH_MAX_FETCHES` | no | `10` | Max fetcher calls per plan per gather run |
| `RELATED_CASE_SIMILARITY_THRESHOLD` | no | `0.1` | Minimum cosine score for related-case results |

---

## Testing

One file per issue (`tests/test_issue_N.py`). All tests use SQLite in-memory — no Postgres required.

```bash
make test                          # full suite
pytest tests/test_issue_26.py      # single issue
pytest -k "commander"              # keyword filter
```

Sprints 1–4 shipped tests for issues #1–#29. LLM calls are mocked in tests.
