from dataclasses import dataclass
from math import hypot
from time import perf_counter

from guidance import TabuMemory
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


BAND_SIZES = (2, 4, 6)


@dataclass
class BorderMove:
    route_a: int
    route_b: int
    customers_a_to_b: tuple[int, ...]
    customers_b_to_a: tuple[int, ...]
    delta: float


def improve(instance, routes, config, rng, deadline: float) -> list[list[int]]:
    current = clone_routes(routes)
    best = clone_routes(current)
    best_obj = objective(instance, best)
    tabu = TabuMemory(config.tabu_tenure) if config.tabu else None

    while perf_counter() < deadline:
        if tabu:
            tabu.next_iteration()
            tabu.prune()

        current_obj = objective(instance, current)
        move, candidate = find_best_border_move(instance, current, tabu, current_obj, best_obj, deadline)
        if move is None or candidate is None or move.delta >= -1e-9:
            break

        current = candidate
        candidate_obj = objective(instance, current)
        if candidate_obj < best_obj:
            best = clone_routes(current)
            best_obj = candidate_obj

        if tabu:
            for customer in move.customers_a_to_b:
                tabu.forbid_reverse_move(customer, move.route_a, move.route_b)
            for customer in move.customers_b_to_a:
                tabu.forbid_reverse_move(customer, move.route_b, move.route_a)

    return best


def find_best_border_move(instance, routes, tabu, current_obj: float, best_obj: float, deadline: float):
    best_move = None
    best_candidate = None
    for route_a, route_b in neighboring_route_pairs(instance, routes):
        if perf_counter() >= deadline:
            break

        candidates = generate_pair_candidates(instance, routes, route_a, route_b)
        for move in candidates:
            if perf_counter() >= deadline:
                return best_move, best_candidate
            if is_tabu_move(tabu, move, current_obj + move.delta < best_obj):
                continue

            candidate = apply_border_move(instance, routes, move)
            if candidate is None or validate_routes(instance, candidate):
                continue
            if best_move is None or move.delta < best_move.delta:
                best_move = move
                best_candidate = candidate

    return best_move, best_candidate


def generate_pair_candidates(instance, routes, route_a: int, route_b: int) -> list[BorderMove]:
    candidates = []
    band_a = boundary_customers(instance, routes, route_a, route_b)
    band_b = boundary_customers(instance, routes, route_b, route_a)

    for k in BAND_SIZES:
        if len(band_a) >= k:
            move = build_move(instance, routes, route_a, route_b, tuple(band_a[:k]), ())
            if move is not None:
                candidates.append(move)
        if len(band_b) >= k:
            move = build_move(instance, routes, route_a, route_b, (), tuple(band_b[:k]))
            if move is not None:
                candidates.append(move)
        if len(band_a) >= k and len(band_b) >= k:
            move = build_move(
                instance,
                routes,
                route_a,
                route_b,
                tuple(band_a[:k]),
                tuple(band_b[:k]),
            )
            if move is not None:
                candidates.append(move)

    return candidates


def build_move(
    instance,
    routes,
    route_a: int,
    route_b: int,
    customers_a_to_b: tuple[int, ...],
    customers_b_to_a: tuple[int, ...],
) -> BorderMove | None:
    if not customers_a_to_b and not customers_b_to_a:
        return None

    old_distance = route_distance(instance, routes[route_a]) + route_distance(instance, routes[route_b])
    candidate = apply_customer_sets(
        instance,
        routes,
        route_a,
        route_b,
        list(customers_a_to_b),
        list(customers_b_to_a),
    )
    if candidate is None:
        return None

    new_distance = route_distance(instance, candidate[route_a]) + route_distance(instance, candidate[route_b])
    return BorderMove(
        route_a,
        route_b,
        customers_a_to_b,
        customers_b_to_a,
        new_distance - old_distance,
    )


def apply_border_move(instance, routes, move: BorderMove):
    return apply_customer_sets(
        instance,
        routes,
        move.route_a,
        move.route_b,
        list(move.customers_a_to_b),
        list(move.customers_b_to_a),
    )


