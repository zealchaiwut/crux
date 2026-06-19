# crux — DESIGN.md

> The design system. Read this (and `tokens.css`) before designing any screen, so every screen is built against one system instead of inventing its own. Pair with PRODUCT.md for *what* each screen does.

---

## 1. Thesis & personality

crux is a **research-and-diagnosis** tool: it races competing causes for a problem and seals the answer until a cheap test proves it. The design should feel **calm, scholarly, and instrument-like** — closer to a lab notebook than a dashboard.

It is a **sibling of commander** and must read as the same product family. So the base (surfaces, grays, semantic colors, SF Mono) is shared and unchanged. crux adds exactly **two** things of its own:

1. **Violet** as the signature accent (commander is blue-terminal; crux is violet-research).
2. The **stage scale** (`--st-1…--st-5`) for the 5-stage pipeline.

> Deliberate non-choice: we did **not** add a display serif or a warm cream background (image 3's parchment). Both would fragment from commander and are common AI-design defaults. Personality here comes from weight, scale, violet, and structure — not a novel typeface.

---

## 2. Color

Defined in `tokens.css`. Roles:

- **Base:** `--bg / --surface / --surface-2 / --border / --text / --text-muted / --text-sub`. Cool gray, identical to commander.
- **Semantic (status only):** `green` = confirmed · `red` = killed · `amber` = inconclusive/warning · `blue` = in-progress/running. Use **only** for state, never decoration.
- **crux signature:** `--crux #7c3aed` (primary actions, leading plan, active stage), `--crux-bg` (tints/chips), `--crux-strong` (hover), `--crux-tint` (card wash).
- **Stage scale:** `--st-1…--st-5`, one violet ramp, used for the stage spine/pips only.

Rule: **spend violet on the signature, not everywhere.** A screen should be mostly neutral gray with violet marking the one thing that matters (the leading cause, the primary action, where you are in the pipeline).

---

## 3. Typography

- **Body / UI:** `--font-sans` (system stack).
- **Data register:** `--font-mono` (SF Mono) — used for *everything machine-truthful*: stage labels, plan keys (A/B/C), priors, target metrics, citations, IDs, counts, timestamps, the footer. This mono/sans split is a core part of the identity: prose is sans, data is mono.
- **Scale:** `--text-2xs 10` … `--text-2xl 21` (see tokens). Titles use `--fw-black (800)` with tight tracking; body `400–600`; mono labels `700` + `.05em`.
- Sentence case everywhere. No all-caps except short mono eyebrow labels.

---

## 4. Spacing, radii, elevation

- **Spacing:** 4px base (`--space-1…--space-7`). Card padding ≈ `--space-3/--space-4`. Section gaps ≈ `--space-5`.
- **Radii:** chips/buttons `--radius-sm 6`, cards `--radius 10`, panels `--radius-lg 12 / --radius-xl 14`, pills `--radius-pill`.
- **Elevation:** containers `--shadow-card`; hover lift is **violet-tinted** `--shadow-hover` (a small but consistent signature). Focus/active = `--ring`.

---

## 5. Layout

Two-pane shell, matching commander:

```
┌────────┬──────────────────────────────┬───────────┐
│ sidebar│  main (feed / detail)        │  right    │
│ 208px  │  flex                        │  rail 288 │
│ nav +  │                              │  prompt + │
│ project│                              │  probes + │
│ switch │                              │  verdicts │
└────────┴──────────────────────────────┴───────────┘
```

- **Sidebar:** brand, primary nav (Cases / Probes / Verdicts) with mono counts, project switcher (commander · perf-coach · crux), mono footer.
- **Right rail** (from the research-app reference): a violet **prompt card** ("New case"), **Probes running**, **Recent verdicts**. The rail is the ambient state of your investigations.
- Collapse the rail under the feed below ~960px; sidebar becomes a top bar under ~720px.

---

## 6. Core components

Spec'd once here; reuse, don't reinvent.

- **Case card** — a row split into a left **stage spine** + body.
  - *Stage spine* (118px): mono stage name + a 5-segment **pip** row (`done` / `now`) encoding pipeline position; mono meta at the bottom. On a closed case the spine tints with the verdict color (green/red/amber).
  - *Body*: case title (sharpened problem, sans 600) + verdict **pill** top-right + the **bake-off race strip**.
- **Bake-off race strip** *(signature — see §7)*.
- **Verdict pill** — `.pill` + state class (`confirmed/killed/inconclusive/awaiting/progress`).
- **Plan card** (detail view) — `plan-key` (A/B/C mono badge) + name + prior chip + mechanism + **source chips**. Leading plan gets `.lead` (violet border + `--crux-tint` wash).
- **Source chip** — `.src` + `book/article/youtube`; the colored icon marks the source kind. One chip per real citation.
- **Probe card** — a `type` chip (`measurement/lab-test/behaviour-experiment/prototype`), a big mono **target metric**, and a foot line (cost/time). Prototype-type probes show **Send to commander**; non-app probes say so plainly (e.g. "see a doctor").
- **Stage bar** (detail header) — horizontal version of the spine: 5 steps with connectors, `done`/`now` states.
- **Locked action plan** *(signature — see §7)*.
- **Right-rail prompt / probe row / verdict row** — as in the mock.

---

## 7. Signature elements (the two things crux is remembered by)

**A. The bake-off race strip.** Plan A/B/C as competing horizontal bars. Bar width = current standing after weighing; the leader fills **violet** (`.lead`), others stay `--st-2`. A won plan gets a "✓ WON" tag; ruled-out plans drop to ~50% opacity. This is the one place a glance tells you the entire state of a case. Always present on a case card and at the top of the detail bake-off.

**B. The sealed action plan.** The action plan stays behind a **hatched, lock-iconed panel** until a Verdict is logged. Copy: "Locked until you log a verdict." This is the 50/50 split made literal — *crux researches; you test.* Never show an action plan on an unverified case.

Spend boldness only on these two. Everything else stays quiet.

---

## 8. Motion

Restrained, and always `prefers-reduced-motion`-safe. Allowed: the live "running" spinner (`ti-loader-2`), a soft pulse on the active stage pip, the violet hover-lift. No page-load theatrics, no decorative motion.

---

## 9. Voice & copy

- Active voice, sentence case, plain verbs. Buttons say what happens ("New case", "Send to commander", "Log verdict").
- Empty states are invitations, not mood: "Got a problem worth solving? Start a case."
- Errors explain and direct; they don't apologize.
- Name things by what the user controls (Cases, Probes, Verdicts) — never by implementation.
- An action keeps its name through the flow: "Log verdict" → toast "Verdict logged."

---

## 10. Quality floor

Responsive to mobile; visible keyboard focus (`--ring`); reduced motion respected; semantic color never the *only* signal (pair with text/icon for colorblind users). Light and dark both first-class — test every screen in both.
