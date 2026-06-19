# crux — UI kit

A high-fidelity recreation of the crux research console: a single-user tool that
turns a messy problem into competing Plan A/B/C bets, grounds each in cited
sources, designs the one cheapest decisive probe, and **refuses to show an action
plan until a verdict is logged**.

Open `index.html` for the interactive click-through.

## Layout

Two-pane shell matching commander:

```
┌────────┬──────────────────────────────┬───────────┐
│ sidebar│  main (cases / case detail)  │  right    │
│ 208px  │  flex                        │  rail 288 │
└────────┴──────────────────────────────┴───────────┘
```

## Files

- `index.html` — orchestrates routing (cases ↔ case detail ↔ verdicts), the New Case modal, and the light/dark toggle.
- `Shell.jsx` — `Wordmark`, `Sidebar` (nav + project switcher + mono footer), `RightRail` (prompt card, probes running, recent verdicts).
- `screens.jsx` — `CasesScreen`, `CaseScreen`, `VerdictScreen`, `NewCaseModal`, `TopBar`.
- `data.js` — fictional sample cases (`window.CRUX_DATA`).

## Composition

Screens compose the published design-system primitives via
`window.CruxDesignSystem_bd6ca7` (the compiled bundle): `CaseCard`, `StageBar`,
`PlanCard`, `ProbeCard`, `LockedPlan`, `BakeOffStrip`, `Pill`, `Button`, `Input`.
Nothing is re-implemented — the kit is a thin orchestration layer.

## Interactions to try

1. **New case** → paste box → "Sharpen" → confirmation step → "Create case".
2. Click any **case row** → full case detail with the bake-off, plans + sources, the probe, and the locked/unlocked action plan.
3. Open a **closed** case (CASE-0142 / CASE-0139) to see the unlocked action plan and verdict.
4. **Verdicts** in the sidebar → the knowledge-base log.
5. Toggle **light / dark** (top-right) — both are first-class.

> Icons: Tabler Icons webfont (CDN). Mono fallback: JetBrains Mono (≈ SF Mono).
