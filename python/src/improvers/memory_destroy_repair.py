from dataclasses import dataclass, field
from math import atan2, exp, pi
from time import perf_counter

from guidance import GranularNeighborhood, TabuMemory
from route_utils import (
    best_insertion_in_route,
    clone_routes,
    customer_to_route,
    distance,
    insert_customer,
    objective,
    remaining_capacities,
    route_centroid,
    route_distance,
    route_load,
    two_opt_route,
    two_opt_routes,
    validate_routes,
)


DESTROY_OPERATORS = ("random", "worst", "related", "route", "memory")
MEMORY_DECAY = 0.995


@dataclass
class CleanupStats:
    successful_pairs: set[tuple[int, int]] = field(default_factory=set)
    failed_pairs: set[tuple[int, int]] = field(default_factory=set)


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


@dataclass
class MemoryState:
    territory_count: int
    operator_weights: dict[str, float] = field(
        default_factory=lambda: {operator: 1.0 for operator in DESTROY_OPERATORS}
    )
    unstable_customers: dict[int, float] = field(default_factory=dict)
    bad_edge_scores: dict[tuple[int, int], float] = field(default_factory=dict)
    route_pair_scores: dict[tuple[int, int], float] = field(default_factory=dict)
    customer_territory_scores: dict[tuple[int, int], float] = field(default_factory=dict)

    def decay(self):
        decay_mapping(self.unstable_customers)
        decay_mapping(self.bad_edge_scores)
        decay_mapping(self.route_pair_scores)
        decay_mapping(self.customer_territory_scores)
        for operator in self.operator_weights:
            self.operator_weights[operator] = max(
                0.05,
                1.0 + (self.operator_weights[operator] - 1.0) * MEMORY_DECAY,
            )


def improve(instance, routes, config, rng, deadline: float) -> list[list[int]]:
    current = clone_routes(routes)
    best = clone_routes(current)
    current_obj = objective(instance, current)
    best_obj = current_obj
    memory = MemoryState(max(4, min(24, int(instance.numVehicles))))
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

        memory.decay()
        operator = choose_operator(memory.operator_weights, rng)
        partial, removed, original_routes = destroy(
            instance,
            current,
            operator,
            config.destroy_fraction,
            memory,
            rng,
        )
        candidate = repair(
            instance,
            partial,
            removed,
            original_routes,
            memory,
            current_obj,
            granular,
            tabu,
            deadline,
        )

        cleanup_stats = CleanupStats()
        valid = False
        candidate_obj = None
        accepted = False

        if candidate is not None and perf_counter() < deadline:
            candidate, cleanup_stats = cleanup(
                instance,
                candidate,
                memory,
                granular,
                tabu,
                current_obj,
                best_obj,
                deadline,
            )
            candidate = two_opt_routes(instance, candidate)
            valid = not validate_routes(instance, candidate)
            if valid:
                candidate_obj = objective(instance, candidate)
                accepted = should_accept(current_obj, candidate_obj, best_obj, rng)

        improved_best = candidate_obj is not None and candidate_obj < best_obj
        improved_current = candidate_obj is not None and candidate_obj < current_obj

        if improved_best:
            best = clone_routes(candidate)
            best_obj = candidate_obj
            accepted = True

        update_memory(
            instance,
            memory,
            operator,
            current,
            candidate,
            cleanup_stats,
            valid,
            accepted,
            improved_current,
            improved_best,
        )

        if accepted and valid:
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


def destroy(instance, routes, operator: str, fraction: float, memory: MemoryState, rng):
    count = max(1, int((instance.numCustomers - 1) * fraction))
    count = min(count, instance.numCustomers - 1)

    if operator == "worst":
        removed = worst_customers(instance, routes, count)
    elif operator == "related":
        removed = related_customers(instance, routes, count, rng)
    elif operator == "route":
        removed = route_customers(instance, routes, count)
    elif operator == "memory":
        removed = memory_customers(instance, routes, memory, count, rng)
    else:
        customers = [customer for route in routes for customer in route]
        removed = rng.sample(customers, min(count, len(customers)))

    if operator != "memory" and count > 3:
        removed = blend_memory_targets(instance, routes, memory, removed, count, rng)

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


