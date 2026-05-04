from route_utils import (
    best_feasible_insertion,
    insert_customer,
    normalize_routes,
    two_opt_routes,
)


def construct(instance, rng=None) -> list[list[int]]:
    routes, unvisited = build_farthest_nearest_solution(instance)
    if unvisited:
        routes, unvisited = build_best_fit_solution(instance)
    return two_opt_routes(instance, normalize_routes(routes, instance.numVehicles))


def build_farthest_nearest_solution(instance) -> tuple[list[list[int]], set[int]]:
    from route_utils import distance

    routes = []
    unvisited = set(range(1, instance.numCustomers))

    for _ in range(instance.numVehicles):
        route = []
        remaining_capacity = int(instance.vehicleCapacity)
        current_location = 0

        feasible = [
            customer
            for customer in unvisited
            if int(instance.demandOfCustomer[customer]) <= remaining_capacity
        ]

        if feasible:
            first = max(feasible, key=lambda customer: distance(instance, 0, customer))
            route.append(first)
            unvisited.remove(first)
            remaining_capacity -= int(instance.demandOfCustomer[first])
            current_location = first

        while True:
            feasible = [
                customer
                for customer in unvisited
                if int(instance.demandOfCustomer[customer]) <= remaining_capacity
            ]
            if not feasible:
                break

            customer = min(
                feasible,
                key=lambda candidate: distance(instance, current_location, candidate),
            )
            route.append(customer)
            unvisited.remove(customer)
            remaining_capacity -= int(instance.demandOfCustomer[customer])
            current_location = customer

        routes.append(route)

    return routes, unvisited


def build_best_fit_solution(instance) -> tuple[list[list[int]], set[int]]:
    from route_utils import distance, remaining_capacities

    routes = [[] for _ in range(instance.numVehicles)]
    unvisited = set(range(1, instance.numCustomers))
    ordered = sorted(
        unvisited,
        key=lambda customer: (
            -int(instance.demandOfCustomer[customer]),
            -distance(instance, 0, customer),
        ),
    )

    for customer in ordered:
        capacities = remaining_capacities(instance, routes)
        feasible_vehicles = [
            vehicle
            for vehicle, capacity in enumerate(capacities)
            if int(instance.demandOfCustomer[customer]) <= capacity
        ]
        if not feasible_vehicles:
            continue

        insertion = best_feasible_insertion(
            instance,
            routes,
            customer,
            candidate_vehicles=feasible_vehicles,
        )
        if insertion is None:
            continue

        vehicle, position, _ = insertion
        routes[vehicle] = insert_customer(routes[vehicle], customer, position)
        unvisited.remove(customer)

    return routes, unvisited
