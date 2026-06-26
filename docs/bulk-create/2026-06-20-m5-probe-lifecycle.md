# M5 — Probe lifecycle

**Date:** 2026-06-20
**Sprint label:** sprint-5
**Default labels:** sprint-5, milestone:m5
**Status:** drafted

> Probes currently sit frozen at `designed` forever. M5 adds the full lifecycle:
> mark a probe running, track its due date, flag overdue probes, and handle the
> most common post-verdict outcome — inconclusive → re-probe — without trashing
> the bake-off and gather work. Depends on M1 (Probe, Verdict gate). Source of
> truth: `PRODUCT.md` §4 (Probe concept), §5.6 (Run + Verdict).

## Prompts

```
Probe status transitions. Add the ability to advance a Probe's status from `designed` → `running` → (verdict logged closes it). Expose a "Mark as running" action on the ProbeCard (only shown when status=designed and a verdict hasn't been logged). Persist the status change via a PATCH /api/probes/{id}/status endpoint. The Verdict gate already handles the final transition — this ticket covers only the designed→running step. Out of scope: due dates (next ticket), re-probe flow (separate ticket).

---

Due date display and overdue flagging. Surface the Probe's due_date on the ProbeCard: show it as a mono date chip when set; highlight it in red (using --red token) when past due and the probe has no verdict. Add a date input to set or update the due date — a small edit affordance on the ProbeCard, no separate modal. Persist via PATCH /api/probes/{id}/due-date. Out of scope: reminders, push notifications — this is display only.

---

Inconclusive re-probe flow. When a Case's verdict is `inconclusive`, offer a "Design new probe" action that triggers a second probe design (reusing the existing POST /api/cases/{id}/probe endpoint) without resetting stage, bake-off plans, or gathered sources. The new probe replaces the previous one in the ProbeCard; the old probe and its inconclusive verdict remain in the DB for history. Gate the action behind the existing Verdict gate — it only appears after an inconclusive verdict is logged. Out of scope: multi-probe history UI (show the current probe only; history is for a future milestone).
```

## Posted issues

| # | Title | Size |
|---|-------|------|
