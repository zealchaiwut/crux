The primary row in the Cases list — a stage spine (stage name + 5-pip position + ID) next to a body (sharpened title, verdict pill, bake-off strip).

```jsx
<CaseCard
  id="CASE-0148"
  title="Why is my 10K pace 20s/km slower than last spring?"
  stage={3}
  verdict="progress"
  plans={[
    { key: 'A', name: 'Chronic underfueling', standing: 0.62, state: 'leading' },
    { key: 'B', name: 'No deload in 14 weeks', standing: 0.30 },
    { key: 'C', name: 'Low ferritin', standing: 0.12, state: 'ruled-out' },
  ]}
  onClick={() => open(148)}
/>
```

- `stage` 0–4 drives the spine pips; a closed `verdict` tints the spine green/red/amber.
- Always carries a BakeOffStrip — that's the at-a-glance state.
