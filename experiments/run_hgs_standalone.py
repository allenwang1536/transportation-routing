#!/usr/bin/env python3
"""Benchmark the standalone single-threaded HGS solver on one instance.

Produces a CSV with the same schema as ga_multithreading_results / full_5min
so results can be compared directly.  Threading/migration columns are all 0
because ga_solver runs a single thread with no worker interaction.

Run from the repo root:
    python experiments/run_hgs_standalone.py                    # 300 s, 386_47_1.vrp
    python experiments/run_hgs_standalone.py --time-limit 10    # quick smoke-check
    python experiments/run_hgs_standalone.py --no-compile       # skip recompile
"""

import argparse
import csv
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

CSV_FIELDS = [
    "instance", "model", "seed", "time_limit", "runtime", "objective", "valid",
    "best_source", "pool_size",
    "accepted_seeds", "rejected_seeds",
    "accepted_children", "rejected_children",
    "accepted_migrants", "rejected_migrants",
    "pulls_attempted", "pulls_accepted",
    "solution", "error",
]


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def compile_solver(root: Path) -> None:
    print("Compiling C++ solvers...")
    subprocess.run(["bash", "compile.sh"], cwd=root / "cpp", check=True)
    print("Compilation done.")


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


def run_hgs(
    root: Path,
    instance: Path,
    *,
    time_limit: float,
    seed: int,
) -> dict[str, Any]:
    cmd = [
        str(root / "cpp" / "ga_solver"),
        str(instance),
        "--time-limit", str(time_limit),
        "--seed", str(seed),
    ]

    print(f"Running: {' '.join(cmd)}")

    try:
        completed = subprocess.run(
            cmd,
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=time_limit + 60,
        )
    except subprocess.TimeoutExpired as exc:
        return _error_row(instance.name, seed, time_limit, f"timeout after {exc.timeout:.1f}s")

    if completed.returncode != 0:
        return _error_row(instance.name, seed, time_limit,
                          completed.stderr.strip() or "solver exited non-zero")

    try:
        lines = [l.strip() for l in completed.stdout.splitlines() if l.strip()]
        parsed = json.loads(lines[-1])
        solver_line = json.dumps(parsed)
        valid = validate_solution(root, instance, solver_line)
    except Exception as exc:
        return _error_row(instance.name, seed, time_limit, f"bad output: {exc}")

    return {
        "instance":          instance.name,
        "model":             "hgs_standalone",
        "seed":              seed,
        "time_limit":        time_limit,
        "runtime":           parsed.get("Time", ""),
        "objective":         parsed.get("Result", ""),
        "valid":             valid,
        "best_source":       "ga",
        "pool_size":         0,
        "accepted_seeds":    0,
        "rejected_seeds":    0,
        "accepted_children": 0,
        "rejected_children": 0,
        "accepted_migrants": 0,
        "rejected_migrants": 0,
        "pulls_attempted":   0,
        "pulls_accepted":    0,
        "solution":          parsed.get("Solution", ""),
        "error":             "",
    }


def _error_row(instance_name: str, seed: int, time_limit: float, msg: str) -> dict[str, Any]:
    return {k: "" for k in CSV_FIELDS} | {
        "instance": instance_name,
        "model": "hgs_standalone",
        "seed": seed,
        "time_limit": time_limit,
        "valid": False,
        "error": msg,
    }


def output_path(root: Path, requested: str | None) -> Path:
    if requested:
        p = Path(requested)
        return p if p.is_absolute() else root / p
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return root / "experiments" / f"hgs_standalone_5min_{stamp}.csv"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--instance",    default="input/386_47_1.vrp",
                   help="path to .vrp file (relative to repo root)")
    p.add_argument("--time-limit",  type=float, default=300.0,
                   help="solver time limit in seconds (default 300)")
    p.add_argument("--seed",        type=int, default=42)
    p.add_argument("--output",      default=None,
                   help="output CSV path (default: auto-timestamped in experiments/)")
    p.add_argument("--no-compile",  action="store_true",
                   help="skip C++ recompilation")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    root = repo_root()

    if not args.no_compile:
        compile_solver(root)

    instance = root / args.instance
    if not instance.exists():
        print(f"Error: instance not found: {instance}", file=sys.stderr)
        return 1

    out = output_path(root, args.output)
    out.parent.mkdir(parents=True, exist_ok=True)

    row = run_hgs(root, instance, time_limit=args.time_limit, seed=args.seed)

    with open(out, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerow(row)

    print(f"\nResult: instance={row['instance']}  model={row['model']}  "
          f"objective={row['objective']}  valid={row['valid']}  "
          f"runtime={row['runtime']}s")
    print(f"Saved → {out}")

    # Quick comparison against known full_5min results for 386_47_1.vrp
    if "386_47_1" in str(instance):
        print("\nComparison (386_47_1.vrp, 300 s, seed 42):")
        print(f"  hgs_standalone (this run): {row['objective']}")
        print(f"  independent  (4-thread, no sharing): 25584.49")
        print(f"  one_way      (workers → GA):          25934.67")
        print(f"  bidirectional (full exchange):         24929.19")

    return 0 if not row["error"] else 1


if __name__ == "__main__":
    sys.exit(main())
