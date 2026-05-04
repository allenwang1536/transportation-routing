#pragma once
#include "farthest_nearest.hpp"
#include "../route_utils.hpp"
#include <algorithm>

// Sort customers by polar angle from depot (sweep line), assign greedily to
// vehicles in angle order.  Falls back to best-fit if any customer is left
// unassigned.
inline Routes sweepConstruct(const VRPInstance& inst, RNG& /*rng*/) {
    Routes routes(inst.numVehicles);
    std::vector<int> remaining(inst.numVehicles, inst.vehicleCapacity);
    std::unordered_set<int> unvisited;

    std::vector<int> customers;
    for (int i = 1; i < inst.numCustomers; ++i) customers.push_back(i);
    std::sort(customers.begin(), customers.end(), [&](int a, int b) {
        double angA = angleFromDepot(inst, a);
        double angB = angleFromDepot(inst, b);
        if (angA != angB) return angA < angB;
        return inst.demandOfCustomer[a] > inst.demandOfCustomer[b];
    });

    for (int c : customers) unvisited.insert(c);

    int vehicle = 0;
    for (int customer : customers) {
        int demand = inst.demandOfCustomer[customer];
        while (vehicle < inst.numVehicles && demand > remaining[vehicle]) ++vehicle;
        if (vehicle >= inst.numVehicles) break;

        std::vector<int> single = {vehicle};
        auto ins = bestFeasibleInsertion(inst, routes, customer, &single);
        if (!ins) break;

        routes[ins->vehicle] = insertCustomer(routes[ins->vehicle], customer, ins->position);
        remaining[vehicle] -= demand;
        unvisited.erase(customer);
    }

    if (!unvisited.empty() || validateRoutes(inst, routes))
        routes = buildBestFitSolution(inst);

    return twoOptRoutes(inst, normalizeRoutes(routes, inst.numVehicles));
}
