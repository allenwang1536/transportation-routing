import argparse
import contextlib
import csv
import io
from pathlib import Path
from time import perf_counter

from pyvrp import Model
from pyvrp.stop import MaxRuntime

from route_utils import distance, objective, route_loads, validate_routes
from solver_config import SolverConfig
from solver_runner import solve_instance
from vrpinstance import VRPInstance


CONSTRUCTORS = ["farthest_nearest", "sweep", "regret_bidding"]
HARD_INSTANCES = [
    "51_5_1.vrp",
    "121_7_1.vrp",
    "200_16_2.vrp",
    "262_25_1.vrp",
    "386_47_1.vrp",
]
IMPROVER_MODES = [
    ("relocate_swap", False, False),
    ("relocate_swap", True, False),
    ("relocate_swap", True, True),
    ("destroy_repair", False, False),
    ("destroy_repair", True, False),
    ("destroy_repair", True, True),
    ("ejection_chains", False, False),
    ("ejection_chains", True, False),
    ("ejection_chains", True, True),
]
DISTANCE_SCALE = 1000


def load_instance(path: Path) -> VRPInstance:
    with contextlib.redirect_stdout(io.StringIO()):
        return VRPInstance(str(path))


def run_homemade(path: Path, config: SolverConfig, baseline: float | None = None) -> dict:
    instance = load_instance(path)
    started = perf_counter()
    try:
        solution, reported, routes = solve_instance(instance, config)
        runtime = perf_counter() - started
        errors = validate_routes(instance, routes)
        recomputed = objective(instance, routes)
        valid = not errors and recomputed == round(float(reported), 2)
        result = recomputed if valid else None
        error = "; ".join(errors)
        if recomputed != round(float(reported), 2):
            error = (error + "; " if error else "") + "objective mismatch"
    except Exception as exc:
        runtime = perf_counter() - started
        solution = ""
        result = None
        valid = False
        error = f"{type(exc).__name__}: {exc}"

    improvement = ""
    if baseline and result is not None:
        improvement = 100.0 * (baseline - result) / baseline

    return {
        "instance": path.name,
        "mode": config.mode_name,
        "constructor": config.constructor,
        "improver": config.improver,
        "granular": config.granular,
        "tabu": config.tabu,
        "time_limit": config.time_limit,
        "seed": config.seed,
        "objective": result if result is not None else "",
        "runtime": round(runtime, 4),
        "valid": valid,
        "percent_improvement_over_baseline": improvement,
        "pyvrp_gap_percent": "",
        "loads": route_loads(instance, routes) if valid else "",
        "solution": solution,
        "error": error,
    }


def write_csv(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
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
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def valid_objective(row: dict) -> float | None:
    if not row.get("valid") or row.get("objective") == "":
        return None
    return float(row["objective"])


def baseline_by_instance(step1_rows: list[dict]) -> dict[str, float]:
    baselines = {}
    for row in step1_rows:
        if row["constructor"] == "farthest_nearest" and row["valid"]:
            baselines[row["instance"]] = float(row["objective"])
    return baselines


def summarize(rows: list[dict]) -> list[dict]:
    grouped = {}
    for row in rows:
        grouped.setdefault(row["mode"], []).append(row)

    wins = {mode: 0 for mode in grouped}
    instances = sorted({row["instance"] for row in rows})
    for instance in instances:
        candidates = [
            row
            for row in rows
            if row["instance"] == instance and valid_objective(row) is not None
        ]
        if not candidates:
            continue
        best = min(candidates, key=lambda row: float(row["objective"]))
        wins[best["mode"]] += 1

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
                "valid_count": len(valid_rows),
                "avg_objective": sum(objectives) / len(objectives) if objectives else float("inf"),
                "avg_improvement": sum(improvements) / len(improvements) if improvements else 0.0,
                "wins": wins[mode],
            }
        )

    return sorted(
        summary,
        key=lambda item: (
            -item["valid_count"],
            item["avg_objective"],
            -item["avg_improvement"],
            -item["wins"],
        ),
    )


def summarize_by_improvement(rows: list[dict]) -> list[dict]:
    summary = summarize(rows)
    return sorted(
        summary,
        key=lambda item: (
            -item["valid_count"],
            -item["avg_improvement"],
            item["avg_objective"],
            -item["wins"],
        ),
    )


