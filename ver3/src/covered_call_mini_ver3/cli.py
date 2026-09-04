from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
from typing import Sequence


COMMANDS: dict[str, tuple[str, str]] = {
    "step-a-main": (
        "ver3/scripts/python/run_ver3_0_stepA_single_etf_sleeves.py",
        "Run Step A main single-ETF sleeves.",
    ),
    "step-a-510050": (
        "ver3/scripts/python/run_ver3_0_stepA_extension_510050_sleeve_clarification.py",
        "Run Step A 510050 extension.",
    ),
    "step-a-588000": (
        "ver3/scripts/python/run_ver3_0_stepA_extension_588000_sleeve_clarification.py",
        "Run Step A 588000 short-sample extension.",
    ),
    "step-a-surface": (
        "ver3/scripts/python/run_ver3_0_stepA_moneyness_refined_daily_mtm_surface.py",
        "Run current Step A refined daily-MTM moneyness x coverage surface.",
    ),
    "step-b": (
        "ver3/scripts/python/ver3_0_stepB_fixed_weight_universe_comparison.py",
        "Run Step B fixed-weight universe comparison.",
    ),
    "step-b-plus": (
        "ver3/scripts/python/run_stepB_plus_mdd_constrained_sharpe_frontier.py",
        "Run Step B+ MDD-constrained Sharpe frontier.",
    ),
    "step-c": (
        "ver3/scripts/python/run_stepC_robustness_stability_diagnostics.py",
        "Run Step C robustness and stability diagnostics.",
    ),
    "step-d": (
        "ver3/scripts/python/run_stepD_volatility_controlled_dynamic_weighting.py",
        "Run Step D dynamic sleeve weighting research layer.",
    ),
    "phase": (
        "ver3/scripts/python/run_phase_sensitivity_diagnostics.py",
        "Run independent phase-sensitivity diagnostics.",
    ),
    "delta-phase": (
        "ver3/scripts/python/run_delta_vs_moneyness_phase_check.py",
        "Run delta-vs-moneyness phase-sensitivity check.",
    ),
    "effective-delta": (
        "ver3/scripts/python/run_ver3_1_effective_zone_target_delta.py",
        "Run ver3.1 effective-zone to target-delta sidecar experiment.",
    ),
    "effective-delta-equivalence": (
        "ver3/scripts/python/run_effective_delta_equivalence_diagnostic.py",
        "Run independent same-effective-delta implementation-equivalence diagnostic.",
    ),
    "dashboard-data": (
        "ver3/scripts/python/build_ver3_dashboard_data.py",
        "Build the dashboard data payload.",
    ),
    "summary-report": (
        "ver3/scripts/python/build_ver3_current_experiment_summary.py",
        "Build the current experiment summary report.",
    ),
}

SMOKE_TESTS: dict[str, str] = {
    "step-b-plus": "ver3/tests/stepB_plus/smoke_test_stepB_plus.py",
    "step-c": "ver3/tests/stepC_robustness/smoke_test_stepC_robustness.py",
    "step-d": "ver3/tests/stepD_dynamic_weighting/smoke_test_stepD_dynamic_weighting.py",
    "effective-delta-equivalence": "ver3/tests/effective_delta_equivalence/smoke_test_effective_delta_equivalence.py",
}


