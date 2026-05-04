import argparse
import contextlib
import io
from pathlib import Path

from ortools.constraint_solver import pywrapcp, routing_enums_pb2
from vrpinstance import VRPInstance


DISTANCE_SCALE = 1000


def parse_solution(solution: str) -> list[list[int]]:
    tokens = [int(token) for token in solution.split()]
    routes = []
    i = 0

    while i < len(tokens):
        if tokens[i] != 0:
            raise ValueError("Each route must start with depot 0.")

        i += 1
        route = []
        while i < len(tokens) and tokens[i] != 0:
            route.append(tokens[i])
            i += 1

        if i == len(tokens):
            raise ValueError("Each route must end with depot 0.")

        i += 1
        routes.append(route)

    return routes


def route_load(instance: VRPInstance, route: list[int]) -> int:
    return sum(int(instance.demandOfCustomer[customer]) for customer in route)


def objective(instance: VRPInstance, routes: list[list[int]]) -> float:
    return round(sum(instance.route_distance(route) for route in routes), 2)


def validate_routes(instance: VRPInstance, routes: list[list[int]]) -> list[str]:
    errors = []
    seen = [customer for route in routes for customer in route]
    expected = set(range(1, instance.numCustomers))

    if len(routes) != instance.numVehicles:
        errors.append(f"expected {instance.numVehicles} routes, found {len(routes)}")

    if set(seen) != expected:
        missing = sorted(expected - set(seen))
        extra = sorted(set(seen) - expected)
        if missing:
            errors.append(f"missing customers: {missing}")
        if extra:
            errors.append(f"unknown customers: {extra}")

    duplicates = sorted({customer for customer in seen if seen.count(customer) > 1})
    if duplicates:
        errors.append(f"duplicate customers: {duplicates}")

    for vehicle, route in enumerate(routes):
        load = route_load(instance, route)
        if load > instance.vehicleCapacity:
            errors.append(
                f"vehicle {vehicle} load {load} exceeds capacity "
                f"{instance.vehicleCapacity}"
            )

    return errors


def solve_with_ortools(
    instance: VRPInstance,
    time_limit_seconds: int,
) -> list[list[int]] | None:
    manager = pywrapcp.RoutingIndexManager(
        instance.numCustomers,
        instance.numVehicles,
        0,
    )
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index: int, to_index: int) -> int:
        origin = manager.IndexToNode(from_index)
        destination = manager.IndexToNode(to_index)
        return int(round(instance.distance(origin, destination) * DISTANCE_SCALE))

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    def demand_callback(from_index: int) -> int:
        customer = manager.IndexToNode(from_index)
        return int(instance.demandOfCustomer[customer])

    demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)
    routing.AddDimensionWithVehicleCapacity(
        demand_callback_index,
        0,
        [int(instance.vehicleCapacity)] * instance.numVehicles,
        True,
        "Capacity",
    )

    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    search_parameters.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    search_parameters.time_limit.seconds = time_limit_seconds

    assignment = routing.SolveWithParameters(search_parameters)
    if assignment is None:
        return None

    routes = []
    for vehicle in range(instance.numVehicles):
        route = []
        index = routing.Start(vehicle)
        while not routing.IsEnd(index):
            customer = manager.IndexToNode(index)
            if customer != 0:
                route.append(customer)
            index = assignment.Value(routing.NextVar(index))
        routes.append(route)

    return routes


def load_instance(path: Path) -> VRPInstance:
    with contextlib.redirect_stdout(io.StringIO()):
        return VRPInstance(str(path))


def solve_homemade(instance: VRPInstance) -> tuple[list[list[int]], float]:
    with contextlib.redirect_stdout(io.StringIO()):
        solution, reported_objective = instance.solve()
    return parse_solution(solution), float(reported_objective)


def check_instance(path: Path, time_limit_seconds: int) -> bool:
    instance = load_instance(path)
    homemade_routes, homemade_reported = solve_homemade(instance)
    homemade_errors = validate_routes(instance, homemade_routes)
    homemade_recomputed = objective(instance, homemade_routes)
    objective_matches = homemade_recomputed == round(homemade_reported, 2)

    ortools_routes = solve_with_ortools(instance, time_limit_seconds)
    ortools_errors = (
        validate_routes(instance, ortools_routes) if ortools_routes is not None else []
    )
    ortools_objective = (
        objective(instance, ortools_routes) if ortools_routes is not None else None
    )

    print(path)
    print(f"  homemade valid: {not homemade_errors and objective_matches}")
    print(f"  homemade objective: {homemade_reported:.2f}")
    print(f"  homemade recomputed objective: {homemade_recomputed:.2f}")
    print(f"  homemade loads: {[route_load(instance, route) for route in homemade_routes]}")
    if homemade_errors:
        print(f"  homemade errors: {homemade_errors}")
    if not objective_matches:
        print("  homemade errors: reported objective does not match route distance")

    if ortools_routes is None:
        print(f"  OR-Tools: no solution found in {time_limit_seconds}s")
    else:
        print(f"  OR-Tools valid: {not ortools_errors}")
        print(f"  OR-Tools objective: {ortools_objective:.2f}")
        print(f"  OR-Tools loads: {[route_load(instance, route) for route in ortools_routes]}")
        print(f"  gap vs OR-Tools: {homemade_recomputed - ortools_objective:.2f}")
        if ortools_errors:
            print(f"  OR-Tools errors: {ortools_errors}")
    print()

    return not homemade_errors and objective_matches


def expand_paths(paths: list[str]) -> list[Path]:
    expanded = []
    for raw_path in paths:
        path = Path(raw_path)
        if path.is_dir():
            expanded.extend(sorted(path.glob("*.vrp")))
        else:
            expanded.append(path)
    return expanded


def main():
    parser = argparse.ArgumentParser(
        description="Validate the homemade VRP solver and compare it to OR-Tools."
    )
    parser.add_argument("paths", nargs="+", help="VRP input files or folders.")
    parser.add_argument(
        "--time-limit",
        type=int,
        default=3,
        help="OR-Tools time limit per instance in seconds.",
    )
    args = parser.parse_args()

    paths = expand_paths(args.paths)
    all_valid = True
    for path in paths:
        all_valid = check_instance(path, args.time_limit) and all_valid

    if not all_valid:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
