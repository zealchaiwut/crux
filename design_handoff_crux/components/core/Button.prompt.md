Primary and neutral button; use `variant="crux"` for the one violet primary action per screen, default (neutral) for everything else.

```jsx
<Button variant="crux" icon="plus">New case</Button>
<Button>Cancel</Button>
<Button size="sm" iconRight="arrow-right">Send to commander</Button>
<Button disabled>Log verdict</Button>
```

- `variant`: `default` (neutral surface) · `crux` (violet fill)
- `size`: `md` · `sm`
- `icon` / `iconRight`: Tabler icon name without the `ti-` prefix
- Sentence case, plain verbs ("New case", "Log verdict"). One crux button per view.
