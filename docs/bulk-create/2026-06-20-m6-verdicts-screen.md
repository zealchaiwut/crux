# M6 — Verdicts screen & knowledge base

**Date:** 2026-06-20
**Sprint label:** sprint-6
**Default labels:** sprint-6, milestone:m6
**Status:** drafted

> The sidebar Verdicts nav item exists but leads nowhere. M6 builds it out as a
> queryable knowledge base: all confirmed causes and killed hypotheses across
> every Case, filterable by outcome and searchable by keyword. This is what turns
> the verdict log from an archive into something you actually consult before
> starting a new Case. Depends on M1 (Verdict log, Case history). Source of
> truth: `PRODUCT.md` §5.7 (Review), §6 (Verdict log screen).

## Prompts

```
Verdicts list API. Add GET /api/verdicts returning all verdicts with their parent probe (type, target_metric) and case (sharpened snippet, id) — newest first. Support query params: ?outcome=confirmed|killed|inconclusive for filtering, and ?q=<keyword> for keyword search across the case's sharpened statement and the verdict's notes. Out of scope: pagination (single-user dataset stays small).

---

Verdicts screen. Build the Verdicts list screen wired to the existing sidebar nav item. Each row shows: the outcome pill (confirmed/killed/inconclusive), the case's sharpened statement as the title, the probe's target metric in mono, and a link back to the source Case. Group by outcome (Confirmed Causes → Killed Hypotheses → Inconclusive) or show flat newest-first — a toggle. Add a keyword search input and outcome filter chips at the top. Empty state per group when nothing matches. Out of scope: editing verdicts — they are immutable once logged (PRODUCT.md §4).
```

## Posted issues

| # | Title | Size |
|---|-------|------|
