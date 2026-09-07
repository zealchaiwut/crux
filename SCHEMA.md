# Schema

Database: Neon Postgres. Migrations managed by Alembic (revision `q7r8s9t0u1v2`).

## Enum types

| Name | Values |
|---|---|
| `stage_enum` | `sharpened`, `bake_off`, `gather`, `weigh`, `probe`, `verdict` |
| `plan_label_enum` | `A`, `B`, `C` |
| `source_kind_enum` | `book`, `article`, `youtube` |
| `support_status_enum` | `supports`, `partial`, `contradicts`, `unverified` |
| `probe_type_enum` | `measurement`, `lab-test`, `behaviour-experiment`, `prototype` |
| `probe_status_enum` | `designed`, `running`, `confirmed`, `killed`, `inconclusive` |
| `probe_horizon_enum` | `short`, `mid`, `long` (issue #168) |
| `verdict_outcome_enum` | `confirmed`, `killed`, `inconclusive` |

## Tables

### `case`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK, default `gen_random_uuid()` |
| `raw_problem` | text | NOT NULL |
| `sharpened` | text | |
| `not_investigating` | text | |
| `stage` | stage_enum | NOT NULL |
| `created_at` | timestamptz | NOT NULL, default `now()` |
| `weigh_context` | text | Persisted user context from Stage 3 re-rank (issue #10) |
| `summary` | text | JSON-encoded AI-generated case summary; cached after first generation (issue #94) |

### `plan`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `case_id` | UUID | FK → case.id ON DELETE CASCADE, NOT NULL |
| `label` | plan_label_enum | NOT NULL |
| `name` | text | |
| `mechanism` | text | |
| `prior` | text | |
| `current_rank` | integer | |
| `standing` | text | Qualitative re-rank status: `ruled-in`, `ruled-out`, or null (issue #10) |
| `rationale` | text | nullable — 1–2 sentence LLM-generated explanation of why this plan holds its rank, citing a specific source or data point where relevant (issues #131, #132) |

### `source`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `plan_id` | UUID | FK → plan.id ON DELETE CASCADE, NOT NULL |
| `kind` | source_kind_enum | NOT NULL |
| `title` | text | |
| `url` | text | |
| `claim` | text | |
| `citation` | text | |
| `support_status` | support_status_enum | NOT NULL, default `unverified` — updated enum values in sprint 54 (issue #153) |
| `support_rationale` | text | nullable — free-text explanation of verification result; replaces `rationale` column (issues #99, #155) |
| `manually_overridden` | boolean | NOT NULL, default false — true when support_status was set by user override (issue #100) |
| `extracted_content` | text | nullable — raw fetched source content, capped at 50,000 chars with a `[TRUNCATED]` sentinel; stays null on fetch failure (issue #171) |
| `content_summary` | text | nullable — Claude-generated neutral 2–4 sentence summary of the source's own content, independent of support status (issue #171) |

### `source_verification`

Added in sprint 11 (issue #99). Stores raw pipeline results from the fetch→Claude→DB verification run before the status is accepted onto the source row.

| Column | Type | Notes |
|---|---|---|
| `id` | varchar(36) | PK |
| `source_id` | varchar(36) | FK → source.id ON DELETE CASCADE, NOT NULL |
| `verdict` | varchar(32) | NOT NULL — mirrors support_status_enum values |
| `summary` | text | nullable — brief summary of source content |
| `reason` | text | nullable — Claude's reasoning for the verdict |
| `created_at` | timestamptz | nullable |

### `probe`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `case_id` | UUID | FK → case.id ON DELETE CASCADE, NOT NULL |
| `type` | probe_type_enum | NOT NULL |
| `target_metric` | text | |
| `cost` | text | |
| `time` | text | |
| `note` | text | |
| `steps` | JSON | Ordered list of 3–6 action steps for running the probe (issue #93) |
| `duration` | text | How long to run the probe, e.g. "7 days" (issue #93) |
| `decision_rule` | text | Confirmatory outcome and kill condition, e.g. "if X ≥ Y → proceed" (issue #93) |
| `status` | probe_status_enum | NOT NULL, default `designed` |
| `horizon` | probe_horizon_enum | nullable — `short`, `mid`, or `long`; each case now holds three probes, one per horizon (issue #168) |
| `due_date` | date | |
| `commander_spec` | text | |

### `verdict`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `probe_id` | UUID | FK → probe.id ON DELETE RESTRICT, NOT NULL |
| `outcome` | verdict_outcome_enum | NOT NULL |
| `notes` | text | |
| `decided_at` | timestamptz | NOT NULL, default `now()` |
| `created_at` | timestamptz | Set at verdict creation time; used as `created_at` fallback when `decided_at` is null (issue #55) |

## Environment variables

| Variable | Values | Notes |
|---|---|---|
| `VERIFIER_ENGINE` | `stub` (default), `ai` | Controls which verification backend is used. **`stub` is for development and testing only — it is not production-ready.** The stub uses hardcoded keyword matching to produce deterministic results so the UI can be exercised without a live AI service. Set to `ai` when a real AI verifier is configured (tracked in issue #98). |
| `CRUX_LLM_PROVIDER` | `""` (default), `groq`, `anthropic_api`, `claude_cli` | Selects the LLM backend for pipeline stages. When unset, falls through to the in-app Settings toggle (`cli` vs `api`). When set, that provider is used exclusively. Invalid values or `groq` without `GROQ_API_KEY` abort startup (issue #189). |
| `GROQ_API_KEY` | Groq API key | Required when `CRUX_LLM_PROVIDER=groq`. Obtain from console.groq.com (issue #189). |
| `CRUX_JUDGMENT_MODEL` | model id (default `openai/gpt-oss-120b`) | Groq model for judgment stages (sharpen, plans, weigh, probe, summary), called with structured outputs (issues #189, #190). |
| `CRUX_BULK_MODEL` | model id (default `llama-3.1-8b-instant`) | Groq model for high-volume bulk stages (content summary, dedup, candidate summarization); bulk stages always route here regardless of caller (issue #191). |

## Verdict gate

`GET /api/cases/{id}` enforces a server-side verdict gate on the `plans` field (issue #201):

| Condition | `plans` value |
|---|---|
| Case has **no probe** yet (stages: sharpened, bake_off, gather, weigh) | Full ranked plan list |
| Case has a probe but **no verdict** has been logged | `null` — plans are locked |
| Case has a probe and **a verdict exists** | Full ranked plan list |

This is a **server guarantee**, not a UI convention. The JavaScript layer enforces the same
rule visually, but machine callers (e.g. viral-radar) that call the API directly are also
subject to this gate. Clients must handle `plans: null` and treat it as a locked state.

The `summary` field is **not** gated by verdict — it is available once the case reaches the
probe stage regardless of verdict state (see issue #148).

### `case_embedding`

Added in sprint 7 (issue #68). Stores pre-computed Claude embedding vectors for semantic related-case matching.

| Column | Type | Notes |
|---|---|---|
| `case_id` | varchar(36) | PK, FK → case.id ON DELETE CASCADE |
| `embedding` | text | NOT NULL — JSON-serialized float array (256 dimensions) |
| `model_version` | varchar(128) | NOT NULL — model ID used to produce this embedding |
| `created_at` | timestamptz | NOT NULL |
