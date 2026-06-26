A competing root-cause bet (detail view): mono A/B/C key, name, prior chip, one-line mechanism, and source chips. Mark the leader with `lead`.

```jsx
<PlanCard
  planKey="A"
  name="Chronic underfueling"
  prior={0.62}
  mechanism="Sustained energy deficit suppresses thyroid + training adaptation."
  sources={[
    { kind: 'book', label: 'Noakes — Lore of Running' },
    { kind: 'article', label: 'RED-S consensus 2023', href: 'https://...' },
  ]}
  lead
/>
```

- `lead`: violet border + `--crux-tint` wash — at most one per case.
- `prior`: 0..1, rendered as a mono chip. One source chip per real citation.
