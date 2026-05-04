from math import exp
from time import perf_counter

from guidance import GranularNeighborhood, TabuMemory
from route_utils import (
    best_feasible_insertion,
    clone_routes,
    customer_to_route,
    distance,
    insert_customer,
    objective,
    remove_customer,
    route_distance,
    two_opt_routes,
    validate_routes,
)


DESTROY_OPERATORS = ("random", "worst", "related", "route")


def improve(instance, routes, config, rng, deadline: float) -> list[list[int]]:
    current = clone_routes(routes)
    best = clone_routes(current)
    current_obj = objective(instance, current)
    best_obj = current_obj
    weights = {operator: 1.0 for operator in DESTROY_OPERATORS}
    granular = (
        GranularNeighborhood(instance, config.neighbor_count)
        if config.granular
        else None
    )
    tabu = TabuMemory(config.tabu_tenure) if config.tabu else None

    while perf_counter() < deadline:
        if tabu:
            tabu.next_iteration()
            tabu.prune()

        operator = choose_operator(weights, rng)
        partial, removed, original_routes = destroy(
            instance,
            current,
            operator,
            config.destroy_fraction,
            rng,
        )
        candidate = repair(instance, partial, removed, original_routes, granular, tabu)
        if candidate is None or validate_routes(instance, candidate):
            weights[operator] *= 0.95
            continue

        candidate = two_opt_routes(instance, candidate)
        candidate_obj = objective(instance, candidate)
        accepted = should_accept(current_obj, candidate_obj, best_obj, deadline, rng)

        if candidate_obj < best_obj:
            best = clone_routes(candidate)
            best_obj = candidate_obj
            weights[operator] += 5.0
            accepted = True
        elif accepted and candidate_obj < current_obj:
            weights[operator] += 1.0
        else:
            weights[operator] *= 0.98

        if accepted:
            if tabu:
                remember_reassignments(tabu, current, candidate)
            current = candidate
            current_obj = candidate_obj

    return best


def choose_operator(weights: dict[str, float], rng) -> str:
    total = sum(max(0.01, weight) for weight in weights.values())
    threshold = rng.random() * total
    cumulative = 0.0
    for operator, weight in weights.items():
        cumulative += max(0.01, weight)
        if cumulative >= threshold:
            return operator
    return DESTROY_OPERATORS[-1]


def destroy(instance, routes, operator: str, fraction: float, rng):
    count = max(1, int((instance.numCustomers - 1) * fraction))
    count = min(count, instance.numCustomers - 1)

    if operator == "worst":
        removed = worst_customers(instance, routes, count)
    elif operator == "related":
        removed = related_customers(instance, routes, count, rng)
    elif operator == "route":
        removed = route_customers(instance, routes, count)
    else:
        customers = [customer for route in routes for customer in route]
        removed = rng.sample(customers, min(count, len(customers)))

    original_routes = customer_to_route(routes)
    partial = clone_routes(routes)
    remove_set = set(removed)
    for vehicle, route in enumerate(partial):
        partial[vehicle] = [customer for customer in route if customer not in remove_set]

    return partial, removed, original_routes


def worst_customers(instance, routes, count: int) -> list[int]:
    scored = []
    for route in routes:
        padded = [0] + route + [0]
        for idx, customer in enumerate(route, start=1):
            marginal = (
                distance(instance, padded[idx - 1], customer)
                + distance(instance, customer, padded[idx + 1])
                - distance(instance, padded[idx - 1], padded[idx + 1])
            )
            scored.append((marginal, customer))
    scored.sort(reverse=True)
    return [customer for _, customer in scored[:count]]


def related_customers(instance, routes, count: int, rng) -> list[int]:
    customers = [customer for route in routes for customer in route]
    if not customers:
        return []
    seed = rng.choice(customers)
    ordered = sorted(customers, key=lambda customer: distance(instance, seed, customer))
    return ordered[:count]


def route_customers(instance, routes, count: int) -> list[int]:
    scored_routes = sorted(
        routes,
        key=lambda route: route_distance(instance, route),
        reverse=True,
    )
    removed = []
    for route in scored_routes:
        for customer in route:
            removed.append(customer)
            if len(removed) >= count:
                return removed
    return removed


def repair(
    instance,
    routes,
    removed: list[int],
    original_routes: dict[int, int],
    granular: GranularNeighborhood | None,
    tabu: TabuMemory | None,
) -> list[list[int]] | None:
    repaired = clone_routes(routes)
    remaining = set(removed)

    while remaining:
        choice = choose_repair_customer(
            instance,
            repaired,
            remaining,
            original_routes,
            granular,
            tabu,
        )
        if choice is None:
            return None

        customer, vehicle, position = choice
        repaired[vehicle] = insert_customer(repaired[vehicle], customer, position)
        remaining.remove(customer)

    return repaired


def choose_repair_customer(
    instance,
    routes,
    remaining: set[int],
    original_routes: dict[int, int],
    granular: GranularNeighborhood | None,
    tabu: TabuMemory | None,
):
    best_choice = None

    for customer in remaining:
        candidate_vehicles = (
            granular.routes_for_customer(routes, customer)
            if granular
            else list(range(len(routes)))
        )
        bids = []
        for vehicle in candidate_vehicles:
            original = original_routes.get(customer, -1)
            if tabu and tabu.is_tabu(customer, original, vehicle):
                continue
            insertion = best_feasible_insertion(
                instance,
                routes,
                customer,
                candidate_vehicles=[vehicle],
            )
            if insertion is not None:
                bids.append(insertion)

        if not bids and tabu:
            for vehicle in candidate_vehicles:
                insertion = best_feasible_insertion(
                    instance,
                    routes,
                    customer,
                    candidate_vehicles=[vehicle],
                )
                if insertion is not None:
                    bids.append(insertion)

        if not bids:
            continue

        bids.sort(key=lambda item: item[2])
        best = bids[0]
        second_delta = bids[1][2] if len(bids) > 1 else best[2] + 1_000_000
        regret = second_delta - best[2]
        priority = (regret, int(instance.demandOfCustomer[customer]), -best[2])
        if best_choice is None or priority > best_choice[0]:
            best_choice = (priority, customer, best[0], best[1])

    if best_choice is None:
        return None

    _, customer, vehicle, position = best_choice
    return customer, vehicle, position


def should_accept(current_obj: float, candidate_obj: float, best_obj: float, deadline, rng) -> bool:
    if candidate_obj <= current_obj:
        return True
    if candidate_obj < best_obj:
        return True

    temperature = max(1e-9, 0.02 * current_obj)
    probability = exp(-(candidate_obj - current_obj) / temperature)
    return rng.random() < probability


def remember_reassignments(tabu: TabuMemory, before, after):
    before_route = customer_to_route(before)
    after_route = customer_to_route(after)
    for customer, old_vehicle in before_route.items():
        new_vehicle = after_route.get(customer)
        if new_vehicle is not None and old_vehicle != new_vehicle:
            tabu.forbid_reverse_move(customer, old_vehicle, new_vehicle)
