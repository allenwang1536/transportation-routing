from route_utils import (
    insert_customer,
    normalize_routes,
    best_insertion_in_route,
    two_opt_routes,
)


def construct(instance, rng=None) -> list[list[int]]:
    routes = [[] for _ in range(instance.numVehicles)]
    remaining_capacities = [
        int(instance.vehicleCapacity)
        for _ in range(instance.numVehicles)
    ]
    unvisited = set(range(1, instance.numCustomers))

    while unvisited:
        choice = choose_customer(instance, routes, remaining_capacities, unvisited)
        if choice is None:
            break

        customer, vehicle, position = choice
        routes[vehicle] = insert_customer(routes[vehicle], customer, position)
        remaining_capacities[vehicle] -= int(instance.demandOfCustomer[customer])
        unvisited.remove(customer)

    return two_opt_routes(instance, normalize_routes(routes, instance.numVehicles))


def choose_customer(
    instance,
    routes: list[list[int]],
    remaining_capacities: list[int],
    unvisited: set[int],
) -> tuple[int, int, int] | None:
    best_choice = None

    for customer in unvisited:
        bids = customer_bids(instance, routes, remaining_capacities, customer)
        if not bids:
            continue

        best_bid = bids[0]
        second_cost = bids[1][2] if len(bids) > 1 else best_bid[2] + 1_000_000
        regret = second_cost - best_bid[2]
        priority = (
            regret,
            int(instance.demandOfCustomer[customer]),
            best_bid[3],
            -best_bid[2],
        )

        if best_choice is None or priority > best_choice[0]:
            best_choice = (priority, customer, best_bid[0], best_bid[1])

    if best_choice is None:
        return None

    _, customer, vehicle, position = best_choice
    return customer, vehicle, position


def customer_bids(
    instance,
    routes: list[list[int]],
    remaining_capacities: list[int],
    customer: int,
):
    bids = []
    demand = int(instance.demandOfCustomer[customer])
    for vehicle in range(len(routes)):
        if demand > remaining_capacities[vehicle]:
            continue

        position, insertion_delta = best_insertion_in_route(
            instance,
            routes[vehicle],
            customer,
        )
        remaining_after = remaining_capacities[vehicle] - demand
        bid = insertion_delta + capacity_pressure(remaining_after)
        bids.append((vehicle, position, bid, insertion_delta))

    return sorted(bids, key=lambda bid: bid[2])


def capacity_pressure(remaining_after: int) -> float:
    if remaining_after < 0:
        return float("inf")
    return 0.01 * remaining_after
