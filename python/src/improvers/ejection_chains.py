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
class ChainMove:
    delta: float
    source_route: int
    source_pos: int
    target_route: int
    target_pos: int
    ejected_pos: int
    rescue_route: int
    rescue_pos: int
    moved_customer: int
    ejected_customer: int


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
        move = find_best_chain(instance, current, current_obj, best_obj, granular, tabu, deadline)
        if move is None or move.delta >= -1e-9:
            break

        current = apply_chain(instance, current, move)
        current_obj = objective(instance, current)
        if current_obj < best_obj:
            best_obj = current_obj

        if tabu:
            tabu.forbid_reverse_move(
                move.moved_customer,
                move.source_route,
                move.target_route,
            )
            tabu.forbid_reverse_move(
                move.ejected_customer,
                move.target_route,
                move.rescue_route,
            )

    return current


def find_best_chain(
    instance,
    routes,
    current_obj: float,
    best_obj: float,
    granular: GranularNeighborhood | None,
    tabu: TabuMemory | None,
    deadline: float,
) -> ChainMove | None:
    best_move = None

    for source_route, route in enumerate(routes):
        old_source_distance = route_distance(instance, route)
        for source_pos, moved_customer in enumerate(route):
            reduced_source = remove_customer(route, source_pos)
            reduced_source_distance = route_distance(instance, reduced_source)
            target_routes = (
                granular.routes_for_customer(routes, moved_customer)
                if granular
                else range(len(routes))
            )

            for target_route in target_routes:
                if target_route == source_route or not routes[target_route]:
                    continue
                if perf_counter() >= deadline:
                    return best_move

                if tabu and tabu.is_tabu(
                    moved_customer,
                    source_route,
                    target_route,
                    current_obj < best_obj,
                ):
                    continue

                target = routes[target_route]
                target_load = route_load(instance, target)
                moved_demand = int(instance.demandOfCustomer[moved_customer])
                if target_load + moved_demand <= instance.vehicleCapacity:
                    continue

                for ejected_pos, ejected_customer in enumerate(target):
                    if granular and ejected_customer not in granular.neighbors.get(
                        moved_customer,
                        set(),
                    ):
                        continue

                    ejected_demand = int(instance.demandOfCustomer[ejected_customer])
                    if target_load + moved_demand - ejected_demand > instance.vehicleCapacity:
                        continue

                    target_without_ejected = remove_customer(target, ejected_pos)
                    target_insert_pos, _ = best_insertion_in_route(
                        instance,
                        target_without_ejected,
                        moved_customer,
                    )
                    target_after = insert_customer(
                        target_without_ejected,
                        moved_customer,
                        target_insert_pos,
                    )

                    rescue_routes = (
                        granular.routes_for_customer(routes, ejected_customer)
                        if granular
                        else range(len(routes))
                    )
                    for rescue_route in rescue_routes:
                        if rescue_route in (source_route, target_route):
                            continue
                        if perf_counter() >= deadline:
                            return best_move

                        if tabu and tabu.is_tabu(
                            ejected_customer,
                            target_route,
                            rescue_route,
                            current_obj < best_obj,
                        ):
                            continue

                        if (
                            route_load(instance, routes[rescue_route])
                            + ejected_demand
                            > instance.vehicleCapacity
                        ):
                            continue

                        rescue_pos, rescue_delta = best_insertion_in_route(
                            instance,
                            routes[rescue_route],
                            ejected_customer,
                        )
                        delta = (
                            reduced_source_distance
                            - old_source_distance
                            + route_distance(instance, target_after)
                            - route_distance(instance, target)
                            + rescue_delta
                        )

                        if best_move is None or delta < best_move.delta:
                            best_move = ChainMove(
                                delta,
                                source_route,
                                source_pos,
                                target_route,
                                target_insert_pos,
                                ejected_pos,
                                rescue_route,
                                rescue_pos,
                                moved_customer,
                                ejected_customer,
                            )

    return best_move


def apply_chain(instance, routes, move: ChainMove) -> list[list[int]]:
    updated = clone_routes(routes)

    moved_customer = updated[move.source_route].pop(move.source_pos)
    target = updated[move.target_route]
    ejected_customer = target.pop(move.ejected_pos)

    target_position = min(move.target_pos, len(target))
    updated[move.target_route] = insert_customer(target, moved_customer, target_position)
    rescue_position = min(move.rescue_pos, len(updated[move.rescue_route]))
    updated[move.rescue_route] = insert_customer(
        updated[move.rescue_route],
        ejected_customer,
        rescue_position,
    )

    for vehicle in {move.source_route, move.target_route, move.rescue_route}:
        updated[vehicle] = two_opt_route(instance, updated[vehicle])

    return updated
