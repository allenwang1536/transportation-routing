import numpy as np
from math import sqrt

class VRPInstance:
    numCustomers: int  # the number of customers
    numVehicles: int  # the number of vehicles
    vehicleCapacity: int  # the capacity of the vehicles
    demandOfCustomer: np.ndarray  # the demand of each customer
    xCoordOfCustomer: np.ndarray  # the x coordinate of each customer
    yCoordOfCustomer: np.ndarray  # the y coordinate of each customer

    def __init__(self, filename: str):
        self.load_from_file(filename)
        self.solution = None
        self.objective_value = 0

    def solve(self):
        routes, unvisited = self.build_farthest_nearest_solution()

        if unvisited:
            routes, unvisited = self.build_best_fit_solution()

        routes = [self.two_opt(route) for route in routes]
        self.solution = self.format_solution(routes)
        self.objective_value = round(
            sum(self.route_distance(route) for route in routes), 2
        )

        return self.solution, self.objective_value

    def build_farthest_nearest_solution(self) -> tuple[list[list[int]], set[int]]:
        routes = []
        unvisited = set(range(1, self.numCustomers))

        for _ in range(self.numVehicles):
            route = []
            remaining_capacity = self.vehicleCapacity
            current_location = 0

            feasible_customers = [
                customer
                for customer in unvisited
                if self.demandOfCustomer[customer] <= remaining_capacity
            ]

            if feasible_customers:
                first_customer = max(
                    feasible_customers,
                    key=lambda customer: self.distance(0, customer),
                )
                route.append(first_customer)
                unvisited.remove(first_customer)
                remaining_capacity -= self.demandOfCustomer[first_customer]
                current_location = first_customer

            while True:
                feasible_customers = [
                    customer
                    for customer in unvisited
                    if self.demandOfCustomer[customer] <= remaining_capacity
                ]
                if not feasible_customers:
                    break

                next_customer = min(
                    feasible_customers,
                    key=lambda customer: self.distance(current_location, customer),
                )
                route.append(next_customer)
                unvisited.remove(next_customer)
                remaining_capacity -= self.demandOfCustomer[next_customer]
                current_location = next_customer

            routes.append(route)

        return routes, unvisited

    def build_best_fit_solution(self) -> tuple[list[list[int]], set[int]]:
        routes = [[] for _ in range(self.numVehicles)]
        remaining_capacities = [self.vehicleCapacity for _ in range(self.numVehicles)]
        unvisited = set(range(1, self.numCustomers))
        ordered_customers = sorted(
            unvisited,
            key=lambda customer: (
                -self.demandOfCustomer[customer],
                -self.distance(0, customer),
            ),
        )

        for customer in ordered_customers:
            feasible_vehicles = [
                vehicle
                for vehicle in range(self.numVehicles)
                if self.demandOfCustomer[customer] <= remaining_capacities[vehicle]
            ]
            if not feasible_vehicles:
                continue

            vehicle = min(
                feasible_vehicles,
                key=lambda candidate: (
                    remaining_capacities[candidate] - self.demandOfCustomer[customer],
                    self.cheapest_insertion_cost(routes[candidate], customer),
                ),
            )
            routes[vehicle] = self.insert_customer_nearest(routes[vehicle], customer)
            remaining_capacities[vehicle] -= self.demandOfCustomer[customer]
            unvisited.remove(customer)

        return routes, unvisited

    def insert_customer_nearest(self, route: list[int], customer: int) -> list[int]:
        if not route:
            return [customer]

        best_position = 0
        best_cost = float("inf")
        for position in range(len(route) + 1):
            candidate = route[:position] + [customer] + route[position:]
            cost = self.route_distance(candidate)
            if cost < best_cost:
                best_position = position
                best_cost = cost

        return route[:best_position] + [customer] + route[best_position:]

    def cheapest_insertion_cost(self, route: list[int], customer: int) -> float:
        current_distance = self.route_distance(route)
        return (
            self.route_distance(self.insert_customer_nearest(route, customer))
            - current_distance
        )

    def distance(self, i: int, j: int) -> float:
        x_diff = self.xCoordOfCustomer[i] - self.xCoordOfCustomer[j]
        y_diff = self.yCoordOfCustomer[i] - self.yCoordOfCustomer[j]
        return sqrt(x_diff * x_diff + y_diff * y_diff)

    def route_distance(self, route: list[int]) -> float:
        if not route:
            return 0.0

        total_distance = self.distance(0, route[0])
        for i in range(len(route) - 1):
            total_distance += self.distance(route[i], route[i + 1])
        total_distance += self.distance(route[-1], 0)
        return total_distance

    def two_opt(self, route: list[int]) -> list[int]:
        best_route = route[:]
        best_distance = self.route_distance(best_route)
        improved = True

        while improved:
            improved = False
            for i in range(len(best_route) - 1):
                for j in range(i + 2, len(best_route) + 1):
                    candidate = best_route[:i] + best_route[i:j][::-1] + best_route[j:]
                    candidate_distance = self.route_distance(candidate)
                    if candidate_distance + 1e-9 < best_distance:
                        best_route = candidate
                        best_distance = candidate_distance
                        improved = True
                        break
                if improved:
                    break

        return best_route

    def format_solution(self, routes: list[list[int]]) -> str:
        output = []
        for route in routes:
            output.append("0")
            output.extend(str(customer) for customer in route)
            output.append("0")
        return " ".join(output)

    def load_from_file(self, filename: str):
        # Note from Taj: print feel free to remove print statements
        try:
            with open(filename, 'r') as f:
                # Read all numbers from the file
                content = f.read().split()
                iterator = iter(content)

                self.numCustomers = int(next(iterator))
                self.numVehicles = int(next(iterator))
                self.vehicleCapacity = int(next(iterator))

                print(f"Number of customers: {self.numCustomers}")
                print(f"Number of vehicles: {self.numVehicles}")
                print(f"Vehicle capacity: {self.vehicleCapacity}")

                self.demandOfCustomer = np.zeros(self.numCustomers, dtype=int)
                self.xCoordOfCustomer = np.zeros(self.numCustomers)
                self.yCoordOfCustomer = np.zeros(self.numCustomers)

                for i in range(self.numCustomers):
                    self.demandOfCustomer[i] = int(next(iterator))
                    self.xCoordOfCustomer[i] = float(next(iterator))
                    self.yCoordOfCustomer[i] = float(next(iterator))

                for i in range(self.numCustomers):
                    print(f"{self.demandOfCustomer[i]} {self.xCoordOfCustomer[i]} {self.yCoordOfCustomer[i]}")
        except Exception as e:
            print(f"Error reading instance file: {e}")
            exit(1)

    def __str__(self):
        out = f"Number of customers: {self.numCustomers}\n"
        out += f"Number of vehicles: {self.numVehicles}\n"
        out += f"Vehicle capacity: {self.vehicleCapacity}\n"
        for i in range(self.numCustomers):
            out += f"{self.demandOfCustomer[i]} {self.xCoordOfCustomer[i]} {self.yCoordOfCustomer[i]}\n"
        return out
