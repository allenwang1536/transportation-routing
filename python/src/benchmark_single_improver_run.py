import argparse
import contextlib
import csv
import io
from pathlib import Path
from time import perf_counter

from route_utils import objective, route_loads, validate_routes
from solver_config import SolverConfig
from solver_runner import solve_instance
from vrpinstance import VRPInstance


FIELDNAMES = [
    "instance",
    "mode",
    "constructor",
    "improver",
    "granular",
    "tabu",
    "time_limit",
    "seed",
    "objective",
    "runtime",
    "valid",
    "percent_improvement_over_baseline",
    "pyvrp_gap_percent",
    "loads",
    "solution",
    "error",
]

FINALIST_MODES = {
    "regret_bidding+destroy_repair",
    "regret_bidding+destroy_repair+granular",
    "regret_bidding+destroy_repair+granular+tabu",
}


def load_instance(path: Path) -> VRPInstance:
    with contextlib.redirect_stdout(io.StringIO()):
        return VRPInstance(str(path))


def parse_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"1", "true", "yes", "on"}


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def valid_objective(row: dict) -> float | None:
    if not parse_bool(row.get("valid")) or row.get("objective") == "":
        return None
    return float(row["objective"])


def baseline_by_instance(rows: list[dict]) -> dict[str, float]:
    baselines = {}
    for row in rows:
        if row["constructor"] == "farthest_nearest" and parse_bool(row["valid"]):
            baselines[row["instance"]] = float(row["objective"])
    return baselines


def run_mode(path: Path, config: SolverConfig, baseline: float | None) -> dict:
    instance = load_instance(path)
    started = perf_counter()
    try:
        solution, reported, routes = solve_instance(instance, config)
        runtime = perf_counter() - started
        errors = validate_routes(instance, routes)
        recomputed = objective(instance, routes)
        valid = not errors and recomputed == round(float(reported), 2)
        result = recomputed if valid else ""
        error = "; ".join(errors)
        if recomputed != round(float(reported), 2):
            error = (error + "; " if error else "") + "objective mismatch"
    except Exception as exc:
        runtime = perf_counter() - started
        solution = ""
        routes = []
        result = ""
        valid = False
        error = f"{type(exc).__name__}: {exc}"

    improvement = ""
    if baseline and result != "":
        improvement = 100.0 * (baseline - float(result)) / baseline

    return {
        "instance": path.name,
        "mode": config.mode_name,
        "constructor": config.constructor,
        "improver": config.improver,
        "granular": config.granular,
        "tabu": config.tabu,
        "time_limit": config.time_limit,
        "seed": config.seed,
        "objective": result,
        "runtime": round(runtime, 4),
        "valid": valid,
        "percent_improvement_over_baseline": improvement,
        "pyvrp_gap_percent": "",
        "loads": route_loads(instance, routes) if valid else "",
        "solution": solution,
        "error": error,
    }


def summarize(rows: list[dict]) -> list[dict]:
    grouped = {}
    for row in rows:
        grouped.setdefault(row["mode"], []).append(row)

    wins = {mode: 0 for mode in grouped}
    for instance in sorted({row["instance"] for row in rows}):
        candidates = [
            row
            for row in rows
            if row["instance"] == instance and valid_objective(row) is not None
        ]
        if candidates:
            wins[min(candidates, key=lambda row: float(row["objective"]))["mode"]] += 1

    summary = []
    for mode, mode_rows in grouped.items():
        valid_rows = [row for row in mode_rows if valid_objective(row) is not None]
        objectives = [float(row["objective"]) for row in valid_rows]
        improvements = [
            float(row["percent_improvement_over_baseline"])
            for row in valid_rows
            if row["percent_improvement_over_baseline"] != ""
        ]
        summary.append(
            {
                "mode": mode,
                "valid": len(valid_rows),
                "avg_objective": sum(objectives) / len(objectives) if objectives else float("inf"),
                "avg_improvement": sum(improvements) / len(improvements) if improvements else 0.0,
                "wins": wins[mode],
            }
        )

    return sorted(
        summary,
        key=lambda row: (
            -row["valid"],
            -row["avg_improvement"],
            row["avg_objective"],
            -row["wins"],
        ),
    )


