from dataclasses import dataclass
from math import hypot
from time import perf_counter

from ortools.sat.python import cp_model

from route_utils import (
    best_insertion_in_route,
    clone_routes,
    distance,
    insert_customer,
    objective,
    route_centroid,
    route_distance,
    route_load,
    two_opt_route,
    validate_routes,
)


MAX_SUBPROBLEM_CUSTOMERS = 22
DISTANCE_SCALE = 1000


@dataclass
class Subproblem:
    routes: tuple[int, ...]
    customers: list[int]
    score: float


def improve(instance, routes, config, rng, deadline: float) -> list[list[int]]:
    current = clone_routes(routes)
    best = clone_routes(current)
    best_obj = objective(instance, best)
    no_improvement_rounds = 0

    while perf_counter() < deadline and no_improvement_rounds < 3:
        improved = False
        subproblems = choose_subproblems(instance, current, rng)
        for subproblem in subproblems:
            if perf_counter() >= deadline:
                break

            remaining = deadline - perf_counter()
            solve_time = min(1.0, max(0.15, remaining * 0.10))
            candidate = solve_and_splice(instance, current, subproblem, solve_time)
            if candidate is None or validate_routes(instance, candidate):
                continue

            candidate_obj = objective(instance, candidate)
            current_obj = objective(instance, current)
            if candidate_obj + 1e-9 < current_obj:
                current = candidate
                improved = True
                if candidate_obj < best_obj:
                    best = clone_routes(candidate)
                    best_obj = candidate_obj
                break

        no_improvement_rounds = 0 if improved else no_improvement_rounds + 1

    return best


def choose_subproblems(instance, routes, rng) -> list[Subproblem]:
    route_indices = [idx for idx, route in enumerate(routes) if route]
    centroids = [route_centroid(instance, route) for route in routes]
    subproblems = []

    for idx, route_a in enumerate(route_indices):
        neighbors = sorted(
            (route_b for route_b in route_indices if route_b != route_a),
            key=lambda route_b: centroid_distance(centroids[route_a], centroids[route_b]),
        )
        for route_b in neighbors[:4]:
            route_set = tuple(sorted((route_a, route_b)))
            customers = customers_for_subproblem(instance, routes, route_set, centroids)
            score = subproblem_score(instance, routes, route_set, centroids)
            subproblems.append(Subproblem(route_set, customers, score))

            for route_c in neighbors[1:3]:
                if route_c == route_b:
                    continue
                triple = tuple(sorted((route_a, route_b, route_c)))
                triple_customers = customers_for_subproblem(instance, routes, triple, centroids)
                if len(triple_customers) <= MAX_SUBPROBLEM_CUSTOMERS:
                    triple_score = subproblem_score(instance, routes, triple, centroids)
                    subproblems.append(Subproblem(triple, triple_customers, triple_score))

    unique = {}
    for subproblem in subproblems:
        if subproblem.routes not in unique or subproblem.score > unique[subproblem.routes].score:
            unique[subproblem.routes] = subproblem

    ordered = sorted(unique.values(), key=lambda item: item.score, reverse=True)
    top = ordered[:30]
    rng.shuffle(top)
    return sorted(top, key=lambda item: item.score, reverse=True)


def customers_for_subproblem(instance, routes, route_indices, centroids) -> list[int]:
    customers = [customer for route_idx in route_indices for customer in routes[route_idx]]
    if len(customers) <= MAX_SUBPROBLEM_CUSTOMERS:
        return customers

    scored = []
    for route_idx in route_indices:
        other_centroids = [
            centroids[other_idx]
            for other_idx in route_indices
            if other_idx != route_idx
        ]
        route = routes[route_idx]
        padded = [0] + route + [0]
        for pos, customer in enumerate(route, start=1):
            marginal = (
                distance(instance, padded[pos - 1], customer)
                + distance(instance, customer, padded[pos + 1])
                - distance(instance, padded[pos - 1], padded[pos + 1])
            )
            boundary = min(
                abs(
                    point_distance(instance, customer, centroids[route_idx])
                    - point_distance(instance, customer, other_centroid)
                )
                for other_centroid in other_centroids
            )
            scored.append((marginal - boundary, customer))

    scored.sort(reverse=True)
    return [customer for _, customer in scored[:MAX_SUBPROBLEM_CUSTOMERS]]


def subproblem_score(instance, routes, route_indices, centroids) -> float:
    route_cost = sum(route_distance(instance, routes[idx]) for idx in route_indices)
    loads = [route_load(instance, routes[idx]) for idx in route_indices]
    capacity = max(1, int(instance.vehicleCapacity))
    tension = sum(load / capacity for load in loads)
    closeness = 0.0
    for pos, route_a in enumerate(route_indices):
        for route_b in route_indices[pos + 1 :]:
            closeness += 100.0 / (1.0 + centroid_distance(centroids[route_a], centroids[route_b]))
    return route_cost + 25.0 * tension + closeness


