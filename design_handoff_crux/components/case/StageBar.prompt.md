The 5-stage pipeline header. Done steps fill the violet ramp, the current step is full violet, pending steps stay neutral.

```jsx
<StageBar current={2} />            {/* now at "Gather" */}
<StageBar current={5} />            {/* closed case — all done */}
```

- `current`: 0=Sharpen, 1=Bake-off, 2=Gather, 3=Weigh, 4=Probe, 5=closed
- Color always pairs with the stage label, never color alone.
