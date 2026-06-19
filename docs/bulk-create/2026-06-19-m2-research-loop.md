# M2 — Custom research loop

**Date:** 2026-06-19
**Sprint label:** sprint-3
**Default labels:** sprint-3, milestone:m2
**Status:** drafted

> The heaviest chunk, deliberately after the spine: a custom research engine that
> auto-fills Stage 2 (Gather), replacing M1's manual source paste. Built as its own
> swappable/stubbable module. This is the biggest effort + quality risk
> (`PRODUCT.md` §11) — borrowed engine (e.g. gpt-researcher) stays a fallback.
> Depends on M1. Source of truth: `PRODUCT.md` §9 (research loop subsystem) + §11.

## Prompts

```
Research-loop module scaffold + query planner. Create the research loop as its own isolated module (so it can be swapped or stubbed) with a clean interface: given a Plan (mechanism + prior), an LLM query-planner produces a small set of search queries. Define the pipeline contract query-planner → fetchers → extractor → synthesiser with typed boundaries; ship stub fetchers behind the interface and a config for the per-Case research budget (how many fetches before synthesis — tunable, see §11 open question). Out of scope: real fetchers, extraction, synthesis (later tickets).

---

Web search + article reader fetchers. Implement two fetchers behind the research-loop interface: a web-search fetcher (turns planned queries into result URLs) and an article reader (fetches a URL and extracts readable main text + title). Handle failures gracefully (timeouts, blocked pages, empty content) without crashing the loop; respect the per-Case fetch budget. Return normalized documents (url, title, text) for the extractor. Out of scope: YouTube, extraction/synthesis.

---

YouTube transcript fetcher. Implement a YouTube fetcher behind the research-loop interface: given a video URL/ID, retrieve the transcript and return a normalized document (url, title, text). Degrade gracefully when no transcript exists (auto-captions off, age-gated, etc.) — skip, don't crash — since transcript reliability is a known risk (§11). Respect the fetch budget. Out of scope: extraction/synthesis.

---

Extractor + citation-aware synthesiser. Implement the back half of the loop: an extractor that pulls candidate claims from fetched documents, and a citation-aware synthesiser (Claude API) that produces per-Plan evidence where every claim carries a citation back to its source (kind/title/url). Output maps directly onto Source rows (book/article/youtube, title, url, claim, citation). Guard citation accuracy — no claim without a traceable source. Out of scope: wiring into the Stage 2 UI.

---

Wire research loop into Stage 2 (replace manual paste). Replace M1's manual source paste with the research loop: on a Case entering Stage 2 (Gather), run query-planner → fetchers → extractor → synthesiser per Plan within the configured budget, persist the cited Sources, and render them as SourceChips on each PlanCard. Show progress/empty/failure states; keep the manual paste available as a fallback. Make the engine selection (custom vs borrowed fallback) config-driven per §11. Out of scope: changes to weigh/probe stages.
```

## Posted issues

| # | Title | Size |
|---|-------|------|
