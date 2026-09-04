# Effective-Delta Equivalence Diagnostic

This is an independent sidecar diagnostic. It compares pre-registered covered-call implementations that target the same entry effective delta:

- `D28_Q100`
- `D35_Q80`
- `D40_Q70`
- `D50_Q56`

Default target effective delta is `0.72`, so each implementation has expected overlay delta `0.28`.

The diagnostic writes real outputs to:

```text
outputs/ver3_0_independent_effective_delta_equivalence_diagnostic/
```

`ver3/outputs/` only receives a lightweight output index.
