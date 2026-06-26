# Handoff: crux design system → codebase

## Overview
This bundle is the crux design system (tokens, foundational CSS, and React UI
components) packaged for implementation in the **crux** repo
(https://github.com/zealchaiwut/crux). It covers the research console: the Cases
list, Case detail (bake-off, plans, probe, locked/unlocked action plan), Verdict
log, and the New Case modal.

## About the design files
The files here are **design references**, not a drop-in library to ship blindly.
- The **CSS** (`styles.css`, `tokens/`, `base.css`, `primitives.css`) *is*
  production-ready — it is a faithful split of the repo's own `tokens.css`, so it
  can replace/extend it directly.
- The **React components** (`components/`) are clean, dependency-free references
  (`import React` only). If the crux frontend is React, adapt them into your
  component conventions; if it is server-rendered, use the CSS + the markup
  patterns as the source of truth and re-implement in your templating layer.
- The **`reference_screens/`** folder is the interactive prototype for look &
  behavior. Recreate these in the crux app's environment — do not serve the HTML.

> Ignore anything referencing `_ds_bundle.js` or `window.CruxDesignSystem_*`.
> That is a *preview-only* mechanism for the design tool. In your codebase you
> import the components directly (`import { Button } from '.../Button'`).

## Fidelity
**High-fidelity.** Final colors, type, spacing, radii, shadows, and interactions.
Recreate pixel-for-pixel using the values in `tokens/`.

## How to integrate

1. **Tokens & base CSS.** Replace (or merge into) the repo's `tokens.css` with
   this `tokens/` set, and link `styles.css` once at the app root. It loads, in
   order: `tokens/fonts.css` → `tokens/colors.css` → `tokens/typography.css` →
   `tokens/spacing.css` → `base.css` → `primitives.css`. All component styling
   reads from these CSS custom properties — never hard-code values.
2. **Theme.** Light is default; dark activates via `data-theme="dark"` on
   `<html>`. Both are first-class — test every view in both.
3. **Icons.** Tabler Icons. Add the webfont (or the React package
   `@tabler/icons-react`). Components take icon names *without* the `ti-` prefix
   (`icon="plus"` → `ti-plus`). ⚠ The repo names an icon font but ships no
   binary — self-host Tabler or install the package.
4. **Fonts.** Sans = system stack (intentional, no custom face). Mono "data
   register" = **SF Mono** (Apple) with **JetBrains Mono** fallback (loaded in
   `tokens/fonts.css`). ⚠ Drop in a licensed SF Mono `@font-face` for exact mono.
5. **Components.** Adapt from `components/core/` and `components/case/`. Each has
   a `.d.ts` (props contract) and a `.prompt.md` (one-liner + usage example).

## Components

**core/**
- `Button` — neutral by default; `variant="crux"` = the one violet primary action per screen. `size`, `icon`, `iconRight`, `disabled`.
- `Pill` — verdict/status badge. `state`: confirmed·killed·inconclusive·awaiting·progress. Color is always paired with a word (colorblind-safe).
- `SourceChip` — one cited source. `kind`: book(amber)·article(blue)·youtube(red). Optional `href`.
- `Card` — neutral surface; `lead` = violet border + tint wash; `hover` = violet lift.
- `Input` — labelled field/textarea; `multiline`, `mono`. Focus shows the violet ring.

**case/** (domain)
- `StageBar` — the 5-stage header (Sharpen→Bake-off→Gather→Weigh→Probe). `current` 0–4, 5=closed.
- `BakeOffStrip` — **signature.** Competing plans as racing bars; leader fills violet, ruled-out fades + strikes, winner gets ✓ WON. `plans: [{key,name,standing(0–1),state}]`.
- `PlanCard` — A/B/C bet: mono key, name, `prior` chip, `mechanism`, `sources[]`; `lead` for the leader.
- `ProbeCard` — the cheapest decisive test: `type`, big mono `targetMetric`, `cost`/`time`, `note`. Only `type="prototype"` shows "Send to commander".
- `LockedPlan` — **signature.** Hatched, lock-iconed panel until `unlocked`; then reveals children. Never show an action plan on an unverified case.
- `CaseCard` — the Cases-list row: stage spine (stage + 5-pip + ID) + body (title, verdict pill, bake-off). Closed cases tint the spine by verdict.

## Screens (see `reference_screens/`)
- **Cases** (`screens.jsx` → `CasesScreen`) — Open / Closed sections of `CaseCard`s; "New case" primary action; right rail (prompt card, probes running, recent verdicts).
- **Case detail** (`CaseScreen`) — StageBar, sharpened statement + "not investigating" chips, the bake-off `PlanCard`s, the `ProbeCard`, and the locked/unlocked action plan + "Log verdict".
- **Verdicts** (`VerdictScreen`) — the confirmed/killed knowledge-base log.
- **New Case** (`NewCaseModal`) — paste box → "Sharpen" → confirmation step → "Create case".
- Shell + sidebar + rail in `Shell.jsx`; sample data in `data.js`.

## Design tokens (key values)
- **Base:** `--bg #f9fafb` · `--surface #fff` · `--surface-2 #f3f4f6` · `--border #e5e7eb` · `--text #111827` · `--text-muted #6b7280` · `--text-sub #9ca3af`.
- **Signature violet:** `--crux #7c3aed` · `--crux-strong #6d28d9` · `--crux-bg #ede9fe` · `--crux-tint #faf8ff`.
- **Semantic (status only):** green `#16a34a` · amber `#d97706` · red `#dc2626` · blue `#2563eb` (+ `-bg` tints).
- **Stage ramp:** `--st-1 #c4b5fd` → `--st-5 #6d28d9`.
- **Dark theme:** see `[data-theme="dark"]` in `tokens/colors.css`.
- **Type:** sizes `--text-2xs 10` → `--text-2xl 21`; weights 400–800; mono tracking `.05em`.
- **Spacing:** 4px base, `--space-1 4` → `--space-7 28`.
- **Radii:** `sm 6` · base `10` · `lg 12` · `xl 14` · pill `999`.
- **Elevation:** `--shadow-card 0 4px 18px rgba(0,0,0,.04)`; `--shadow-hover` violet-tinted; focus `--ring 0 0 0 3px var(--crux-bg)`.
- **Motion:** `--speed .15s`; restrained, `prefers-reduced-motion`-safe.

## Core rules (don't lose these)
- **Spend violet on the one thing that matters** — leading plan, primary action, pipeline position. Everything else stays neutral gray.
- **Mono/sans split is the identity** — prose in sans, every machine-truthful value (labels, keys, priors, metrics, IDs, timestamps) in mono.
- **The verdict gate is product law** — never render an action plan for a case without a logged verdict.
- Sentence case; no emoji; honest probe copy ("see a doctor", not an invented app).

## Assets
- **Icons:** Tabler Icons (external — webfont/package). No icon binaries shipped in the repo.
- **Logo:** none in the repo — a typographic `crux•` wordmark is used (see `Shell.jsx` → `Wordmark`).
- **Imagery:** none — crux is an instrument; the "imagery" is the data (bars, pips, pills).

## Files in this bundle
- `styles.css`, `tokens/`, `base.css`, `primitives.css` — the CSS foundation.
- `components/core/`, `components/case/` — React components (`.jsx` + `.d.ts` + `.prompt.md`).
- `reference_screens/` — interactive prototype (`index.html`, `Shell.jsx`, `screens.jsx`, `data.js`) for look & behavior.