def solve_pyvrp(instance: VRPInstance, time_limit: float, seed: int):
    model = Model()
    depot = model.add_depot(
        float(instance.xCoordOfCustomer[0]),
        float(instance.yCoordOfCustomer[0]),
    )
    clients = [
        model.add_client(
            float(instance.xCoordOfCustomer[customer]),
            float(instance.yCoordOfCustomer[customer]),
            delivery=int(instance.demandOfCustomer[customer]),
        )
        for customer in range(1, instance.numCustomers)
    ]
    model.add_vehicle_type(
        num_available=int(instance.numVehicles),
        capacity=int(instance.vehicleCapacity),
        start_depot=depot,
        end_depot=depot,
    )

    locations = [depot] + clients
    for i, origin in enumerate(locations):
        for j, destination in enumerate(locations):
            if i == j:
                continue
            model.add_edge(
                origin,
                destination,
                distance=int(round(distance(instance, i, j) * DISTANCE_SCALE)),
            )

    result = model.solve(MaxRuntime(time_limit), seed=seed, display=False)
    if not result.is_feasible():
        return None

    routes = [list(route.visits()) for route in result.best.routes()]
    while len(routes) < instance.numVehicles:
        routes.append([])
    return routes[: instance.numVehicles]


def run_pyvrp_reference(
    paths: list[Path],
    winner_rows: list[dict],
    final_time: float,
    seed: int,
) -> list[dict]:
    winner_by_instance = {
        row["instance"]: float(row["objective"])
        for row in winner_rows
        if valid_objective(row) is not None
    }
    rows = []
    for path in paths:
        instance = load_instance(path)
        started = perf_counter()
        try:
            routes = solve_pyvrp(instance, final_time, seed)
            runtime = perf_counter() - started
            if routes is None:
                raise RuntimeError("PyVRP did not find a feasible solution")
            errors = validate_routes(instance, routes)
            result = objective(instance, routes) if not errors else None
            valid = not errors
            error = "; ".join(errors)
        except Exception as exc:
            runtime = perf_counter() - started
            routes = []
            result = None
            valid = False
            error = f"{type(exc).__name__}: {exc}"

        gap = ""
        winner_obj = winner_by_instance.get(path.name)
        if winner_obj and result is not None:
            gap = 100.0 * (winner_obj - result) / result

        rows.append(
            {
                "instance": path.name,
                "mode": "pyvrp_reference",
                "constructor": "pyvrp",
                "improver": "pyvrp",
                "granular": "",
                "tabu": "",
                "time_limit": final_time,
                "seed": seed,
                "objective": result if result is not None else "",
                "runtime": round(runtime, 4),
                "valid": valid,
                "percent_improvement_over_baseline": "",
                "pyvrp_gap_percent": gap,
                "loads": route_loads(instance, routes) if valid else "",
                "solution": "",
                "error": error,
            }
        )
    return rows


