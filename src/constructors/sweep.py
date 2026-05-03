from constructors.farthest_nearest import build_best_fit_solution
from route_utils import (
    angle_from_depot,
    best_feasible_insertion,
    insert_customer,
    normalize_routes,
    two_opt_routes,
    validate_routes,
)


def construct(instance, rng=None) -> list[list[int]]:
    routes = [[] for _ in range(instance.numVehicles)]
    remaining = [int(instance.vehicleCapacity) for _ in range(instance.numVehicles)]
    customers = sorted(
        range(1, instance.numCustomers),
        key=lambda customer: (
            angle_from_depot(instance, customer),
            -int(instance.demandOfCustomer[customer]),
        ),
    )

    vehicle = 0
    unvisited = set(customers)
    for customer in customers:
        demand = int(instance.demandOfCustomer[customer])
        while vehicle < instance.numVehicles and demand > remaining[vehicle]:
            vehicle += 1

        if vehicle >= instance.numVehicles:
            break

        insertion = best_feasible_insertion(
            instance,
            routes,
            customer,
            candidate_vehicles=[vehicle],
        )
        if insertion is None:
            break

        _, position, _ = insertion
        routes[vehicle] = insert_customer(routes[vehicle], customer, position)
        remaining[vehicle] -= demand
        unvisited.remove(customer)

    if unvisited or validate_routes(instance, routes):
        routes, _ = build_best_fit_solution(instance)

    return two_opt_routes(instance, normalize_routes(routes, instance.numVehicles))
