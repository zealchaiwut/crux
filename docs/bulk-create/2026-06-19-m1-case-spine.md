# M1 — Case spine (structure-first)

**Date:** 2026-06-19
**Sprint label:** sprint-2
**Default labels:** sprint-2, milestone:m1
**Status:** drafted

> The full five-stage Case pipeline with the Verdict gate, usable end-to-end with
> **manually pasted** sources (the custom research loop replaces the paste in M2).
> Depends on M0. Sources of truth: `PRODUCT.md` §4–6, design components in
> `design_handoff_crux/components/case/`, screens in `reference_screens/`.

## Prompts

```
Cases list screen. Build the Cases list (reference_screens/screens.jsx → CasesScreen): Open and Closed sections of CaseCard rows; each CaseCard shows the stage spine (current stage + 5-pip indicator + Case ID) and a body (title, verdict pill, bake-off mini-strip); closed cases tint the spine by verdict. Primary "New case" action (Button variant="crux", one per screen). Right rail: prompt card, "probes running", "recent verdicts". Reads Cases from the DB; empty state when none. Stage ramp colors --st-1..--st-5. Out of scope: New Case creation flow (separate ticket) — button can open the modal stub.

---

New Case modal + Sharpen (Stage 0). Build the New Case modal (reference_screens → NewCaseModal): paste box for a messy problem → "Sharpen" calls the Claude API to return a sharpened, falsifiable statement plus a "not investigating" list → confirmation step shows both for review → "Create case" persists a Case at stage 0 and routes to its detail. Sharpened statement and not-investigating chips render in the Case header. Use the stage prompt approach from PRODUCT.md §9 (LLM). Out of scope: bake-off generation.

---

Case detail shell + StageBar. Build the Case detail page scaffold (reference_screens → CaseScreen) with the StageBar header (5 stages Sharpen→Bake-off→Gather→Weigh→Probe, current 0–4, 5=closed) driven by the Case's stage; the sharpened statement block and "not investigating" chips; and slots/sections for the bake-off, probe, and action plan filled by later tickets. Navigation from a CaseCard opens this page. Out of scope: the stage contents themselves.

---

Bake-off — generate Plan A/B/C (Stage 1). On a Case at stage 1, call the Claude API to generate three competing root-cause Plans (labels A/B/C), each with a one-line mechanism and a prior. Persist as Plan rows. Render with PlanCard (mono key, name, prior chip, mechanism, sources list; lead style for the leader) and the signature BakeOffStrip (racing bars; standing 0–1 per plan; leader fills violet; ruled-out fades + strikes; winner gets ✓ WON). Advance the Case stage. Out of scope: sources, weighing, probe.

---

Manual source paste (Stage 2 / Gather). Let me attach cited sources to a Plan by hand: a paste/add form capturing kind (book/article/youtube), title, url, claim, citation → persists Source rows linked to the Plan. Render as SourceChip (book=amber, article=blue, youtube=red, optional href) inside each PlanCard. This is the manual stand-in the M2 research loop later auto-fills. Out of scope: any automated fetching/synthesis.

---

Weigh against my data (Stage 3). On a Case at stage 3, give me a box to paste my own numbers/context, then call the Claude API to re-rank the Plans by fit to me and flag any I can already rule in or out. Update each Plan's current_rank and standing; BakeOffStrip and PlanCard lead styling reflect the new leader; ruled-out plans fade + strike. Persist the pasted context on the Case. Out of scope: probe design.

---

Probe design + type + target metric (Stage 4). On a Case at stage 4, call the Claude API to design the single cheapest decisive test for the leading Plan(s): classify type (measurement/lab-test/behaviour-experiment/prototype — honest, e.g. "this is a blood test, see a doctor", never an invented app), name one target metric, and add cost/time/note. Persist a Probe (status=designed). Render ProbeCard (type, big mono targetMetric, cost/time, note); only type="prototype" shows a "Send to commander" affordance (spec generation is M3 — stub/disabled here). Out of scope: verdict, action plan.

---

Verdict gate + Log verdict (Stage 5 + gate). Enforce product law: never render an action plan for a Case without a logged Verdict. Show the action plan inside LockedPlan — hatched, lock-iconed panel until unlocked. "Log verdict" records a Verdict (outcome confirmed/killed/inconclusive + notes), updates Probe status, moves the Case to closed (stage 5), and unlocks LockedPlan to reveal the action plan. Verdicts are kept forever, including dead ends. Out of scope: cross-case verdict memory (M4).

---

Verdict log screen. Build the Verdicts screen (reference_screens → VerdictScreen): the confirmed/killed knowledge-base log across all Cases — each entry shows the Case, outcome pill (confirmed/killed/inconclusive), the decided metric, notes, and a link back to the Case. Sections or filters for confirmed vs killed. Read-only list from Verdict rows. Out of scope: surfacing these on new related Cases (M4).
```

## Posted issues

| # | Title | Size |
|---|-------|------|
