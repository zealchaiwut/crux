# M4 — Verdict memory

**Date:** 2026-06-19
**Sprint label:** sprint-5
**Default labels:** sprint-5, milestone:m4
**Status:** drafted

> Close the loop: prior confirmed/killed learnings surface when I open a related
> new Case, so the Verdict log becomes a working personal knowledge base instead
> of an archive. Depends on M1 (Verdict log). Source of truth: `PRODUCT.md`
> §5.7 (Review), §10.

## Prompts

```
Related-case matching. When a new Case is created/sharpened, find prior Cases with logged Verdicts that relate to it (by topic/problem similarity over sharpened statements + plan mechanisms; LLM or embedding-based). Return ranked matches with their outcome (confirmed/killed/inconclusive) and the deciding metric. Build as a queryable service over Verdict + Case rows. Out of scope: UI surfacing (next ticket).

---

Surface prior learnings on new Cases. In the New Case flow and the Case header, surface the related prior learnings from the matching service: confirmed causes and killed hypotheses from past Cases, each with its outcome pill and a link back to the source Case — so I don't re-investigate a settled question. Show nothing gracefully when there are no relevant priors. Out of scope: changing the verdict-gate or stage logic.
```

## Posted issues

| # | Title | Size |
|---|-------|------|