def markdown_table(summary: list[dict]) -> str:
    lines = [
        "| Mode | Valid | Avg Objective | Avg Improvement vs Baseline | Wins |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in summary:
        lines.append(
            f"| `{row['mode']}` | {row['valid']} | {row['avg_objective']:.2f} | "
            f"{row['avg_improvement']:.2f}% | {row['wins']} |"
        )
    return "\n".join(lines)


def head_to_head(rows: list[dict], new_mode: str) -> str:
    by_key = {(row["mode"], row["instance"]): valid_objective(row) for row in rows}
    instances = sorted({row["instance"] for row in rows})
    lines = [
        "| Opponent | New Mode Wins | Ties | Opponent Wins |",
        "|---|---:|---:|---:|",
    ]
    for opponent in sorted(FINALIST_MODES):
        new_wins = ties = opponent_wins = 0
        for instance in instances:
            new_obj = by_key.get((new_mode, instance))
            opponent_obj = by_key.get((opponent, instance))
            if new_obj is None or opponent_obj is None:
                continue
            if new_obj < opponent_obj:
                new_wins += 1
            elif new_obj > opponent_obj:
                opponent_wins += 1
            else:
                ties += 1
        lines.append(f"| `{opponent}` | {new_wins} | {ties} | {opponent_wins} |")
    return "\n".join(lines)


def write_readme(path: Path, summary: list[dict], run_rows: list[dict], comparison_rows: list[dict], config: SolverConfig):
    content = f"""# {config.mode_name} 30s Benchmark

This run benchmarks `{config.mode_name}` on all selected input instances and
compares it against the cached Step 3 finalist results.

## Configuration

- Constructor: `{config.constructor}`
- Improver: `{config.improver}`
- Granular: `{config.granular}`
- Tabu: `{config.tabu}`
- Time limit: `{config.time_limit}` seconds per instance
- Seed: `{config.seed}`

## Summary

{markdown_table(summary)}

## Head-to-Head

{head_to_head(comparison_rows, config.mode_name)}

## Files

- `run_results.csv`: new run only.
- `comparison_vs_finalists.csv`: cached finalists plus the new run.

Valid rows for new mode: {sum(parse_bool(row["valid"]) for row in run_rows)}/{len(run_rows)}.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def main():
    parser = argparse.ArgumentParser(description="Benchmark one improver against cached finalists.")
    parser.add_argument("--input-dir", default="../input")
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--cached-results-dir", default="experiments/results")
    parser.add_argument("--constructor", default="regret_bidding")
    parser.add_argument("--improver", required=True)
    parser.add_argument("--granular", action="store_true")
    parser.add_argument("--tabu", action="store_true")
    parser.add_argument("--time-limit", type=float, default=30.0)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-instances", type=int, default=None)
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    results_dir = Path(args.results_dir)
    cached_results_dir = Path(args.cached_results_dir)
    paths = sorted(input_dir.glob("*.vrp"))
    if args.max_instances is not None:
        paths = paths[: args.max_instances]

    baselines = baseline_by_instance(read_csv(cached_results_dir / "step1_constructors.csv"))
    path_names = {path.name for path in paths}
    finalist_rows = [
        row
        for row in read_csv(cached_results_dir / "step3_finalists.csv")
        if row["mode"] in FINALIST_MODES and row["instance"] in path_names
    ]
    config = SolverConfig(
        constructor=args.constructor,
        improver=args.improver,
        granular=args.granular,
        tabu=args.tabu,
        time_limit=args.time_limit,
        seed=args.seed,
    )

    run_rows = []
    for path in paths:
        row = run_mode(path, config, baselines.get(path.name))
        run_rows.append(row)
        print(
            f"{config.mode_name:45} {path.name:14} {row['objective']} valid={row['valid']}",
            flush=True,
        )

    comparison_rows = finalist_rows + run_rows
    write_csv(results_dir / "run_results.csv", run_rows)
    write_csv(results_dir / "comparison_vs_finalists.csv", comparison_rows)
    write_readme(results_dir / "README.md", summarize(comparison_rows), run_rows, comparison_rows, config)
    print(f"Wrote results to {results_dir}", flush=True)


if __name__ == "__main__":
    main()
