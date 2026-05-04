from math import atan2, sqrt


def clone_routes(routes: list[list[int]]) -> list[list[int]]:
    return [route[:] for route in routes]


def distance(instance, i: int, j: int) -> float:
    cache = getattr(instance, "_distance_cache", None)
    if cache is not None:
        return cache[i][j]

    cache = build_distance_cache(instance)
    instance._distance_cache = cache
    return cache[i][j]


def build_distance_cache(instance) -> list[list[float]]:
    num_customers = int(instance.numCustomers)
    cache = [[0.0 for _ in range(num_customers)] for _ in range(num_customers)]
    for i in range(num_customers):
        for j in range(i + 1, num_customers):
            x_diff = instance.xCoordOfCustomer[i] - instance.xCoordOfCustomer[j]
            y_diff = instance.yCoordOfCustomer[i] - instance.yCoordOfCustomer[j]
            value = sqrt(x_diff * x_diff + y_diff * y_diff)
            cache[i][j] = value
            cache[j][i] = value
    return cache


def uncached_distance(instance, i: int, j: int) -> float:
    x_diff = instance.xCoordOfCustomer[i] - instance.xCoordOfCustomer[j]
    y_diff = instance.yCoordOfCustomer[i] - instance.yCoordOfCustomer[j]
    return sqrt(x_diff * x_diff + y_diff * y_diff)


def angle_from_depot(instance, customer: int) -> float:
    return atan2(
        instance.yCoordOfCustomer[customer] - instance.yCoordOfCustomer[0],
        instance.xCoordOfCustomer[customer] - instance.xCoordOfCustomer[0],
    )


def route_distance(instance, route: list[int]) -> float:
    if not route:
        return 0.0

    total = distance(instance, 0, route[0])
    for idx in range(len(route) - 1):
        total += distance(instance, route[idx], route[idx + 1])
    total += distance(instance, route[-1], 0)
    return total


def objective(instance, routes: list[list[int]]) -> float:
    return round(sum(route_distance(instance, route) for route in routes), 2)


def route_load(instance, route: list[int]) -> int:
    return sum(int(instance.demandOfCustomer[customer]) for customer in route)


def route_loads(instance, routes: list[list[int]]) -> list[int]:
    return [route_load(instance, route) for route in routes]


def remaining_capacities(instance, routes: list[list[int]]) -> list[int]:
    return [
        int(instance.vehicleCapacity) - route_load(instance, route)
        for route in routes
    ]


def normalize_routes(routes: list[list[int]], num_routes: int) -> list[list[int]]:
    normalized = clone_routes(routes[:num_routes])
    while len(normalized) < num_routes:
        normalized.append([])
    return normalized


def validate_routes(instance, routes: list[list[int]]) -> list[str]:
    errors = []
    normalized = normalize_routes(routes, instance.numVehicles)
    seen = [customer for route in normalized for customer in route]
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

    for vehicle, route in enumerate(normalized):
        load = route_load(instance, route)
        if load > instance.vehicleCapacity:
            errors.append(
                f"vehicle {vehicle} load {load} exceeds capacity "
                f"{instance.vehicleCapacity}"
            )

    return errors


def format_solution(routes: list[list[int]]) -> str:
    output = []
    for route in routes:
        output.append("0")
        output.extend(str(customer) for customer in route)
        output.append("0")
    return " ".join(output)


def parse_solution(solution: str) -> list[list[int]]:
    tokens = [int(token) for token in solution.split()]
    routes = []
    idx = 0

    while idx < len(tokens):
        if tokens[idx] != 0:
            raise ValueError("Each route must start with depot 0.")
        idx += 1

        route = []
        while idx < len(tokens) and tokens[idx] != 0:
            route.append(tokens[idx])
            idx += 1

        if idx == len(tokens):
            raise ValueError("Each route must end with depot 0.")
        idx += 1
        routes.append(route)

    return routes


def insert_customer(route: list[int], customer: int, position: int) -> list[int]:
    return route[:position] + [customer] + route[position:]


def remove_customer(route: list[int], position: int) -> list[int]:
    return route[:position] + route[position + 1:]


def best_insertion_in_route(
    instance,
    route: list[int],
    customer: int,
) -> tuple[int, float]:
    best_position = 0
    best_delta = float("inf")

    for position in range(len(route) + 1):
        previous_customer = 0 if position == 0 else route[position - 1]
        next_customer = 0 if position == len(route) else route[position]
        delta = (
            distance(instance, previous_customer, customer)
            + distance(instance, customer, next_customer)
            - distance(instance, previous_customer, next_customer)
        )
        if delta < best_delta:
            best_delta = delta
            best_position = position

    return best_position, best_delta


def best_feasible_insertion(
    instance,
    routes: list[list[int]],
    customer: int,
    candidate_vehicles: list[int] | None = None,
    forbidden_vehicles: set[int] | None = None,
) -> tuple[int, int, float] | None:
    capacities = remaining_capacities(instance, routes)
    vehicles = candidate_vehicles if candidate_vehicles is not None else range(len(routes))
    forbidden_vehicles = forbidden_vehicles or set()
    best = None

    for vehicle in vehicles:
        if vehicle in forbidden_vehicles:
            continue
        if int(instance.demandOfCustomer[customer]) > capacities[vehicle]:
            continue

        position, delta = best_insertion_in_route(instance, routes[vehicle], customer)
        if best is None or delta < best[2]:
            best = (vehicle, position, delta)

    return best


def insert_best_feasible(
    instance,
    routes: list[list[int]],
    customer: int,
    candidate_vehicles: list[int] | None = None,
    forbidden_vehicles: set[int] | None = None,
) -> bool:
    insertion = best_feasible_insertion(
        instance,
        routes,
        customer,
        candidate_vehicles,
        forbidden_vehicles,
    )
    if insertion is None:
        return False

    vehicle, position, _ = insertion
    routes[vehicle] = insert_customer(routes[vehicle], customer, position)
    return True


def two_opt_route(instance, route: list[int]) -> list[int]:
    best_route = route[:]
    best_distance = route_distance(instance, best_route)
    improved = True

    while improved:
        improved = False
        for start in range(len(best_route) - 1):
            for end in range(start + 2, len(best_route) + 1):
                candidate = (
                    best_route[:start]
                    + best_route[start:end][::-1]
                    + best_route[end:]
                )
                candidate_distance = route_distance(instance, candidate)
                if candidate_distance + 1e-9 < best_distance:
                    best_route = candidate
                    best_distance = candidate_distance
                    improved = True
                    break
            if improved:
                break

    return best_route


def two_opt_routes(instance, routes: list[list[int]]) -> list[list[int]]:
    return [two_opt_route(instance, route) for route in routes]


def customer_to_route(routes: list[list[int]]) -> dict[int, int]:
    mapping = {}
    for vehicle, route in enumerate(routes):
        for customer in route:
            mapping[customer] = vehicle
    return mapping


def route_centroid(instance, route: list[int]) -> tuple[float, float]:
    if not route:
        return (
            float(instance.xCoordOfCustomer[0]),
            float(instance.yCoordOfCustomer[0]),
        )

    return (
        sum(float(instance.xCoordOfCustomer[customer]) for customer in route)
        / len(route),
        sum(float(instance.yCoordOfCustomer[customer]) for customer in route)
        / len(route),
    )
