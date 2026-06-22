# M9 — Real web sources with pick-to-attach

**Date:** 2026-06-22
**Sprint label:** sprint-9
**Default labels:** sprint-9, milestone:m9
**Status:** drafted

> Stage 2 (Gather) currently runs the research loop against a `StubFetcher`
> (`services/research_orchestrator.py:75`), so it produces placeholder sources
> instead of real ones. Real fetchers already exist (`WebSearchFetcher`,
> `ArticleReaderFetcher`, `YouTubeTranscriptFetcher` in `research/fetchers.py`)
> but are not wired in. M9 makes Gather surface **3–5 real candidate sources per
> plan, citation-grounded**, and lets the user **pick which to attach
> (multi-select)** rather than auto-attaching everything. Manual source entry
> (`POST /api/sources`) stays as the fallback. Source of truth: `PRODUCT.md` §5.3
> (Gather), architecture.md (Research Loop). Depends on M2 (research loop) and the
> M9-prior provider routing (Claude via CLI/API in `app/claude_cli.py`).

## Prompts

```
Wire real web fetchers into the custom research engine. In services/research_orchestrator.py, replace the hardcoded StubFetcher() in _CustomEngine.run with the real fetchers from research/fetchers.py: WebSearchFetcher for discovery, then ArticleReaderFetcher / YouTubeTranscriptFetcher to read each candidate's content. Keep RESEARCH_ENGINE=custom as the real-web engine and RESEARCH_ENGINE=fallback as the no-op StubFetcher engine (graceful empty results) — select via config, no code change to switch. Cap fetches with the existing ResearchConfig.max_fetches and handle per-fetch failures (timeouts, blocks, rate-limits) by skipping that candidate with a WARNING log rather than failing the whole gather. The CitationSynthesiser (already routed through app/claude_cli.complete, so it honors the CLI/API provider toggle) grounds each surviving candidate. Out of scope: any UI; persisting candidates.

---

Candidate-suggestion endpoint that does not auto-attach. Add POST /api/plans/{plan_id}/gather/suggest: run the research loop and return 3–5 ranked candidate sources WITHOUT persisting them — each candidate carries kind (book/article/youtube), title, url, claim, citation, a relevance score, and a client-side candidate_id (uuid). Keep the existing POST /api/plans/{plan_id}/gather behavior available but treat suggest as the primary path for the new pick flow. Return an empty list (200, not 500) when the engine yields nothing or when an embedding/LLM dependency is unavailable, mirroring the graceful degradation already added to the related-cases endpoints. Out of scope: storing unpicked candidates; background/async gather.

---

Batch-attach picked sources. Add POST /api/sources/batch accepting a plan_id plus a list of source objects (kind, title, url, claim, citation) and persisting them in one transaction, returning the created Source rows. Reuse the validation in the existing POST /api/sources (valid kind enum, non-empty title/claim/citation, url shape). This is what the pick UI calls after the user selects candidates. Out of scope: dedup against already-attached sources (a later refinement); editing a candidate before attaching.

---

Pick-to-attach UI for suggested sources. In the case detail Gather section, add a "Suggest sources" action per plan that calls POST /api/plans/{id}/gather/suggest and renders the 3–5 returned candidates as selectable SourceCards: each shows kind icon, title, url, claim, and citation, with a checkbox for multi-select. Provide "Select all", a running selected count, and an "Add selected" button that POSTs the chosen candidates to /api/sources/batch and then refreshes the plan's attached sources list. Show a loading state while suggesting (gather spawns network fetches + a claude -p synthesis call, so it is not instant), an empty state ("No sources found — add one manually") when the list is empty, and keep the existing manual "Add source" affordance alongside. Style strictly via CSS custom properties (design tokens); no hard-coded colors. Out of scope: inline editing of a candidate; pagination of candidates.
```

## Posted issues

| # | Title | Size |
|---|-------|------|
