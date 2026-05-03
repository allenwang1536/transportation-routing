from dataclasses import dataclass
from time import perf_counter

from guidance import GranularNeighborhood, TabuMemory
from route_utils import (
    best_insertion_in_route,
    clone_routes,
    insert_customer,
    objective,
    remove_customer,
    route_distance,
    route_load,
    two_opt_route,
)


@dataclass
class Move:
    kind: str
    delta: float
    route_a: int
    pos_a: int
    route_b: int
    pos_b: int
    customer_a: int
    customer_b: int | None = None


def improve(instance, routes, config, rng, deadline: float) -> list[list[int]]:
    current = clone_routes(routes)
    best_obj = objective(instance, current)
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

        current_obj = objective(instance, current)
        move = find_best_move(instance, current, current_obj, best_obj, granular, tabu, deadline)
        if move is None or move.delta >= -1e-9:
            break

        current = apply_move(instance, current, move)
        current_obj = objective(instance, current)
        if current_obj < best_obj:
            best_obj = current_obj

        if tabu:
            if move.kind == "relocate":
                tabu.forbid_reverse_move(move.customer_a, move.route_a, move.route_b)
            else:
                tabu.forbid_reverse_move(move.customer_a, move.route_a, move.route_b)
                tabu.forbid_reverse_move(move.customer_b, move.route_b, move.route_a)

    return current


def find_best_move(
    instance,
    routes: list[list[int]],
    current_obj: float,
    best_obj: float,
    granular: GranularNeighborhood | None,
    tabu: TabuMemory | None,
    deadline: float,
) -> Move | None:
    best_move = None
    checks = 0

    for route_a, route in enumerate(routes):
        old_a = route_distance(instance, route)
        for pos_a, customer in enumerate(route):
            reduced_a = remove_customer(route, pos_a)
            new_a_distance = route_distance(instance, reduced_a)

            target_routes = (
                granular.routes_for_customer(routes, customer)
                if granular
                else range(len(routes))
            )
            for route_b in target_routes:
                if route_a == route_b:
                    continue

                if perf_counter() >= deadline:
                    return best_move

                if (
                    route_load(instance, routes[route_b])
                    + int(instance.demandOfCustomer[customer])
                    > instance.vehicleCapacity
                ):
                    continue

                position, insertion_delta = best_insertion_in_route(
                    instance,
                    routes[route_b],
                    customer,
                )
                delta = new_a_distance - old_a + insertion_delta
                aspiration = current_obj + delta < best_obj
                if tabu and tabu.is_tabu(customer, route_a, route_b, aspiration):
                    continue

                if best_move is None or delta < best_move.delta:
                    best_move = Move(
                        "relocate",
                        delta,
                        route_a,
                        pos_a,
                        route_b,
                        position,
                        customer,
                    )

            checks += 1
            if checks % 500 == 0 and perf_counter() >= deadline:
                return best_move

    for route_a in range(len(routes)):
        for route_b in range(route_a + 1, len(routes)):
            if granular:
                route_pairs = granular.neighboring_route_pairs(routes)
                if (route_a, route_b) not in route_pairs:
                    continue

            old_distance = (
                route_distance(instance, routes[route_a])
                + route_distance(instance, routes[route_b])
            )
            load_a = route_load(instance, routes[route_a])
            load_b = route_load(instance, routes[route_b])

            for pos_a, customer_a in enumerate(routes[route_a]):
                for pos_b, customer_b in enumerate(routes[route_b]):
                    if perf_counter() >= deadline:
                        return best_move

                    if granular and customer_b not in granular.neighbors.get(customer_a, set()):
                        continue

                    demand_a = int(instance.demandOfCustomer[customer_a])
                    demand_b = int(instance.demandOfCustomer[customer_b])
                    if load_a - demand_a + demand_b > instance.vehicleCapacity:
                        continue
                    if load_b - demand_b + demand_a > instance.vehicleCapacity:
                        continue

                    new_route_a = routes[route_a][:]
                    new_route_b = routes[route_b][:]
                    new_route_a[pos_a] = customer_b
                    new_route_b[pos_b] = customer_a
                    delta = (
                        route_distance(instance, new_route_a)
                        + route_distance(instance, new_route_b)
                        - old_distance
                    )
                    aspiration = current_obj + delta < best_obj
                    if tabu and (
                        tabu.is_tabu(customer_a, route_a, route_b, aspiration)
                        or tabu.is_tabu(customer_b, route_b, route_a, aspiration)
                    ):
                        continue

                    if best_move is None or delta < best_move.delta:
                        best_move = Move(
                            "swap",
                            delta,
                            route_a,
                            pos_a,
                            route_b,
                            pos_b,
                            customer_a,
                            customer_b,
                        )

    return best_move


def apply_move(instance, routes: list[list[int]], move: Move) -> list[list[int]]:
    updated = clone_routes(routes)

    if move.kind == "relocate":
        customer = updated[move.route_a].pop(move.pos_a)
        updated[move.route_b] = insert_customer(updated[move.route_b], customer, move.pos_b)
        updated[move.route_a] = two_opt_route(instance, updated[move.route_a])
        updated[move.route_b] = two_opt_route(instance, updated[move.route_b])
        return updated

    updated[move.route_a][move.pos_a] = move.customer_b
    updated[move.route_b][move.pos_b] = move.customer_a
    updated[move.route_a] = two_opt_route(instance, updated[move.route_a])
    updated[move.route_b] = two_opt_route(instance, updated[move.route_b])
    return updated
