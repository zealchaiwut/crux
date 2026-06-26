# crux — PRODUCT.md

> Source of truth. Everything downstream — DESIGN.md, Claude Design mocks, commander tickets, the advisor — reads this first. Keep it current.

---

## 1. Problem

Researching a problem normally ends in a pile of generic advice, and acting on it means betting on one guess. Two failure modes:

- **Vague in, vague out.** "Why is my running dropping" returns the same listicle everyone gets, not *your* answer.
- **Guess-then-fix.** People jump from a hunch straight to an expensive fix (rewrite the training plan, build the app, fund the bot) without cheaply confirming the cause first.

crux fixes both: it sharpens the problem, forces it into **competing hypotheses**, grounds each in real sources with citations, and designs the **single cheapest test** that decides between them — then refuses to show an action plan until a test result is logged.

## 2. Who it's for

- **Primary and only user: me.** Single-user product. No teams, no sharing, no multi-tenant.
- **Deployed on Render** so it's reachable from anywhere (laptop, iPad while travelling), behind a single-user login.
- Used alongside **commander** (which builds the probe-prototypes) and **perf-coach** (where winning prototypes may graduate).

## 3. What it is

A small companion app to commander. commander builds and ships; crux decides what's worth building by turning a messy problem into a falsifiable bake-off plus the cheapest experiment that settles it. crux does only the desk-research and design half — running probes and building prototypes stays with the human.

**Core philosophy — the 50/50 split:**

| crux does (AI / desk work) | I do (the half that matters) |
|---|---|
| Sharpen the problem into one falsifiable statement | Paste my own data and context |
| Generate competing Plan A/B/C with priors | **Run the probe** (blood test, deload, blurt log) |
| Research + cite from web, articles, YouTube | **Build the prototype** (via commander) and UAT it |
| Re-weight the plans against my pasted data | **Call the verdict** — confirmed / killed / inconclusive |
| Design the cheapest probe and classify its type | Decide graduation (does a winner become a real feature) |
| Generate a commander ticket spec | Copy that spec into commander |

**The hard gate:** crux will not display an action plan for a Case until a probe **Verdict** is logged. This is what structurally keeps the testing half with the human.

## 4. Core concepts (glossary)

- **Case** — one problem, moving through five stages to a Verdict. Never "done" until a Verdict exists.
- **Plan (A/B/C)** — a competing root-cause bet within a Case, each with a one-line mechanism and a prior. Plans race each other.
- **Source** — a cited book / article / YouTube reference attached to a Plan's evidence.
- **Probe** — the cheapest decisive test for the leading Plan(s). Has a **type**: `measurement` | `lab-test` | `behaviour-experiment` | `prototype`, a single **target metric**, a status (`designed` / `running` / `confirmed` / `killed`), and a due date.
- **Verdict** — the logged outcome of a Probe: `confirmed` / `killed` / `inconclusive`. Unlocks the action plan. Kept forever, including dead ends.

## 5. Core flows

1. **New Case.** Paste a messy problem → crux returns a sharpened, falsifiable statement + a "not investigating" list. *(Stage 0)*
2. **Bake-off.** crux generates Plan A/B/C — rival bets with mechanism + prior each. *(Stage 1)*
3. **Gather.** The custom research loop fetches and synthesises evidence per Plan from web/articles/YouTube, every claim carrying a citation. *(Stage 2)*
4. **Weigh.** I paste my own numbers/context; crux re-ranks the Plans by fit to *me* and flags any I can already rule in/out. *(Stage 3)*
5. **Probe.** crux designs the cheapest decisive test, classifies its type, and names the one metric. If `prototype`, it generates a commander ticket spec. *(Stage 4)*
6. **Run + Verdict.** I run the probe (or commander builds the prototype and I UAT it), then log the Verdict. The action plan unlocks. *(Stage 5 + gate)*
7. **Review.** Verdict log and Case history surface prior confirmed/killed learnings when I open a related new Case.

## 6. Screens (feeds Claude Design at step 4)

- **Cases list** — open problems, each showing current stage + the loudest Plan so far.
- **Case view** — the five stages, the A/B/C bake-off, sources with links, the probe card, the locked/unlocked action plan.
- **Probe card** — status, target metric, due date, "Send to commander" (spec) button when prototype-shaped.
- **Verdict log** — confirmed causes + killed hypotheses across all Cases; the personal knowledge base.
- **New Case modal** — paste box + the sharpened-statement confirmation step.

## 7. Scope (v1, in)