def apply_customer_sets(
    instance,
    routes,
    route_a: int,
    route_b: int,
    customers_a_to_b: list[int],
    customers_b_to_a: list[int],
):
    candidate = clone_routes(routes)
    customers_a_to_b, customers_b_to_a = repair_capacity(
        instance,
        routes,
        route_a,
        route_b,
        customers_a_to_b,
        customers_b_to_a,
    )
    if not customers_a_to_b and not customers_b_to_a:
        return None

    moving = set(customers_a_to_b) | set(customers_b_to_a)
    candidate[route_a] = [customer for customer in candidate[route_a] if customer not in moving]
    candidate[route_b] = [customer for customer in candidate[route_b] if customer not in moving]

    for customer in customers_b_to_a:
        position, _ = best_insertion_in_route(instance, candidate[route_a], customer)
        candidate[route_a] = insert_customer(candidate[route_a], customer, position)
    for customer in customers_a_to_b:
        position, _ = best_insertion_in_route(instance, candidate[route_b], customer)
        candidate[route_b] = insert_customer(candidate[route_b], customer, position)

    candidate[route_a] = two_opt_route(instance, candidate[route_a])
    candidate[route_b] = two_opt_route(instance, candidate[route_b])
    return candidate


def repair_capacity(
    instance,
    routes,
    route_a: int,
    route_b: int,
    customers_a_to_b: list[int],
    customers_b_to_a: list[int],
) -> tuple[list[int], list[int]]:
    load_a = route_load(instance, routes[route_a])
    load_b = route_load(instance, routes[route_b])
    capacity = int(instance.vehicleCapacity)

    def projected_loads():
        demand_a_to_b = sum(int(instance.demandOfCustomer[customer]) for customer in customers_a_to_b)
        demand_b_to_a = sum(int(instance.demandOfCustomer[customer]) for customer in customers_b_to_a)
        return load_a - demand_a_to_b + demand_b_to_a, load_b - demand_b_to_a + demand_a_to_b

    next_a, next_b = projected_loads()
    while next_a > capacity and customers_b_to_a:
        customers_b_to_a.pop()
        next_a, next_b = projected_loads()
    while next_b > capacity and customers_a_to_b:
        customers_a_to_b.pop()
        next_a, next_b = projected_loads()
    return customers_a_to_b, customers_b_to_a


def boundary_customers(instance, routes, source_route: int, target_route: int) -> list[int]:
    source_centroid = route_centroid(instance, routes[source_route])
    target_centroid = route_centroid(instance, routes[target_route])
    scored = []
    for customer in routes[source_route]:
        source_distance = point_distance(instance, customer, source_centroid)
        target_distance = point_distance(instance, customer, target_centroid)
        border_score = abs(source_distance - target_distance)
        target_pull = source_distance - target_distance
        scored.append((border_score - 0.25 * target_pull, customer))
    scored.sort()
    return [customer for _, customer in scored]


def neighboring_route_pairs(instance, routes) -> list[tuple[int, int]]:
    nonempty = [idx for idx, route in enumerate(routes) if route]
    centroids = [route_centroid(instance, route) for route in routes]
    pairs = []
    for route_a in nonempty:
        ordered = sorted(
            (route_b for route_b in nonempty if route_b != route_a),
            key=lambda route_b: centroid_distance(centroids[route_a], centroids[route_b]),
        )
        for route_b in ordered[:4]:
            pair = tuple(sorted((route_a, route_b)))
            if pair not in pairs:
                pairs.append(pair)
    return pairs


def is_tabu_move(tabu, move: BorderMove, aspiration: bool) -> bool:
    if tabu is None:
        return False
    for customer in move.customers_a_to_b:
        if tabu.is_tabu(customer, move.route_a, move.route_b, aspiration):
            return True
    for customer in move.customers_b_to_a:
        if tabu.is_tabu(customer, move.route_b, move.route_a, aspiration):
            return True
    return False


def centroid_distance(left: tuple[float, float], right: tuple[float, float]) -> float:
    return hypot(left[0] - right[0], left[1] - right[1])


def point_distance(instance, customer: int, point: tuple[float, float]) -> float:
    return hypot(
        float(instance.xCoordOfCustomer[customer]) - point[0],
        float(instance.yCoordOfCustomer[customer]) - point[1],
    )