def memory_customers(instance, routes, memory: MemoryState, count: int, rng) -> list[int]:
    scored = []
    for route in routes:
        padded = [0] + route + [0]
        for idx, customer in enumerate(route, start=1):
            prev_customer = padded[idx - 1]
            next_customer = padded[idx + 1]
            score = memory.unstable_customers.get(customer, 0.0)
            score += edge_score(memory, customer, prev_customer)
            score += edge_score(memory, customer, next_customer)
            score += 0.01 * rng.random()
            scored.append((score, customer))

    if not scored:
        return []

    scored.sort(reverse=True)
    chosen = [customer for _, customer in scored[:count]]
    if max(score for score, _ in scored) <= 0:
        customers = [customer for _, customer in scored]
        return rng.sample(customers, min(count, len(customers)))
    return chosen


def blend_memory_targets(
    instance,
    routes,
    memory: MemoryState,
    removed: list[int],
    count: int,
    rng,
) -> list[int]:
    memory_count = max(1, int(0.25 * count))
    memory_targets = memory_customers(instance, routes, memory, memory_count, rng)
    blended = list(dict.fromkeys(memory_targets + removed))
    if len(blended) > count:
        return blended[:count]
    return blended


def repair(
    instance,
    routes,
    removed: list[int],
    original_routes: dict[int, int],
    memory: MemoryState,
    current_obj: float,
    granular: GranularNeighborhood | None,
    tabu: TabuMemory | None,
    deadline: float,
) -> list[list[int]] | None:
    repaired = clone_routes(routes)
    remaining = set(removed)
    bias_cap = 0.20 * max(1.0, current_obj / max(1, instance.numCustomers - 1))

    while remaining and perf_counter() < deadline:
        choice = choose_repair_customer(
            instance,
            repaired,
            remaining,
            original_routes,
            memory,
            bias_cap,
            granular,
            tabu,
        )
        if choice is None:
            return None

        customer, vehicle, position = choice
        repaired[vehicle] = insert_customer(repaired[vehicle], customer, position)
        remaining.remove(customer)

    return repaired if not remaining else None


def choose_repair_customer(
    instance,
    routes,
    remaining: set[int],
    original_routes: dict[int, int],
    memory: MemoryState,
    bias_cap: float,
    granular: GranularNeighborhood | None,
    tabu: TabuMemory | None,
):
    best_choice = None
    territories = route_territories(instance, routes, memory.territory_count)

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
            insertion = memory_feasible_insertion(
                instance,
                routes,
                customer,
                vehicle,
                territories[vehicle],
                memory,
                bias_cap,
            )
            if insertion is not None:
                bids.append(insertion)

        if not bids and tabu:
            for vehicle in candidate_vehicles:
                insertion = memory_feasible_insertion(
                    instance,
                    routes,
                    customer,
                    vehicle,
                    territories[vehicle],
                    memory,
                    bias_cap,
                )
                if insertion is not None:
                    bids.append(insertion)

        if not bids:
            continue

        bids.sort(key=lambda item: item[3])
        best = bids[0]
        second_adjusted = bids[1][3] if len(bids) > 1 else best[3] + 1_000_000
        regret = second_adjusted - best[3]
        priority = (regret, int(instance.demandOfCustomer[customer]), -best[3])
        if best_choice is None or priority > best_choice[0]:
            best_choice = (priority, customer, best[0], best[1])

    if best_choice is None:
        return None

    _, customer, vehicle, position = best_choice
    return customer, vehicle, position


def memory_feasible_insertion(
    instance,
    routes,
    customer: int,
    vehicle: int,
    territory: int,
    memory: MemoryState,
    bias_cap: float,
) -> tuple[int, int, float, float] | None:
    capacities = remaining_capacities(instance, routes)
    if int(instance.demandOfCustomer[customer]) > capacities[vehicle]:
        return None

    position, delta = best_insertion_in_route(instance, routes[vehicle], customer)
    raw_score = memory.customer_territory_scores.get((customer, territory), 0.0)
    memory_bonus = max(-bias_cap, min(bias_cap, raw_score))
    adjusted_delta = delta - memory_bonus
    return vehicle, position, delta, adjusted_delta


