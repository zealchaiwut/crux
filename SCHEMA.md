# Schema

Database: Neon Postgres. Migrations managed by Alembic (revision `i9j0k1l2m3n4`).

## Enum types

| Name | Values |
|---|---|
| `stage_enum` | `sharpened`, `bake_off`, `gather`, `weigh`, `probe`, `verdict` |
| `plan_label_enum` | `A`, `B`, `C` |
| `source_kind_enum` | `book`, `article`, `youtube` |
| `probe_type_enum` | `measurement`, `lab-test`, `behaviour-experiment`, `prototype` |
| `probe_status_enum` | `designed`, `running`, `confirmed`, `killed`, `inconclusive` |
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

### `case_embedding`

Added in sprint 7 (issue #68). Stores pre-computed Claude embedding vectors for semantic related-case matching.

| Column | Type | Notes |
|---|---|---|
| `case_id` | varchar(36) | PK, FK → case.id ON DELETE CASCADE |
| `embedding` | text | NOT NULL — JSON-serialized float array (256 dimensions) |
| `model_version` | varchar(128) | NOT NULL — model ID used to produce this embedding |
| `created_at` | timestamptz | NOT NULL |
