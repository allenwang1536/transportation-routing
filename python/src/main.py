import json
from argparse import ArgumentParser
from pathlib import Path
from vrpinstance import VRPInstance
from timer import Timer
from solver_config import SolverConfig
from solver_runner import solve_instance

if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("input_file", type=str)
    parser.add_argument("--constructor", default=None)
    parser.add_argument("--improver", default=None)
    parser.add_argument("--granular", action="store_true")
    parser.add_argument("--tabu", action="store_true")
    parser.add_argument("--time-limit", type=float, default=None)
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()

    input_file = args.input_file
    path = Path(input_file)
    filename = path.name

    timer = Timer()
    timer.start()

    instance = VRPInstance(str(input_file))
    if any(
        value is not None
        for value in [args.constructor, args.improver, args.time_limit, args.seed]
    ) or args.granular or args.tabu:
        config = SolverConfig(
            constructor=args.constructor or "farthest_nearest",
            improver=args.improver or "none",
            granular=args.granular,
            tabu=args.tabu,
            time_limit=args.time_limit or 0,
            seed=args.seed or 0,
        )
        solution, objective_value, _ = solve_instance(instance, config)
    else:
        solution, objective_value = instance.solve()

    timer.stop()

    output_dict = {"Instance": filename,
                   "Time": f"{timer.getTime():.2f}",
                   "Result": objective_value if objective_value else "--",
                   "Solution": solution if solution else "--"}

    print(json.dumps(output_dict))