def find_repo_root(start: Path | None = None) -> Path:
    """Locate the checkout root that owns ver3 and the root outputs directory."""

    env_root = os.environ.get("CCM_REPO_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()

    candidates: list[Path] = []
    if start is not None:
        candidates.extend([start.resolve(), *start.resolve().parents])
    cwd = Path.cwd().resolve()
    candidates.extend([cwd, *cwd.parents])
    here = Path(__file__).resolve()
    candidates.extend(here.parents)

    for candidate in candidates:
        if (candidate / "ver3").is_dir() and (candidate / "outputs").is_dir():
            return candidate
    raise SystemExit(
        "Cannot locate covered_call_mini repo root. Run from the checkout root "
        "or set CCM_REPO_ROOT."
    )


def build_env(repo_root: Path) -> dict[str, str]:
    """Build a subprocess environment that exposes repo-root and ver3/src imports."""

    env = os.environ.copy()
    paths = [str(repo_root), str(repo_root / "ver3" / "src")]
    current = env.get("PYTHONPATH")
    if current:
        paths.append(current)
    env["PYTHONPATH"] = os.pathsep.join(paths)
    return env


def command_path(repo_root: Path, command_name: str) -> Path:
    """Resolve a named ver3 workflow command to its script path."""

    if command_name not in COMMANDS:
        known = ", ".join(sorted(COMMANDS))
        raise SystemExit(f"Unknown command '{command_name}'. Known commands: {known}")
    return repo_root / COMMANDS[command_name][0]


def run_script(repo_root: Path, script: Path, args: Sequence[str], *, dry_run: bool = False) -> int:
    """Run a workflow script from the checkout root with the ver3 import path set."""

    if not script.exists():
        raise SystemExit(f"Script does not exist: {script}")
    command = [sys.executable, str(script), *args]
    if dry_run:
        print("cwd:", repo_root)
        print("cmd:", " ".join(command))
        return 0
    completed = subprocess.run(command, cwd=repo_root, env=build_env(repo_root), check=False)
    return int(completed.returncode)


def print_command_list() -> None:
    """Print the registered workflow commands."""

    width = max(len(name) for name in COMMANDS)
    for name, (_, description) in sorted(COMMANDS.items()):
        print(f"{name:<{width}}  {description}")


def run_doctor(repo_root: Path) -> int:
    """Check packaging-level assumptions without running any backtest."""

    checks = {
        "repo_root": repo_root.exists(),
        "ver3_src": (repo_root / "ver3" / "src" / "covered_call_mini_ver3").is_dir(),
        "root_outputs": (repo_root / "outputs").is_dir(),
        "dashboard": (repo_root / "ver3" / "dashboard" / "index.html").exists(),
        "pyproject": (repo_root / "ver3" / "pyproject.toml").exists(),
    }
    for name, passed in checks.items():
        print(f"{name}: {'ok' if passed else 'missing'}")
    return 0 if all(checks.values()) else 1


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line interface parser."""

    parser = argparse.ArgumentParser(
        prog="ccm-ver3",
        description="Unified command wrapper for the covered_call_mini ver3 workflow.",
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    subparsers.add_parser("list", help="List available workflow commands.")
    subparsers.add_parser("doctor", help="Check packaging-level assumptions.")

    run_parser = subparsers.add_parser("run", help="Run a registered workflow command.")
    run_parser.add_argument("name", choices=sorted(COMMANDS), help="Workflow command name.")
    run_parser.add_argument("--dry-run", action="store_true", help="Print the resolved command without running it.")
    run_parser.add_argument("args", nargs=argparse.REMAINDER, help="Extra arguments passed to the workflow script.")

    smoke_parser = subparsers.add_parser("smoke", help="Run a lightweight smoke test.")
    smoke_parser.add_argument("name", choices=sorted(SMOKE_TESTS), help="Smoke test name.")
    smoke_parser.add_argument("--dry-run", action="store_true", help="Print the resolved command without running it.")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint used by the ccm-ver3 console script."""

    parser = build_parser()
    args = parser.parse_args(argv)
    repo_root = find_repo_root()

    if args.subcommand == "list":
        print_command_list()
        return 0
    if args.subcommand == "doctor":
        return run_doctor(repo_root)
    if args.subcommand == "run":
        script = command_path(repo_root, args.name)
        extra_args = list(args.args)
        dry_run = bool(args.dry_run)
        if "--dry-run" in extra_args:
            dry_run = True
            extra_args = [item for item in extra_args if item != "--dry-run"]
        if extra_args and extra_args[0] == "--":
            extra_args = extra_args[1:]
        return run_script(repo_root, script, extra_args, dry_run=dry_run)
    if args.subcommand == "smoke":
        return run_script(repo_root, repo_root / SMOKE_TESTS[args.name], (), dry_run=bool(args.dry_run))

    parser.error(f"Unsupported subcommand: {args.subcommand}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
