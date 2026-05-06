#!/usr/bin/env python3
"""Benchmark the standalone single-threaded HGS solver across one or many instances.

Produces a CSV with the same schema as ga_multithreading_results / full_5min
so results can be compared directly.  Threading/migration columns are all 0
because ga_solver runs a single thread with no worker interaction.

Run from the repo root:
    python experiments/run_hgs_standalone.py                          # all 16 inputs, 300 s each
    python experiments/run_hgs_standalone.py --instances 386_47_1.vrp # single instance
    python experiments/run_hgs_standalone.py --time-limit 10          # quick smoke-check (still all instances)
    python experiments/run_hgs_standalone.py --no-compile             # skip recompile
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


def instance_sort_key(path: Path) -> tuple[int, str]:
    try:
        return (int(path.stem.split("_")[0]), path.name)
    except ValueError:
        return (10**9, path.name)


def resolve_instances(root: Path, requested: list[str] | None) -> list[Path]:
    input_dir = root / "input"
    if not requested:
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


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--instances",   nargs="+", default=None,
                   help="instance filenames or paths (default: all input/*.vrp)")
    p.add_argument("--time-limit",  type=float, default=300.0,
                   help="solver time limit in seconds per instance (default 300)")
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

    try:
        instances = resolve_instances(root, args.instances)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    if not instances:
        print("No instances found.", file=sys.stderr)
        return 1

    out = output_path(root, args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    print(f"Writing benchmark rows to {out}")

    rows: list[dict[str, Any]] = []
    with open(out, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for instance in instances:
            print(
                f"Running hgs_standalone on {instance.name} "
                f"({args.time_limit:.0f}s)...",
                flush=True,
            )
            row = run_hgs(root, instance, time_limit=args.time_limit, seed=args.seed)
            writer.writerow(row)
            fh.flush()
            rows.append(row)
            status = "OK" if not row["error"] else f"ERROR: {row['error']}"
            print(f"  {instance.name}: objective={row['objective']} "
                  f"valid={row['valid']} runtime={row['runtime']}s [{status}]")

    print(f"\nDone. Results: {out}")
    return 0 if all(not r["error"] for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
