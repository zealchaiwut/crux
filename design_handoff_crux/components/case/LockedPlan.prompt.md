Signature element B — the sealed action plan. Hidden behind a hatched, lock-iconed panel until a Verdict is logged.

```jsx
{/* before a verdict */}
<LockedPlan />

{/* after a verdict */}
<LockedPlan unlocked>
  <PlanCard planKey="A" name="Add 400 kcal on hard days" mechanism="…" />
</LockedPlan>
```

- Default = locked hatched panel, copy "Locked until you log a verdict."
- `unlocked` reveals children inside a green-confirmed frame.
- Never render an action plan for an unverified case — this gate is the product's core philosophy.
