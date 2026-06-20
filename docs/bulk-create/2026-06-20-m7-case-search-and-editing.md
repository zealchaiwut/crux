# M7 — Case search & filtering

**Date:** 2026-06-20
**Sprint label:** sprint-7
**Default labels:** sprint-7, milestone:m7
**Status:** drafted

> The Cases list becomes hard to navigate past ~20 cases and there is no way to
> correct a sharpened statement after creation. M7 adds keyword search and
> outcome/stage filtering to the list, and a lightweight case-editing flow for
> the fields that matter most. Depends on M1 (Cases list, Case detail). Source
> of truth: `PRODUCT.md` §6 (Cases list screen).

## Prompts

```
Case search and filter API. Extend GET /api/cases to accept: ?q=<keyword> (search across sharpened statement and plan mechanisms, case-insensitive), ?stage=<stage_enum> (filter by current stage), and ?verdict=<confirmed|killed|inconclusive|open> (filter by verdict outcome; "open" means no verdict logged yet). All params are optional and composable. Out of scope: full-text index — a simple ILIKE / LIKE scan is sufficient for a single-user dataset.

---

Case list search and filter UI. Add a search input and filter row to the Cases list screen. The search input debounces at 300ms and filters the list live. Filter chips for stage (All / Sharpened / Bake-off / Gather / Weigh / Probe / Verdict) and outcome (All / Open / Confirmed / Killed / Inconclusive) sit below the input. Active filters show a clear-all affordance. Empty state when no cases match. Out of scope: saved searches.

---

Case editing. Allow editing the sharpened statement and not-investigating list on an existing Case without resetting its stage or downstream data (plans, sources, probe, verdict all stay intact). Surface a small edit affordance on the Case detail header — an inline edit or a minimal modal. Persist via PATCH /api/cases/{id} accepting {sharpened?, not_investigating?}. Gate: only allow editing when stage < verdict (a closed case is immutable). Out of scope: editing plans or probe fields directly.
```

## Posted issues

| # | Title | Size |
|---|-------|------|