def cleanup(
    instance,
    routes,
    memory: MemoryState,
    granular: GranularNeighborhood | None,
    tabu: TabuMemory | None,
    current_obj: float,
    best_obj: float,
    deadline: float,
) -> tuple[list[list[int]], CleanupStats]:
    updated = clone_routes(routes)
    stats = CleanupStats()
    max_passes = 3

    for _ in range(max_passes):
        if perf_counter() >= deadline:
            break

        move = find_best_cleanup_move(
            instance,
            updated,
            memory,
            granular,
            tabu,
            current_obj,
            best_obj,
            stats,
            deadline,
        )
        if move is None or move.delta >= -1e-9:
            break

        pair_key = route_pair_key(instance, updated, move.route_a, move.route_b, memory)
        updated = apply_move(instance, updated, move)
        stats.successful_pairs.add(pair_key)

        if tabu:
            if move.kind == "relocate":
                tabu.forbid_reverse_move(move.customer_a, move.route_a, move.route_b)
            else:
                tabu.forbid_reverse_move(move.customer_a, move.route_a, move.route_b)
                tabu.forbid_reverse_move(move.customer_b, move.route_b, move.route_a)

    return updated, stats


def find_best_cleanup_move(
    instance,
    routes,
    memory: MemoryState,
    granular: GranularNeighborhood | None,
    tabu: TabuMemory | None,
    current_obj: float,
    best_obj: float,
    stats: CleanupStats,
    deadline: float,
) -> Move | None:
    best_move = None
    for route_a, route_b in ordered_route_pairs(instance, routes, memory, granular):
        if perf_counter() >= deadline:
            return best_move

        pair_key = route_pair_key(instance, routes, route_a, route_b, memory)
        before_best = best_move
        best_move = best_relocate_between(
            instance,
            routes,
            route_a,
            route_b,
            current_obj,
            best_obj,
            granular,
            tabu,
            best_move,
            deadline,
        )
        best_move = best_swap_between(
            instance,
            routes,
            route_a,
            route_b,
            current_obj,
            best_obj,
            granular,
            tabu,
            best_move,
            deadline,
        )
        if best_move is before_best:
            stats.failed_pairs.add(pair_key)

    return best_move


def best_relocate_between(
    instance,
    routes,
    route_a: int,
    route_b: int,
    current_obj: float,
    best_obj: float,
    granular: GranularNeighborhood | None,
    tabu: TabuMemory | None,
    best_move: Move | None,
    deadline: float,
) -> Move | None:
    for source, target in ((route_a, route_b), (route_b, route_a)):
        old_source = route_distance(instance, routes[source])
        target_load = route_load(instance, routes[target])
        for pos, customer in enumerate(routes[source]):
            if perf_counter() >= deadline:
                return best_move
            if granular and not granular.route_is_relevant(customer, routes[target]):
                continue
            if (
                target_load + int(instance.demandOfCustomer[customer])
                > instance.vehicleCapacity
            ):
                continue

            reduced_source = routes[source][:pos] + routes[source][pos + 1 :]
            new_source_distance = route_distance(instance, reduced_source)
            position, insertion_delta = best_insertion_in_route(
                instance,
                routes[target],
                customer,
            )
            delta = new_source_distance - old_source + insertion_delta
            aspiration = current_obj + delta < best_obj
            if tabu and tabu.is_tabu(customer, source, target, aspiration):
                continue

            if best_move is None or delta < best_move.delta:
                best_move = Move(
                    "relocate",
                    delta,
                    source,
                    pos,
                    target,
                    position,
                    customer,
                )

    return best_move


