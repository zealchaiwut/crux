The verdict / status pill — the single way crux renders state. Color is always paired with a word (colorblind-safe).

```jsx
<Pill state="confirmed" />
<Pill state="killed" />
<Pill state="inconclusive" />
<Pill state="awaiting">awaiting probe</Pill>
<Pill state="progress" />
```

- `state`: `confirmed` (green) · `killed` (red) · `inconclusive` (amber) · `awaiting` (neutral) · `progress` (blue)
- Pass children to override the label; otherwise a sensible default word is shown.