- Single-user auth, Render-deployed, Neon-backed.
- Full five-stage Case pipeline with the Verdict gate.
- **Custom research loop** (own engine): query planning → web/article/YouTube fetch → extraction → cited synthesis.
- Probe design + type classification + target metric.
- Commander handoff as a **copyable spec** (markdown).
- Verdict log + Case history recall.
- Light/dark theme, responsive web (matches existing dashboard tokens).

## 8. Non-goals (explicit)

- **Not a second brain / notes app** — use Notion. crux stores Cases, not knowledge dumps.
- **Not a chatbot** — it's a structured Case pipeline, not freeform chat.
- **Does not run probes** — no auto blood tests, deloads, or experiments. The human runs them.
- **Does not build prototypes** — commander does that.
- **Not a topic→essay research report tool** — it's problem→probe, not "write me a report on X."
- **No multi-user / teams / sharing** in v1.
- **No auto-creation of commander/GitHub tickets** in v1 — spec-only, copy by hand. (Revisit later.)
- **No native mobile app** — responsive web is enough.

## 9. Architecture / stack

- **Backend:** FastAPI (Python), matching the commander stack.
- **DB:** Neon Postgres.
- **Frontend:** light SPA / server-rendered, reusing the existing dashboard design tokens; light/dark toggle.
- **Hosting:** Render web service.
- **Auth:** single-user — one secret/password, session cookie. Not OAuth, not multi-tenant.
- **LLM:** Claude API for the stage prompts (sharpen, plans, weigh, probe design).
- **Research loop (custom subsystem):** query-planner (LLM) → fetchers (web search, article reader, YouTube transcript) → extractor → citation-aware synthesiser. Built as its own module so it can be swapped or stubbed.

**Data model (sketch):**
```
Case(id, raw_problem, sharpened, not_investigating, stage, created_at)
Plan(id, case_id, label[A/B/C], mechanism, prior, current_rank)
Source(id, plan_id, kind[book/article/youtube], title, url, claim, citation)
Probe(id, case_id, type, target_metric, status, due_date, commander_spec)
Verdict(id, probe_id, outcome[confirmed/killed/inconclusive], notes, decided_at)
```

## 10. Milestones (roadmap)

**Sequencing principle:** ship the usable Case spine *before* the risky research engine. The spine works with manually-pasted sources; the custom loop replaces that paste later.

### Completed

- **M0 — Foundation.** ✓ Repo, Render deploy, Neon schema, single-user auth, app shell + `tokens.css` + theme toggle.
- **M1 — Case spine (structure-first).** ✓ New Case → sharpen → Plan A/B/C → manual source paste → weigh-against-my-data → probe design + type → Verdict gate + log.
- **M2 — Custom research loop.** ✓ Query planning, web/article/YouTube fetch, extraction, cited synthesis; auto-fills Stage 2.
- **M3 — Commander bridge.** ✓ Generate the probe-prototype ticket spec (one metric + AC) as copyable markdown.
- **M4 — Verdict memory.** ✓ TF cosine similarity surfaces prior confirmed/killed learnings when opening a related new Case.

### Upcoming

- **M5 — Probe lifecycle.** Status transitions (`designed → running → verdict`), due date visibility with overdue flagging, and an inconclusive re-probe flow — design a second probe on the same case without resetting the bake-off and gather stages. Closes the biggest daily-use gap after the first verdicts start coming in.
- **M6 — Verdicts screen & knowledge base.** Build out the Verdicts nav screen: all confirmed causes and killed hypotheses across every case, filterable by outcome, searchable by keyword. Turns the case history into a queryable personal knowledge base you check before starting a new case.
- **M7 — Case search & filtering.** Keyword search across sharpened statements and plan mechanisms, filter by stage and verdict outcome, and basic case editing (update the sharpened statement or not-investigating list without losing downstream stages). Needed once the library grows past ~20 cases.
- **M8 — Embedding-based related cases.** Swap `_compute_similarity` in `services/related_cases.py` for a Claude embedding call. TF cosine misses semantically similar cases phrased differently — fine for a small library, noticeably weak past ~50 cases.

## 11. Risks / open questions

- **Custom research loop is the biggest effort + quality risk** (fetch reliability, YouTube transcripts, citation accuracy). Mitigation: it's isolated as M2 behind a working spine, and a borrowed engine (e.g. gpt-researcher) remains a fallback if the custom build stalls.
- **Probe-type classifier** must be honest — e.g. tell me "this is a blood test, see a doctor," not invent an app. Needs eval cases.
- **Single-user auth on a public Render URL** — keep it genuinely locked (no weak default secret).
- **Open:** exact light research budget per Case (how many fetches before synthesis) — tune in M2.
