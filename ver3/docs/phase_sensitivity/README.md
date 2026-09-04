# Independent Phase Sensitivity Diagnostics

This folder documents the ver3 sidecar diagnostic for covered-call phase risk.

The runnable entrypoint is:

```powershell
python ver3/scripts/python/run_phase_sensitivity_diagnostics.py
```

The experiment is intentionally independent from Step A-D. Large outputs are written under root `outputs/`; `ver3/outputs/` only stores a lightweight index.
