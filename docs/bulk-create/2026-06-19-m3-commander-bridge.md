# M3 — Commander bridge

**Date:** 2026-06-19
**Sprint label:** sprint-4
**Default labels:** sprint-4, milestone:m3
**Status:** drafted

> Turn a prototype-shaped Probe into a copyable commander ticket spec — markdown
> only, copy by hand (no auto-creation of GitHub/commander tickets in v1, §8).
> Depends on M1 (ProbeCard, Probe.commander_spec). Source of truth: `PRODUCT.md`
> §3 (50/50 split), §5.5, §9.

## Prompts

```
Commander spec generator. For a Probe of type="prototype", call the Claude API to generate a commander ticket spec as markdown: a clear title, the single target metric, acceptance criteria, and just enough context for commander to build the probe-prototype. Persist to Probe.commander_spec. Keep it spec-only — crux does not build the prototype (PRODUCT.md §3). Out of scope: any UI; auto-creating tickets (explicit non-goal §8).

---

"Send to commander" on ProbeCard. Wire the "Send to commander" affordance on ProbeCard (only shown for type="prototype", stubbed in M1) to surface the generated commander_spec markdown with a copy-to-clipboard action — I paste it into commander by hand. Show a regenerate option and a sensible state when no spec exists yet. Out of scope: GitHub/commander API integration (revisit later, §8).
```

## Posted issues

| # | Title | Size |
|---|-------|------|
