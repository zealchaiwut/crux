The signature crux element — competing Plans race as horizontal bars; one glance shows the whole state of a case.

```jsx
<BakeOffStrip plans={[
  { key: 'A', name: 'Chronic underfueling', standing: 0.62, state: 'leading' },
  { key: 'B', name: 'Overtraining / no deload', standing: 0.30 },
  { key: 'C', name: 'Low iron / ferritin', standing: 0.12, state: 'ruled-out' },
]} />
```

- Leader fills violet; others use `--st-2`.
- `state: 'ruled-out'` → 50% opacity + strikethrough.
- `state: 'won'` → green ✓ WON tag.
- `standing` (0..1) sets each bar's width. Always show this on a case card and at the top of the detail bake-off.