def markdown_table(summary: list[dict]) -> str:
    lines = [
        "| Mode | Valid | Avg Objective | Avg Improvement vs Baseline | Wins |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in summary:
        avg_obj = row["avg_objective"]
        lines.append(
            f"| `{row['mode']}` | {row['valid_count']} | {avg_obj:.2f} | "
            f"{row['avg_improvement']:.2f}% | {row['wins']} |"
        )
    return "\n".join(lines)


def write_readme(
    path: Path,
    step1_summary,
    step2_summary,
    step3_summary,
    best_constructor: str,
    finalists: list[str],
    winner: str,
):
    content = f"""# VRP Experiment Results

This folder records the staged homemade-solver experiment.

Selection note: winners/finalists are ranked by average percent improvement over
the original `farthest_nearest` baseline, with raw average objective and wins
reported as supporting context. Raw averages are useful, but they are dominated
by the largest instances.

## Methods

- Constructors: `farthest_nearest`, `sweep`, `regret_bidding`.
- Improvers: `relocate_swap`, `destroy_repair`, `ejection_chains`.
- Guidance: `granular` nearest-neighbor filtering and `tabu` move memory.
- PyVRP is used only as an external reference for the final winner.

## Step 1: Constructor Bakeoff

Best constructor selected: `{best_constructor}`.

{markdown_table(step1_summary)}

## Step 2: Improver Screening

Screened 9 improver/guidance modes on the 5 hard instances for the configured
screening time.

Selected finalists: {", ".join(f"`{mode}`" for mode in finalists)}.

{markdown_table(step2_summary)}

## Step 3: Finalist Benchmark

Final homemade winner: `{winner}`.

Important nuance: the selected winner maximizes normalized improvement over the
baseline. A different mode may have a lower raw average objective or more
per-instance wins; report those supporting metrics alongside the selected
winner.

{markdown_table(step3_summary)}

## Step 4: PyVRP Reference

See `step4_pyvrp_reference.csv` for objective gaps between PyVRP and the final
homemade winner on each input instance.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def main():
    parser = argparse.ArgumentParser(description="Run the staged VRP experiment.")
    parser.add_argument("--input-dir", default="input")
    parser.add_argument("--results-dir", default="experiments/results")
    parser.add_argument("--screen-time", type=float, default=10.0)
    parser.add_argument("--final-time", type=float, default=30.0)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--skip-pyvrp", action="store_true")
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    results_dir = Path(args.results_dir)
    all_paths = sorted(input_dir.glob("*.vrp"))
    hard_paths = [input_dir / name for name in HARD_INSTANCES]
    log = lambda message: print(message, flush=True)

    log("Step 1: constructor bakeoff")
    step1_rows = []
    for constructor in CONSTRUCTORS:
        for path in all_paths:
            config = SolverConfig(constructor=constructor, seed=args.seed)
            row = run_homemade(path, config)
            step1_rows.append(row)
            log(f"  {constructor:16} {path.name:14} {row['objective']}")
    baselines = baseline_by_instance(step1_rows)
    for row in step1_rows:
        baseline = baselines.get(row["instance"])
        if baseline and row["objective"] != "":
            row["percent_improvement_over_baseline"] = (
                100.0 * (baseline - float(row["objective"])) / baseline
            )
    write_csv(results_dir / "step1_constructors.csv", step1_rows)
    step1_summary = summarize_by_improvement(step1_rows)
    best_constructor = step1_summary[0]["mode"]

    log(f"Step 2: improver screening with constructor {best_constructor}")
    step2_rows = []
    for improver, granular, tabu in IMPROVER_MODES:
        for path in hard_paths:
            config = SolverConfig(
                constructor=best_constructor,
                improver=improver,
                granular=granular,
                tabu=tabu,
                time_limit=args.screen_time,
                seed=args.seed,
            )
            row = run_homemade(path, config, baselines.get(path.name))
            step2_rows.append(row)
            log(f"  {config.mode_name:45} {path.name:14} {row['objective']}")
    write_csv(results_dir / "step2_improver_screen.csv", step2_rows)
    step2_summary = summarize_by_improvement(step2_rows)
    finalists = [row["mode"] for row in step2_summary[:3]]

    log("Step 3: finalist benchmark")
    step3_rows = []
    finalist_configs = [
        row
        for row in step2_rows
        if row["mode"] in finalists
    ]
    seen_modes = {}
    for row in finalist_configs:
        seen_modes[row["mode"]] = (
            row["improver"],
            bool(row["granular"]),
            bool(row["tabu"]),
        )

    for mode, (improver, granular, tabu) in seen_modes.items():
        for path in all_paths:
            config = SolverConfig(
                constructor=best_constructor,
                improver=improver,
                granular=granular,
                tabu=tabu,
                time_limit=args.final_time,
                seed=args.seed,
            )
            row = run_homemade(path, config, baselines.get(path.name))
            step3_rows.append(row)
            log(f"  {mode:45} {path.name:14} {row['objective']}")
    write_csv(results_dir / "step3_finalists.csv", step3_rows)
    step3_summary = summarize_by_improvement(step3_rows)
    winner = step3_summary[0]["mode"]
    winner_rows = [row for row in step3_rows if row["mode"] == winner]

    if not args.skip_pyvrp:
        log(f"Step 4: PyVRP reference against {winner}")
        step4_rows = run_pyvrp_reference(
            all_paths,
            winner_rows,
            args.final_time,
            args.seed,
        )
        write_csv(results_dir / "step4_pyvrp_reference.csv", step4_rows)

    write_readme(
        Path("experiments") / "README.md",
        step1_summary,
        step2_summary,
        step3_summary,
        best_constructor,
        finalists,
        winner,
    )

    log(f"Best constructor: {best_constructor}")
    log(f"Finalists: {', '.join(finalists)}")
    log(f"Winner: {winner}")


if __name__ == "__main__":
    main()
