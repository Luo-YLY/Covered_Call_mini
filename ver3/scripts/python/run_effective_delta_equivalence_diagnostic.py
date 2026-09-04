from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
VER3_SRC = ROOT / "ver3" / "src"
for candidate in (ROOT, VER3_SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from covered_call_mini_ver3.diagnostics.effective_delta_equivalence.config import (  # noqa: E402
    load_effective_delta_config,
)
from covered_call_mini_ver3.diagnostics.effective_delta_equivalence.pipeline import (  # noqa: E402
    run_effective_delta_equivalence_diagnostic,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run independent effective-delta equivalent covered-call implementation diagnostic."
    )
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--ver3-root", type=Path, default=ROOT / "ver3")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "outputs" / "ver3_0_independent_effective_delta_equivalence_diagnostic",
    )
    parser.add_argument("--target-effective-delta", type=float, default=None)
    parser.add_argument("--include-growth-diagnostic", action="store_true")
    parser.add_argument("--skip-phase-lite", action="store_true")
    parser.add_argument("--skip-plots", action="store_true")
    parser.add_argument("--write-report", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--rf", type=float, default=0.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_effective_delta_config(
        project_root=args.project_root,
        ver3_root=args.ver3_root,
        output_dir=args.output_dir,
        target_effective_delta=args.target_effective_delta,
        include_growth_diagnostic=args.include_growth_diagnostic,
        skip_phase_lite=args.skip_phase_lite,
        skip_plots=args.skip_plots,
        write_report=args.write_report,
        strict=args.strict,
        rf=args.rf,
    )
    print("running effective-delta implementation-equivalence diagnostic...")
    result = run_effective_delta_equivalence_diagnostic(config)
    validation_passed = int(result.validation["passed"].sum()) if not result.validation.empty else 0
    validation_total = len(result.validation)
    success_rate = float(result.summary["implementation_name"].notna().mean()) if not result.summary.empty else 0.0
    d40_state = "; ".join(result.recommendation["d40_q70_support_state"].astype(str).unique()) if not result.recommendation.empty else "unknown"
    appendix = bool(result.recommendation["final_appendix_recommended"].any()) if not result.recommendation.empty else False
    print(f"project root: {config.paths.project_root}")
    print(f"ver3 root: {config.paths.ver3_root}")
    print(f"real output dir: {result.output_root}")
    print(f"ver3 output index: {result.index_path}")
    print(f"target effective delta: {config.target_effective_delta:.2f}")
    print(f"target ETF count: {len(config.active_etfs)}")
    print(f"implementation count: {len(config.implementations)}")
    print(f"run success rate: {success_rate:.1%}")
    for etf in config.active_etfs:
        sample = result.summary[result.summary["etf_code"].eq(etf)].copy()
        if sample.empty:
            continue
        stable = sample.sort_values(["sharpe_daily_mean", "max_drawdown"], ascending=[False, True]).iloc[0]
        print(f"{etf} most stable implementation proxy: {stable['implementation_name']}")
    print(f"D40_Q70 support state: {d40_state}")
    print(f"D28_Q100 worth appendix: {appendix}")
    print(f"recommend final appendix: {appendix}")
    print(f"validation: {validation_passed}/{validation_total} passed")
    if config.strict and validation_passed != validation_total:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