def solve_and_splice(instance, routes, subproblem: Subproblem, solve_time: float):
    selected = set(subproblem.customers)
    if not selected:
        return None

    frozen_routes = {
        route_idx: [customer for customer in routes[route_idx] if customer not in selected]
        for route_idx in subproblem.routes
    }
    residual_capacities = [
        int(instance.vehicleCapacity) - route_load(instance, frozen_routes[route_idx])
        for route_idx in subproblem.routes
    ]

    if any(capacity < 0 for capacity in residual_capacities):
        return None

    solved_routes = solve_cvrp_subproblem(
        instance,
        list(subproblem.customers),
        residual_capacities,
        solve_time,
    )
    if solved_routes is None:
        return None

    candidate = clone_routes(routes)
    old_distance = sum(route_distance(instance, routes[idx]) for idx in subproblem.routes)

    for local_vehicle, route_idx in enumerate(subproblem.routes):
        rebuilt = frozen_routes[route_idx][:]
        if not rebuilt:
            rebuilt = solved_routes[local_vehicle][:]
        else:
            for customer in solved_routes[local_vehicle]:
                position, _ = best_insertion_in_route(instance, rebuilt, customer)
                rebuilt = insert_customer(rebuilt, customer, position)
        candidate[route_idx] = two_opt_route(instance, rebuilt)

    new_distance = sum(route_distance(instance, candidate[idx]) for idx in subproblem.routes)
    if new_distance + 1e-9 >= old_distance:
        return None
    return candidate


def solve_cvrp_subproblem(instance, customers: list[int], capacities: list[int], solve_time: float):
    num_customers = len(customers)
    num_vehicles = len(capacities)
    if num_customers == 0:
        return [[] for _ in capacities]

    model = cp_model.CpModel()
    nodes = range(num_customers + 1)
    customer_nodes = range(1, num_customers + 1)
    x = {}
    y = {}
    order = {}
    used = {}

    for vehicle in range(num_vehicles):
        used[vehicle] = model.NewBoolVar(f"used_{vehicle}")
        for node in customer_nodes:
            y[vehicle, node] = model.NewBoolVar(f"y_{vehicle}_{node}")
            order[vehicle, node] = model.NewIntVar(0, num_customers, f"u_{vehicle}_{node}")
        for i in nodes:
            for j in nodes:
                if i != j:
                    x[vehicle, i, j] = model.NewBoolVar(f"x_{vehicle}_{i}_{j}")

    for node in customer_nodes:
        model.Add(sum(y[vehicle, node] for vehicle in range(num_vehicles)) == 1)

    for vehicle in range(num_vehicles):
        model.Add(sum(x[vehicle, 0, j] for j in customer_nodes) == used[vehicle])
        model.Add(sum(x[vehicle, i, 0] for i in customer_nodes) == used[vehicle])
        model.Add(
            sum(
                int(instance.demandOfCustomer[customers[node - 1]]) * y[vehicle, node]
                for node in customer_nodes
            )
            <= capacities[vehicle]
        )

        for node in customer_nodes:
            model.Add(sum(x[vehicle, i, node] for i in nodes if i != node) == y[vehicle, node])
            model.Add(sum(x[vehicle, node, j] for j in nodes if j != node) == y[vehicle, node])
            model.Add(order[vehicle, node] >= y[vehicle, node])
            model.Add(order[vehicle, node] <= num_customers * y[vehicle, node])

        for i in customer_nodes:
            for j in customer_nodes:
                if i == j:
                    continue
                model.Add(
                    order[vehicle, i] + 1
                    <= order[vehicle, j] + num_customers * (1 - x[vehicle, i, j])
                )

    objective_terms = []
    for vehicle in range(num_vehicles):
        for i in nodes:
            for j in nodes:
                if i == j:
                    continue
                customer_i = 0 if i == 0 else customers[i - 1]
                customer_j = 0 if j == 0 else customers[j - 1]
                scaled_distance = int(round(distance(instance, customer_i, customer_j) * DISTANCE_SCALE))
                objective_terms.append(scaled_distance * x[vehicle, i, j])
    model.Minimize(sum(objective_terms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max(0.05, solve_time)
    solver.parameters.num_search_workers = 1
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None

    routes = []
    for vehicle in range(num_vehicles):
        route = []
        current = 0
        seen = set()
        while True:
            next_node = None
            for j in nodes:
                if j != current and solver.BooleanValue(x[vehicle, current, j]):
                    next_node = j
                    break
            if next_node is None or next_node == 0:
                break
            if next_node in seen:
                return None
            seen.add(next_node)
            route.append(customers[next_node - 1])
            current = next_node
        routes.append(route)

    assigned = sorted(customer for route in routes for customer in route)
    if assigned != sorted(customers):
        return None
    return routes


def centroid_distance(left: tuple[float, float], right: tuple[float, float]) -> float:
    return hypot(left[0] - right[0], left[1] - right[1])


def point_distance(instance, customer: int, point: tuple[float, float]) -> float:
    return hypot(
        float(instance.xCoordOfCustomer[customer]) - point[0],
        float(instance.yCoordOfCustomer[customer]) - point[1],
    )
