from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
VER3_SRC = ROOT / "ver3" / "src"
for candidate in (ROOT, VER3_SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from covered_call_mini_ver3.diagnostics.phase_sensitivity.config import PhaseRunConfig  # noqa: E402
from covered_call_mini_ver3.diagnostics.phase_sensitivity.diagnostics import (  # noqa: E402
    run_phase_sensitivity_diagnostics,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run independent phase-sensitivity diagnostics for ver3 selected sleeves.")
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--ver3-root", type=Path, default=ROOT / "ver3")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "outputs" / "ver3_0_independent_phase_sensitivity_diagnostics",
    )
    parser.add_argument("--max-phase-shift", type=int, default=20)
    parser.add_argument("--phase-step", type=int, default=1)
    parser.add_argument("--skip-cycle-attribution", action="store_true")
    parser.add_argument("--skip-ensemble", action="store_true")
    parser.add_argument("--skip-plots", action="store_true")
    parser.add_argument("--write-report", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_config = PhaseRunConfig(
        max_phase_shift=args.max_phase_shift,
        phase_step=args.phase_step,
        skip_cycle_attribution=args.skip_cycle_attribution,
        skip_ensemble=args.skip_ensemble,
        skip_plots=args.skip_plots,
        write_report=args.write_report,
        strict=args.strict,
    )
    summary = run_phase_sensitivity_diagnostics(
        project_root=args.project_root.resolve(),
        ver3_root=args.ver3_root.resolve(),
        output_dir=args.output_dir.resolve(),
        run_config=run_config,
    )
    print("Phase sensitivity diagnostics complete.")
    for key in [
        "project_root",
        "ver3_root",
        "output_root",
        "ver3_output_index",
        "phase_shift_count",
        "target_sleeve_count",
        "target_portfolio_count",
        "phase_run_success_rate",
        "highest_phase_fragility_sleeve",
        "most_phase_robust_candidate",
        "b_default_d20_phase_robustness_label",
        "ensemble_improves_phase_robustness",
        "appendix_recommendation",
        "report_path",
        "validation_passed",
        "validation_total",
    ]:
        print(f"{key}: {summary[key]}")


if __name__ == "__main__":
    main()
