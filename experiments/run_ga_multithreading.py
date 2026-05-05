#!/usr/bin/env python3
"""Benchmark the final 3-worker + GA-thread VRP design.

By default this script compiles the C++ solver, smoke-tests all three models,
then benchmarks every input instance for 120 seconds per model. Use
--smoke-only for a quick correctness check without launching the full run.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


MODELS = ["independent", "one_way", "bidirectional"]
CSV_FIELDS = [
    "instance",
    "model",
    "seed",
    "time_limit",
    "runtime",
    "objective",
    "valid",
    "best_source",
    "pool_size",
    "accepted_seeds",
    "rejected_seeds",
    "accepted_children",
    "rejected_children",
    "accepted_migrants",
    "rejected_migrants",
    "pulls_attempted",
    "pulls_accepted",
    "solution",
    "error",
]


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run GA multithreading VRP benchmarks."
    )
    parser.add_argument("--time-limit", type=float, default=120.0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--tau", type=float, default=0.10)
    parser.add_argument("--p-pull", type=float, default=0.10)
    parser.add_argument("--migration-interval", type=float, default=5.0)
    parser.add_argument("--models", nargs="+", choices=MODELS, default=MODELS)
    parser.add_argument(
        "--instances",
        nargs="+",
        default=None,
        help="Instance filenames or paths. Defaults to all input/*.vrp.",
    )
    parser.add_argument("--skip-smoke", action="store_true")
    parser.add_argument("--smoke-only", action="store_true")
    parser.add_argument("--no-compile", action="store_true")
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args()


def instance_sort_key(path: Path) -> tuple[int, str]:
    try:
        return (int(path.stem.split("_")[0]), path.name)
    except ValueError:
        return (10**9, path.name)


def resolve_instances(root: Path, requested: list[str] | None) -> list[Path]:
    input_dir = root / "input"
    if requested is None:
        return sorted(input_dir.glob("*.vrp"), key=instance_sort_key)

    resolved: list[Path] = []
    for item in requested:
        path = Path(item)
        if not path.is_absolute():
            candidate = root / item
            if candidate.exists():
                path = candidate
            else:
                path = input_dir / item
        if not path.exists():
            raise FileNotFoundError(f"instance not found: {item}")
        resolved.append(path)
    return sorted(resolved, key=instance_sort_key)


def compile_cpp(root: Path) -> None:
    subprocess.run(["bash", "compile.sh"], cwd=root / "cpp", check=True)


def parse_solver_json(stdout: str) -> dict[str, Any]:
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    if not lines:
        raise ValueError("solver produced no stdout")
    return json.loads(lines[-1])


def validate_solution(root: Path, instance: Path, solver_json: str) -> bool:
    completed = subprocess.run(
        [str(root / "cpp" / "validate"), str(instance)],
        input=solver_json,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    return completed.returncode == 0


def run_solver(
    root: Path,
    instance: Path,
    model: str,
    *,
    time_limit: float,
    seed: int,
    tau: float,
    p_pull: float,
    migration_interval: float,
) -> dict[str, Any]:
    cmd = [
        str(root / "cpp" / "ga_multithreaded_solver"),
        str(instance),
        "--model",
        model,
        "--time-limit",
        str(time_limit),
        "--seed",
        str(seed),
        "--tau",
        str(tau),
        "--p-pull",
        str(p_pull),
        "--migration-interval",
        str(migration_interval),
    ]

    try:
        completed = subprocess.run(
            cmd,
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=time_limit + 45,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "instance": instance.name,
            "model": model,
            "seed": seed,
            "time_limit": time_limit,
            "runtime": "",
            "objective": "",
            "valid": False,
            "best_source": "",
            "pool_size": "",
            "accepted_seeds": "",
            "rejected_seeds": "",
            "accepted_children": "",
            "rejected_children": "",
            "accepted_migrants": "",
            "rejected_migrants": "",
            "pulls_attempted": "",
            "pulls_accepted": "",
            "solution": "",
            "error": f"timeout after {exc.timeout:.1f}s",
        }

    if completed.returncode != 0:
        return {
            "instance": instance.name,
            "model": model,
            "seed": seed,
            "time_limit": time_limit,
            "runtime": "",
            "objective": "",
            "valid": False,
            "best_source": "",
            "pool_size": "",
            "accepted_seeds": "",
            "rejected_seeds": "",
            "accepted_children": "",
            "rejected_children": "",
            "accepted_migrants": "",
            "rejected_migrants": "",
            "pulls_attempted": "",
            "pulls_accepted": "",
            "solution": "",
            "error": completed.stderr.strip() or "solver failed",
        }

    try:
        parsed = parse_solver_json(completed.stdout)
        solver_line = json.dumps(parsed)
        valid = bool(parsed.get("Valid")) and validate_solution(root, instance, solver_line)
    except Exception as exc:  # noqa: BLE001 - turn parser/validator failures into CSV rows.
        return {
            "instance": instance.name,
            "model": model,
            "seed": seed,
            "time_limit": time_limit,
            "runtime": "",
            "objective": "",
            "valid": False,
            "best_source": "",
            "pool_size": "",
            "accepted_seeds": "",
            "rejected_seeds": "",
            "accepted_children": "",
            "rejected_children": "",
            "accepted_migrants": "",
            "rejected_migrants": "",
            "pulls_attempted": "",
            "pulls_accepted": "",
            "solution": "",
            "error": f"bad solver output: {exc}",
        }

    return {
        "instance": instance.name,
        "model": model,
        "seed": seed,
        "time_limit": time_limit,
        "runtime": parsed.get("Time", ""),
        "objective": parsed.get("Result", ""),
        "valid": valid,
        "best_source": parsed.get("BestSource", ""),
        "pool_size": parsed.get("PoolSize", 0),
        "accepted_seeds": parsed.get("AcceptedSeeds", 0),
        "rejected_seeds": parsed.get("RejectedSeeds", 0),
        "accepted_children": parsed.get("AcceptedChildren", 0),
        "rejected_children": parsed.get("RejectedChildren", 0),
        "accepted_migrants": parsed.get("AcceptedMigrants", 0),
        "rejected_migrants": parsed.get("RejectedMigrants", 0),
        "pulls_attempted": parsed.get("PullsAttempted", 0),
        "pulls_accepted": parsed.get("PullsAccepted", 0),
        "solution": parsed.get("Solution", ""),
        "error": "",
    }


def smoke_test(root: Path, instances: list[Path], seed: int, tau: float) -> None:
    smoke_instance = min(instances, key=instance_sort_key)
    print(f"Smoke testing {smoke_instance.name} across all models...")
    for model in MODELS:
        row = run_solver(
            root,
            smoke_instance,
            model,
            time_limit=2.0,
            seed=seed,
            tau=tau,
            p_pull=1.0 if model == "bidirectional" else 0.10,
            migration_interval=0.5,
        )
        if row["error"]:
            raise RuntimeError(f"smoke {model} failed: {row['error']}")
        if not row["valid"]:
            raise RuntimeError(f"smoke {model} produced an invalid solution")
        if model == "independent" and int(row["pulls_attempted"]) != 0:
            raise RuntimeError("independent smoke recorded GA pulls")
        if model == "one_way" and int(row["pulls_attempted"]) != 0:
            raise RuntimeError("one_way smoke recorded worker pulls")
        if model == "bidirectional" and int(row["pulls_attempted"]) == 0:
            raise RuntimeError("bidirectional smoke recorded no pull attempts")
        print(
            f"  {model}: objective={row['objective']} "
            f"valid={row['valid']} pool={row['pool_size']}"
        )


def output_path(root: Path, requested: Path | None) -> Path:
    if requested is not None:
        return requested if requested.is_absolute() else root / requested
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return root / "experiments" / f"ga_multithreading_results_{stamp}.csv"


def main() -> int:
    args = parse_args()
    root = repo_root()
    instances = resolve_instances(root, args.instances)
    if not instances:
        print("No instances found.", file=sys.stderr)
        return 1

    if not args.no_compile:
        print("Compiling C++ solvers...")
        compile_cpp(root)

    if not args.skip_smoke:
        smoke_test(root, instances, args.seed, args.tau)

    if args.smoke_only:
        print("Smoke-only run complete; full benchmark not started.")
        return 0

    out = output_path(root, args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    print(f"Writing benchmark rows to {out}")

    with out.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for instance in instances:
            for model in args.models:
                print(
                    f"Running {model} on {instance.name} "
                    f"({args.time_limit:.0f}s)...",
                    flush=True,
                )
                row = run_solver(
                    root,
                    instance,
                    model,
                    time_limit=args.time_limit,
                    seed=args.seed,
                    tau=args.tau,
                    p_pull=args.p_pull,
                    migration_interval=args.migration_interval,
                )
                writer.writerow(row)
                fh.flush()

    print(f"Done. Results: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