def best_swap_between(
    instance,
    routes,
    route_a: int,
    route_b: int,
    current_obj: float,
    best_obj: float,
    granular: GranularNeighborhood | None,
    tabu: TabuMemory | None,
    best_move: Move | None,
    deadline: float,
) -> Move | None:
    old_distance = route_distance(instance, routes[route_a]) + route_distance(
        instance,
        routes[route_b],
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


def apply_move(instance, routes, move: Move) -> list[list[int]]:
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


def ordered_route_pairs(
    instance,
    routes,
    memory: MemoryState,
    granular: GranularNeighborhood | None,
) -> list[tuple[int, int]]:
    all_pairs = [
        (route_a, route_b)
        for route_a in range(len(routes))
        for route_b in range(route_a + 1, len(routes))
    ]
    granular_pairs = granular.neighboring_route_pairs(routes) if granular else set()

    def pair_priority(pair):
        key = route_pair_key(instance, routes, pair[0], pair[1], memory)
        memory_score = memory.route_pair_scores.get(key, 0.0)
        granular_score = 1.0 if pair in granular_pairs else 0.0
        return (memory_score, granular_score)

    return sorted(all_pairs, key=pair_priority, reverse=True)


def update_memory(
    instance,
    memory: MemoryState,
    operator: str,
    before,
    candidate,
    cleanup_stats: CleanupStats,
    valid: bool,
    accepted: bool,
    improved_current: bool,
    improved_best: bool,
):
    if improved_best:
        memory.operator_weights[operator] += 5.0
        reward = 2.0
    elif accepted and improved_current:
        memory.operator_weights[operator] += 1.0
        reward = 0.75
    elif accepted:
        memory.operator_weights[operator] *= 0.99
        reward = 0.0
    else:
        memory.operator_weights[operator] *= 0.95
        reward = -0.75

    if valid and candidate is not None and accepted and reward > 0:
        update_customer_memory(instance, memory, before, candidate, max(0.25, reward))
        update_route_pair_memory(memory, cleanup_stats, max(0.25, reward))
        weaken_edges(memory, collect_customer_edges(candidate), 0.5 if improved_best else 0.2)
    elif candidate is not None:
        new_edges = collect_customer_edges(candidate) - collect_customer_edges(before)
        for edge in new_edges:
            memory.bad_edge_scores[edge] = memory.bad_edge_scores.get(edge, 0.0) + 1.0
        update_route_pair_memory(memory, cleanup_stats, -0.5)


def update_customer_memory(instance, memory: MemoryState, before, after, reward: float):
    before_route = customer_to_route(before)
    after_route = customer_to_route(after)
    after_territories = route_territories(instance, after, memory.territory_count)

    for customer, old_route in before_route.items():
        new_route = after_route.get(customer)
        if new_route is None or old_route == new_route:
            continue

        territory = after_territories[new_route]
        memory.unstable_customers[customer] = (
            memory.unstable_customers.get(customer, 0.0) + reward
        )
        key = (customer, territory)
        memory.customer_territory_scores[key] = (
            memory.customer_territory_scores.get(key, 0.0) + reward
        )


def update_route_pair_memory(
    memory: MemoryState,
    stats: CleanupStats,
    reward: float,
):
    for pair in stats.successful_pairs:
        memory.route_pair_scores[pair] = memory.route_pair_scores.get(pair, 0.0) + reward
    for pair in stats.failed_pairs:
        memory.route_pair_scores[pair] = memory.route_pair_scores.get(pair, 0.0) - 0.1


def should_accept(current_obj: float, candidate_obj: float, best_obj: float, rng) -> bool:
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


def route_territories(instance, routes, territory_count: int) -> list[int]:
    return [
        territory_for_point(instance, *route_centroid(instance, route), territory_count)
        for route in routes
    ]


def route_pair_key(
    instance,
    routes,
    route_a: int,
    route_b: int,
    memory: MemoryState,
) -> tuple[int, int]:
    territories = route_territories(instance, routes, memory.territory_count)
    return tuple(sorted((territories[route_a], territories[route_b])))


def territory_for_point(instance, x_coord: float, y_coord: float, territory_count: int) -> int:
    angle = atan2(
        y_coord - float(instance.yCoordOfCustomer[0]),
        x_coord - float(instance.xCoordOfCustomer[0]),
    )
    normalized = (angle + pi) / (2 * pi)
    return min(territory_count - 1, int(normalized * territory_count))


def collect_customer_edges(routes) -> set[tuple[int, int]]:
    edges = set()
    for route in routes:
        for left, right in zip(route, route[1:]):
            edges.add(edge_key(left, right))
    return edges


def edge_score(memory: MemoryState, customer: int, other: int) -> float:
    if other == 0:
        return 0.0
    return memory.bad_edge_scores.get(edge_key(customer, other), 0.0)


def edge_key(left: int, right: int) -> tuple[int, int]:
    return tuple(sorted((left, right)))


def weaken_edges(memory: MemoryState, edges: set[tuple[int, int]], amount: float):
    for edge in edges:
        if edge not in memory.bad_edge_scores:
            continue
        memory.bad_edge_scores[edge] *= max(0.0, 1.0 - amount)


def decay_mapping(mapping):
    stale = []
    for key, value in mapping.items():
        updated = value * MEMORY_DECAY
        if abs(updated) < 1e-4:
            stale.append(key)
        else:
            mapping[key] = updated
    for key in stale:
        del mapping[key]
