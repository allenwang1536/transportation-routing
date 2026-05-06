#pragma once
#include "../route_utils.hpp"
#include <algorithm>
#include <limits>
#include <optional>
#include <tuple>
#include <vector>

// A bid represents a vehicle's offer to serve a customer at a given insertion
// cost.  bidCost = insertionDelta + capacity_pressure.
struct Bid {
    int vehicle, position;
    double bidCost, insertionDelta;
};

// Penalise vehicles that are already heavily loaded.
inline double capacityPressure(int remainingAfter) {
    if (remainingAfter < 0) return std::numeric_limits<double>::infinity();
    return 0.01 * remainingAfter;
}

// Returns bids for all feasible vehicles, sorted cheapest-first.
inline std::vector<Bid> customerBids(
    const VRPInstance& inst,
    const Routes& routes,
    const std::vector<int>& remainingCaps,
    int customer)
{
    std::vector<Bid> bids;
    int demand = inst.demandOfCustomer[customer];

    for (int v = 0; v < static_cast<int>(routes.size()); ++v) {
        if (demand > remainingCaps[v]) continue;
        auto [pos, delta] = bestInsertionInRoute(inst, routes[v], customer);
        int remainingAfter = remainingCaps[v] - demand;
        double cost = delta + capacityPressure(remainingAfter);
        bids.push_back({v, pos, cost, delta});
    }

    std::sort(bids.begin(), bids.end(), [](const Bid& a, const Bid& b) {
        return a.bidCost < b.bidCost;
    });
    return bids;
}

// Choose the customer whose second-best insertion is most expensive relative
// to its best insertion (highest regret), breaking ties by demand then delta.
// Priority tuple: (regret, demand, insertionDelta, -bidCost) — higher is better.
struct ChoiceResult { int customer, vehicle, position; };

inline std::optional<ChoiceResult> chooseCustomer(
    const VRPInstance& inst,
    const Routes& routes,
    const std::vector<int>& remainingCaps,
    const std::unordered_set<int>& unvisited)
{
    using Priority = std::tuple<double, int, double, double>;
    std::optional<Priority> bestPriority;
    std::optional<ChoiceResult> bestChoice;

    for (int customer : unvisited) {
        auto bids = customerBids(inst, routes, remainingCaps, customer);
        if (bids.empty()) continue;

        const Bid& best = bids[0];
        double secondCost = (bids.size() > 1) ? bids[1].bidCost : best.bidCost + 1'000'000.0;
        double regret = secondCost - best.bidCost;
        Priority priority{regret, inst.demandOfCustomer[customer], best.insertionDelta, -best.bidCost};

        if (!bestPriority || priority > *bestPriority) {
            bestPriority = priority;
            bestChoice = ChoiceResult{customer, best.vehicle, best.position};
        }
    }
    return bestChoice;
}

// Iteratively insert the highest-regret unvisited customer until all are placed.
inline Routes regretBiddingConstruct(const VRPInstance& inst, RNG& /*rng*/) {
    Routes routes(inst.numVehicles);
    std::vector<int> caps(inst.numVehicles, inst.vehicleCapacity);
    std::unordered_set<int> unvisited;
    for (int i = 1; i < inst.numCustomers; ++i) unvisited.insert(i);

    while (!unvisited.empty()) {
        auto choice = chooseCustomer(inst, routes, caps, unvisited);
        if (!choice) break;
        routes[choice->vehicle] = insertCustomer(routes[choice->vehicle], choice->customer, choice->position);
        caps[choice->vehicle] -= inst.demandOfCustomer[choice->customer];
        unvisited.erase(choice->customer);
    }

    return twoOptRoutes(inst, normalizeRoutes(routes, inst.numVehicles));
}
