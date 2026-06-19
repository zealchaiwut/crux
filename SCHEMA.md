# Schema

Database: Neon Postgres. Migrations managed by Alembic (revision `a1b2c3d4e5f6`).

## Enum types

| Name | Values |
|---|---|
| `stage_enum` | `sharpened`, `bake_off`, `gather`, `weigh`, `probe`, `verdict` |
| `plan_label_enum` | `A`, `B`, `C` |
| `source_kind_enum` | `book`, `article`, `youtube` |
| `probe_type_enum` | `measurement`, `lab-test`, `behaviour-experiment`, `prototype` |
| `probe_status_enum` | `designed`, `running`, `confirmed`, `killed` |
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

### `plan`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `case_id` | UUID | FK → case.id ON DELETE CASCADE, NOT NULL |
| `label` | plan_label_enum | NOT NULL |
| `mechanism` | text | |
| `prior` | text | |
| `current_rank` | integer | |

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
