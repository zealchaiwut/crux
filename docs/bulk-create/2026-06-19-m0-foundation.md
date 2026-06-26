# M0 — Foundation

**Date:** 2026-06-19
**Sprint label:** sprint-1
**Default labels:** sprint-1, milestone:m0
**Status:** drafted

> Foundation milestone: repo scaffold, deploy, schema, single-user auth, and the
> app shell with design tokens. Ships the empty-but-deployable skeleton the Case
> spine (M1) builds on. Source of truth: `PRODUCT.md` §9 and the design bundle in
> `design_handoff_crux/`.

## Prompts

```
FastAPI backend scaffold + Render deploy. Stand up the crux backend as a FastAPI (Python) app matching the commander stack. Include: project layout (app package, config via env vars, health-check route GET /healthz returning 200), local dev runner (uvicorn), dependency pinning, and a Render web-service config (render.yaml or equivalent) so the service deploys from the develop branch. No business logic yet — this is the deployable skeleton. Out of scope: auth, DB models, any UI.

---

Neon Postgres schema + migrations. Create the database layer on Neon Postgres with a migration tool (Alembic or equivalent). Model the five core entities from PRODUCT.md §9 exactly: Case(id, raw_problem, sharpened, not_investigating, stage, created_at); Plan(id, case_id, label[A/B/C], mechanism, prior, current_rank); Source(id, plan_id, kind[book/article/youtube], title, url, claim, citation); Probe(id, case_id, type[measurement/lab-test/behaviour-experiment/prototype], target_metric, status[designed/running/confirmed/killed], due_date, commander_spec); Verdict(id, probe_id, outcome[confirmed/killed/inconclusive], notes, decided_at). Add foreign keys, enums where listed, the initial migration, and a documented connection-string env var. Out of scope: API routes over these tables.

---

Single-user auth. Implement single-user login per PRODUCT.md §9: one secret/password from an env var, no OAuth, no multi-tenant. On success set a signed session cookie; protect all app routes behind it; provide a login page and logout. Reject a weak/empty default secret at startup (the public Render URL must stay genuinely locked — see Risks §11). Out of scope: user accounts, registration, password reset.

---

App shell + design tokens + theme toggle. Build the application shell from the design bundle: link styles.css once at the app root loading tokens in order (fonts → colors → typography → spacing → base → primitives); recreate the sidebar nav, the right rail container, and the typographic `crux•` wordmark (design_handoff_crux/reference_screens/Shell.jsx). Light theme is default; dark activates via data-theme="dark" on <html> with a working toggle — both first-class. Wire Tabler Icons (webfont or @tabler/icons-react; names without the ti- prefix). All styling reads CSS custom properties — never hard-code token values. Out of scope: any screen content (Cases list etc. come in M1) — placeholder routes are fine.
```

## Posted issues

| # | Title | Size |
|---|-------|------|
