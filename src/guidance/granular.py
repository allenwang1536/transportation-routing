from route_utils import customer_to_route, distance


class GranularNeighborhood:
    def __init__(self, instance, neighbor_count: int = 20):
        self.instance = instance
        self.neighbor_count = max(1, neighbor_count)
        self.neighbors = self._build_neighbors()

    def _build_neighbors(self) -> dict[int, set[int]]:
        neighbors = {}
        customers = list(range(1, self.instance.numCustomers))
        for customer in customers:
            ordered = sorted(
                (other for other in customers if other != customer),
                key=lambda other: distance(self.instance, customer, other),
            )
            neighbors[customer] = set(ordered[: self.neighbor_count])
        return neighbors

    def route_is_relevant(
        self,
        customer: int,
        route: list[int],
        allow_empty: bool = True,
    ) -> bool:
        if not route:
            return allow_empty

        nearby = self.neighbors.get(customer, set())
        return any(other in nearby for other in route)

    def routes_for_customer(
        self,
        routes: list[list[int]],
        customer: int,
        include_empty: bool = True,
    ) -> list[int]:
        candidates = [
            vehicle
            for vehicle, route in enumerate(routes)
            if self.route_is_relevant(customer, route, include_empty)
        ]
        return candidates or list(range(len(routes)))

    def customers_near_customer(self, customer: int, candidates: list[int]) -> list[int]:
        nearby = self.neighbors.get(customer, set())
        filtered = [other for other in candidates if other in nearby]
        return filtered or candidates

    def neighboring_route_pairs(self, routes: list[list[int]]) -> set[tuple[int, int]]:
        route_of = customer_to_route(routes)
        pairs = set()
        for customer, route_a in route_of.items():
            for neighbor in self.neighbors.get(customer, set()):
                route_b = route_of.get(neighbor)
                if route_b is None or route_a == route_b:
                    continue
                pairs.add(tuple(sorted((route_a, route_b))))
        return pairs
