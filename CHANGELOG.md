# Changelog

Per-sprint changelog for crux. Entries are written by the documentor when a
sprint finishes. Dated per-sprint files live under [docs/changelog/](docs/changelog/).

## Sprint 52 (2026-06-26)

- #130: Fix WeighPanel not rendering in CaseDetailScreen
- #131: Add rationale field to Weigh plan output
- #132: Persist plan rationale from Weigh rerank response
- #133: Render per-plan rationale text in PlanCard
- #134: Make weigh context optional in WeighPanel UI
- #135: Add tests for rerank rationale and WeighPanel regression

## Sprint 13 (2026-06-26)

- #71: Wire _VALID_VERDICT_PARAMS into verdict query validation
- #72: Verify OUTCOME_CHIP_DEFS verdict values match API response
- #73: Verify open/closed CasesScreen vars are active, not orphaned
- #74: Add API error fallback message in edit modal handleSave
- #75: Return stage as string enum in all case API responses
- #86: Replace bare except in research_orchestrator with specific fetch exceptions
- #87: Distribute relevance_score evenly by actual candidate count in suggest
- #88: Tighten sources type hint to List[Dict[str, Any]] in batch endpoint
- #111: Add error logging to silent catch blocks in cases.js
- #112: Document SourceChip override state persistence behavior
- #113: Extract inline font-size styles to .chip-expanded CSS class
- #114: Move os import to module level in routers/sources.py
- #115: Document VERIFIER_ENGINE env var and stub verifier in SCHEMA.md

## Sprint 12 (2026-06-25)

- #36: [follow-up] Clarify httpx timeout semantics in commander spec generation
- #37: [follow-up] Validate plan presence before spec generation
- #38: [follow-up] Replace deprecated navigator.clipboard fallback
- #39: [follow-up] Extract UI state constants
- #40: [follow-up] Clarify httpx timeout semantics
- #41: [follow-up] Validate plan presence before spec generation
- #42: [follow-up] Replace deprecated clipboard fallback
- #43: [follow-up] Extract UI state constants
- #54: [follow-up] GET /api/verdicts keyword search should filter at database layer
- #55: [follow-up] GET /api/verdicts timestamp field null-handling
- #56: [follow-up] GET /api/verdicts inconsistent empty-string vs None defaults

## Sprint 11.1 (2026-06-24)

- #98: Add source-verifier service for claim support detection

## Sprint 11 (2026-06-24)

- #99: Add source verification endpoints (single & batch)
- #100: Colour SourceChip by support_status with Verify actions
- #101: Add integration tests for source verification pipeline

## Sprint 10 (2026-06-24)

- #92: Make Weigh stage optional: skip context input
- #93: Expand Probe into full structured experiment plan
- #94: Add AI-powered Case Summary generator
- #95: Show Case Summary section at probe stage
- #96: Split case gate: Summary pre-verdict, ActionPlan stays locked

## Sprint 8 (2026-06-22)

- #81: Wire real web fetchers into custom research engine
- #82: Add suggest endpoint for non-persisting candidate sources
- #83: Add POST /api/sources/batch to attach multiple sources
- #84: Add pick-to-attach UI for suggested sources in Gather

## Sprint 7 (2026-06-21)

- #68: Replace TF-IDF with Claude embedding-based similarity for related cases
- #35: Extract UI state constants to eliminate string literals in cases.js
- #34: Replace deprecated navigator.clipboard fallback with error-reporting copy path
- #33: Validate plan presence before Commander spec generation (422 if no plans)
- #32: Clarify httpx timeout semantics in commander spec generation
- #31: Clarify httpx timeout semantics in commander spec generation

## Sprint 6 (2026-06-21)

- #64: Add search and filter params to GET /api/cases
- #65: Add search input and filter chips to Cases list
- #66: Allow editing case sharpened statement and not-investigating list

## Sprint 5 (2026-06-20)

- #48: Add 'Mark as Running' transition for Probes
- #51: Add GET /api/verdicts list endpoint
- #52: Build Verdicts list screen with search, filter, and grouping

## Sprint 4 (2026-06-19)

- #26: Generate Commander Spec for Prototype Probes via Claude API
- #27: Wire 'Send to commander' on ProbeCard to display spec
- #28: Build related-case matching service over Verdicts
- #29: Surface prior learnings on new Cases

## Sprint 3 (2026-06-19)

- #17: Scaffold research-loop module and LLM query planner
- #18: Implement web-search and article-reader fetchers
- #19: Implement YouTube transcript fetcher for research loop
- #20: Implement claim extractor and citation-aware synthesiser
- #21: Automate Stage 2 source gathering via research loop

## Sprint 2 (2026-06-19)

- #5: Build Cases List screen with CaseCard rows
- #6: Add New Case modal with Sharpen (Stage 0)
- #7: Build Case detail page scaffold with StageBar
- #8: Generate and display Plan A/B/C bake-off at Stage 1
- #9: Add manual source attachment form to Plan cards
- #10: Re-rank Plans Against User Data at Stage 3
- #11: Design probe type and target metric at Stage 4
- #12: Enforce verdict gate and log verdict action (Stage 5)

## Sprint 1 (2026-06-19)

- #1: Scaffold FastAPI backend and configure Render deploy
- #2: Set up Neon Postgres schema and Alembic migrations
- #3: Implement single-user password auth with session cookies
- #4: Build app shell with design tokens and theme toggle
