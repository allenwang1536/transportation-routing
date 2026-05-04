#pragma once
#include "../route_utils.hpp"
#include <algorithm>
#include <limits>
#include <unordered_set>

// Build one route per vehicle: start with the farthest-from-depot feasible
// customer, then greedily append the nearest feasible one until full.
// If any customers remain unvisited, fall back to best-fit insertion.
inline Routes buildFarthestNearestSolution(const VRPInstance& inst) {
    Routes routes;
    std::unordered_set<int> unvisited;
    for (int i = 1; i < inst.numCustomers; ++i) unvisited.insert(i);

    for (int veh = 0; veh < inst.numVehicles && !unvisited.empty(); ++veh) {
        std::vector<int> route;
        int remaining = inst.vehicleCapacity;
        int current = 0;

        // First customer: farthest feasible from depot
        int first = -1;
        double bestDist = -1.0;
        for (int c : unvisited) {
            if (inst.demandOfCustomer[c] <= remaining) {
                double d = inst.distance(0, c);
                if (d > bestDist) { bestDist = d; first = c; }
            }
        }
        if (first != -1) {
            route.push_back(first);
            unvisited.erase(first);
            remaining -= inst.demandOfCustomer[first];
            current = first;
        }

        // Subsequent customers: nearest feasible
        while (true) {
            int next = -1;
            double minDist = std::numeric_limits<double>::infinity();
            for (int c : unvisited) {
                if (inst.demandOfCustomer[c] <= remaining) {
                    double d = inst.distance(current, c);
                    if (d < minDist) { minDist = d; next = c; }
                }
            }
            if (next == -1) break;
            route.push_back(next);
            unvisited.erase(next);
            remaining -= inst.demandOfCustomer[next];
            current = next;
        }
        routes.push_back(route);
    }
    return routes;
}

// Assign customers by best-fit: sort by demand desc, then for each customer
// find the vehicle with the tightest remaining capacity that fits, and
// insert at the cheapest position.
inline Routes buildBestFitSolution(const VRPInstance& inst) {
    Routes routes(inst.numVehicles);
    std::unordered_set<int> unvisited;
    for (int i = 1; i < inst.numCustomers; ++i) unvisited.insert(i);

    std::vector<int> ordered(unvisited.begin(), unvisited.end());
    std::sort(ordered.begin(), ordered.end(), [&](int a, int b) {
        if (inst.demandOfCustomer[a] != inst.demandOfCustomer[b])
            return inst.demandOfCustomer[a] > inst.demandOfCustomer[b];
        return inst.distance(0, a) > inst.distance(0, b);
    });

    for (int customer : ordered) {
        auto caps = remainingCapacities(inst, routes);
        std::vector<int> feasible;
        for (int v = 0; v < inst.numVehicles; ++v)
            if (inst.demandOfCustomer[customer] <= caps[v]) feasible.push_back(v);
        if (feasible.empty()) continue;

        auto ins = bestFeasibleInsertion(inst, routes, customer, &feasible);
        if (!ins) continue;
        routes[ins->vehicle] = insertCustomer(routes[ins->vehicle], customer, ins->position);
        unvisited.erase(customer);
    }
    return routes;
}

inline Routes farthestNearestConstruct(const VRPInstance& inst, RNG& /*rng*/) {
    auto [routes, unvisited] = [&]() -> std::pair<Routes, std::unordered_set<int>> {
        auto r = buildFarthestNearestSolution(inst);
        std::unordered_set<int> leftover;
        auto rm = customerToRoute(r);
        for (int i = 1; i < inst.numCustomers; ++i)
            if (!rm.count(i)) leftover.insert(i);
        return {r, leftover};
    }();

    if (!unvisited.empty())
        routes = buildBestFitSolution(inst);

    return twoOptRoutes(inst, normalizeRoutes(routes, inst.numVehicles));
}
