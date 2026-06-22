# Changelog

Per-sprint changelog for crux. Entries are written by the documentor when a
sprint finishes. Dated per-sprint files live under [docs/changelog/](docs/changelog/).

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
