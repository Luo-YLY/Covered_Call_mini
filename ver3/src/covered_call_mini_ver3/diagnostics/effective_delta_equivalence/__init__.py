"""Independent effective-delta implementation-equivalence diagnostic."""

from .config import DiagnosticConfig, ImplementationSpec, load_effective_delta_config
from .pipeline import run_effective_delta_equivalence_diagnostic

__all__ = [
    "DiagnosticConfig",
    "ImplementationSpec",
    "load_effective_delta_config",
    "run_effective_delta_equivalence_diagnostic",
]
