# M8 — Embedding-based related cases

**Date:** 2026-06-20
**Sprint label:** sprint-8
**Default labels:** sprint-8, milestone:m8
**Status:** drafted

> The TF cosine similarity in `services/related_cases.py` misses semantically
> similar cases phrased differently — "my running pace has dropped" vs "slower
> splits in training" won't match. M8 swaps `_compute_similarity` for Claude
> embeddings so the Prior Learnings recall works on meaning, not token overlap.
> Depends on M4 (related-case service, Prior Learnings UI). Source of truth:
> `PRODUCT.md` §5.7 (Review), architecture.md (Related Cases section).

## Prompts

```
Embedding-based similarity for related cases. Replace the TF cosine implementation in services/related_cases.py with Claude embedding vectors (claude-3 text-embedding or equivalent Anthropic embedding endpoint). Store embeddings in a new `case_embedding` table (case_id FK, embedding blob/vector, model_version, created_at) so they are computed once on case creation/update and reused on every query — avoid re-embedding on every related-case lookup. The public interface (_find_related_cases, _compute_similarity) stays identical so routers/related_cases.py needs no changes. Seed embeddings for all existing cases in a migration or a one-off backfill script. Out of scope: vector DB (store as JSON/blob in Postgres; cosine is computed in-process over the small single-user dataset).

---

Embedding freshness and invalidation. Keep case embeddings in sync: recompute the embedding when a Case's sharpened statement or plan mechanisms change (POST /api/cases/{id}/bake-off, PATCH /api/cases/{id} from M7). Expose a GET /api/admin/reindex endpoint (auth-protected, no new login required) that recomputes all embeddings — useful after a model version change or a bulk import. Log the model_version used so stale embeddings from an old model can be detected and refreshed. Out of scope: automatic model-version migration — manual reindex is sufficient.
```

## Posted issues

| # | Title | Size |
|---|-------|------|
