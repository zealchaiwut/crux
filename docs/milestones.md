# Milestones

A running history of what each sprint shipped for crux — derived from
sprint summaries, not a forward roadmap. The documentor appends one entry per
finished sprint inside the auto-managed region below.

<!-- Anything above this line is hand-maintained. -->

<!-- AUTO:milestones START -->
<!-- The documentor manages everything between these markers. Do not edit by hand. -->

## M0 — Foundation · Sprint 1 · 2026-06-19

Repo scaffold, Render deploy config, Neon Postgres schema + Alembic migrations, single-user session-cookie auth, app shell with design tokens and light/dark theme toggle.

Issues: #1 #2 #3 #4

---

## M1 — Case Spine · Sprint 2 · 2026-06-19

Full five-stage Case pipeline with the Verdict gate, usable end-to-end with manually pasted sources. Cases list screen, New Case modal with Sharpen (Stage 0), Case detail scaffold with StageBar, Plan A/B/C bake-off (Stage 1), manual source attachment form, re-rank against user data (Stage 3), probe design + type classification (Stage 4), Verdict gate + log (Stage 5).

Issues: #5 #6 #7 #8 #9 #10 #11 #12

---

## M2 — Custom Research Loop · Sprint 3 · 2026-06-19

Auto-fills Stage 2 (Gather) with cited sources from web, articles, and YouTube. LLM query planner → DuckDuckGo/article/YouTube fetchers → claim extractor → citation-aware synthesiser. Per-plan gather states (idle → running → done/empty/error) with spinner, retry, and manual fallback. Auto-triggers on entering Stage 2.

Issues: #17 #18 #19 #20 #21

---

## M3 + M4 — Commander Bridge + Verdict Memory · Sprint 4 · 2026-06-19

**Commander bridge:** Generate a copyable markdown commander spec for `prototype`-type probes. Cached in the DB; regenerate with `?force=true`. Copy-to-clipboard modal with a one-click send-to-commander flow.

**Verdict memory:** Related-case matching via TF cosine similarity surfaces prior confirmed/killed learnings when opening a related new case, and in the New Case confirm step. Background fetch on case load; no extra interaction required.

Issues: #26 #27 #28 #29

<!-- AUTO:milestones END -->
