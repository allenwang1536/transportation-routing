#pragma once
#include "vrpinstance.hpp"
#include <algorithm>
#include <cassert>
#include <chrono>
#include <cmath>
#include <functional>
#include <limits>
#include <numeric>
#include <optional>
#include <random>
#include <set>
#include <sstream>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

// ── Type aliases ─────────────────────────────────────────────────────────────
using Routes   = std::vector<std::vector<int>>;
using RouteMap = std::unordered_map<int, int>; // customer → vehicle index
using ImprovementCallback = std::function<void(const Routes&, double)>;

// ── Monotonic clock (mirrors Python's time.perf_counter) ─────────────────────
inline double now() {
    static const auto epoch = std::chrono::steady_clock::now();
    return std::chrono::duration<double>(std::chrono::steady_clock::now() - epoch).count();
}

// ── RNG wrapper (mirrors Python's random.Random) ─────────────────────────────
struct RNG {
    std::mt19937 gen;

    explicit RNG(int seed) : gen(static_cast<unsigned>(seed)) {}

    double random() {
        return std::uniform_real_distribution<double>(0.0, 1.0)(gen);
    }

    int choice(const std::vector<int>& v) {
        return v[std::uniform_int_distribution<int>(0, static_cast<int>(v.size()) - 1)(gen)];
    }

    // Returns k unique elements drawn without replacement (Fisher-Yates partial shuffle).
    std::vector<int> sample(const std::vector<int>& population, int k) {
        std::vector<int> copy = population;
        k = std::min(k, static_cast<int>(copy.size()));
        for (int i = 0; i < k; ++i) {
            int j = std::uniform_int_distribution<int>(i, static_cast<int>(copy.size()) - 1)(gen);
            std::swap(copy[i], copy[j]);
        }
        return std::vector<int>(copy.begin(), copy.begin() + k);
    }
};

// ── Basic route operations ────────────────────────────────────────────────────
inline Routes cloneRoutes(const Routes& routes) {
    return routes; // vector copy
}

inline std::vector<int> insertCustomer(const std::vector<int>& route, int customer, int position) {
    std::vector<int> result;
    result.reserve(route.size() + 1);
    result.insert(result.end(), route.begin(), route.begin() + position);
    result.push_back(customer);
    result.insert(result.end(), route.begin() + position, route.end());
    return result;
}

inline std::vector<int> removeCustomer(const std::vector<int>& route, int position) {
    std::vector<int> result;
    result.reserve(route.size() - 1);
    result.insert(result.end(), route.begin(), route.begin() + position);
    result.insert(result.end(), route.begin() + position + 1, route.end());
    return result;
}

// ── Distance and objective ────────────────────────────────────────────────────
inline double routeDistance(const VRPInstance& inst, const std::vector<int>& route) {
    if (route.empty()) return 0.0;
    double total = inst.distance(0, route[0]);
    for (int i = 0; i + 1 < static_cast<int>(route.size()); ++i)
        total += inst.distance(route[i], route[i + 1]);
    total += inst.distance(route.back(), 0);
    return total;
}

inline double objective(const VRPInstance& inst, const Routes& routes) {
    double total = 0.0;
    for (const auto& r : routes) total += routeDistance(inst, r);
    return std::round(total * 100.0) / 100.0;
}

inline double angleFromDepot(const VRPInstance& inst, int customer) {
    return std::atan2(inst.yCoordOfCustomer[customer] - inst.yCoordOfCustomer[0],
                      inst.xCoordOfCustomer[customer] - inst.xCoordOfCustomer[0]);
}

// ── Capacity helpers ──────────────────────────────────────────────────────────
inline int routeLoad(const VRPInstance& inst, const std::vector<int>& route) {
    int load = 0;
    for (int c : route) load += inst.demandOfCustomer[c];
    return load;
}

inline std::vector<int> routeLoads(const VRPInstance& inst, const Routes& routes) {
    std::vector<int> loads;
    loads.reserve(routes.size());
    for (const auto& r : routes) loads.push_back(routeLoad(inst, r));
    return loads;
}

inline std::vector<int> remainingCapacities(const VRPInstance& inst, const Routes& routes) {
    std::vector<int> caps;
    caps.reserve(routes.size());
    for (const auto& r : routes) caps.push_back(inst.vehicleCapacity - routeLoad(inst, r));
    return caps;
}

// ── Route normalization ───────────────────────────────────────────────────────
inline Routes normalizeRoutes(Routes routes, int numRoutes) {
    if (static_cast<int>(routes.size()) > numRoutes)
        routes.resize(numRoutes);
    while (static_cast<int>(routes.size()) < numRoutes)
        routes.push_back({});
    return routes;
}

// ── Validation ────────────────────────────────────────────────────────────────
// Returns true if there are errors (mirrors Python's truthy non-empty list).
inline bool validateRoutes(const VRPInstance& inst, const Routes& routes) {
    Routes normalized = normalizeRoutes(routes, inst.numVehicles);

    std::vector<int> seen;
    for (const auto& r : normalized)
        for (int c : r) seen.push_back(c);

    std::unordered_set<int> expected;
    for (int i = 1; i < inst.numCustomers; ++i) expected.insert(i);

    std::unordered_set<int> seenSet(seen.begin(), seen.end());
    if (seenSet != expected) return true;

    // Check duplicates
    std::unordered_map<int, int> counts;
    for (int c : seen) ++counts[c];
    for (const auto& [c, cnt] : counts)
        if (cnt > 1) return true;

    // Check capacity
    for (const auto& r : normalized)
        if (routeLoad(inst, r) > inst.vehicleCapacity) return true;

    return false;
}

// ── Solution formatting ───────────────────────────────────────────────────────
inline std::string formatSolution(const Routes& routes) {
    std::ostringstream oss;
    bool first = true;
    for (const auto& route : routes) {
        if (!first) oss << " ";
        oss << "0";
        for (int c : route) oss << " " << c;
        oss << " 0";
        first = false;
    }
    return oss.str();
}

// ── Customer → vehicle mapping ────────────────────────────────────────────────
inline RouteMap customerToRoute(const Routes& routes) {
    RouteMap mapping;
    for (int v = 0; v < static_cast<int>(routes.size()); ++v)
        for (int c : routes[v]) mapping[c] = v;
    return mapping;
}

// ── Insertion helpers ─────────────────────────────────────────────────────────
inline std::pair<int, double> bestInsertionInRoute(
    const VRPInstance& inst, const std::vector<int>& route, int customer)
{
    int bestPos = 0;
    double bestDelta = std::numeric_limits<double>::infinity();
    int n = static_cast<int>(route.size());

    for (int pos = 0; pos <= n; ++pos) {
        int prev = (pos == 0) ? 0 : route[pos - 1];
        int next = (pos == n) ? 0 : route[pos];
        double delta = inst.distance(prev, customer)
                     + inst.distance(customer, next)
                     - inst.distance(prev, next);
        if (delta < bestDelta) {
            bestDelta = delta;
            bestPos = pos;
        }
    }
    return {bestPos, bestDelta};
}

struct Insertion {
    int vehicle, position;
    double delta;
};

inline std::optional<Insertion> bestFeasibleInsertion(
    const VRPInstance& inst,
    const Routes& routes,
    int customer,
    const std::vector<int>* candidateVehicles = nullptr,
    const std::unordered_set<int>* forbiddenVehicles = nullptr)
{
    auto caps = remainingCapacities(inst, routes);
    int demand = inst.demandOfCustomer[customer];
    std::optional<Insertion> best;
    int nv = static_cast<int>(routes.size());

    std::vector<int> vehicles;
    if (candidateVehicles) {
        vehicles = *candidateVehicles;
    } else {
        vehicles.resize(nv);
        std::iota(vehicles.begin(), vehicles.end(), 0);
    }

    for (int v : vehicles) {
        if (forbiddenVehicles && forbiddenVehicles->count(v)) continue;
        if (demand > caps[v]) continue;
        auto [pos, delta] = bestInsertionInRoute(inst, routes[v], customer);
        if (!best || delta < best->delta)
            best = Insertion{v, pos, delta};
    }
    return best;
}

inline bool insertBestFeasible(
    const VRPInstance& inst,
    Routes& routes,
    int customer,
    const std::vector<int>* candidateVehicles = nullptr,
    const std::unordered_set<int>* forbiddenVehicles = nullptr)
{
    auto ins = bestFeasibleInsertion(inst, routes, customer, candidateVehicles, forbiddenVehicles);
    if (!ins) return false;
    routes[ins->vehicle] = insertCustomer(routes[ins->vehicle], customer, ins->position);
    return true;
}

// ── 2-opt ─────────────────────────────────────────────────────────────────────
inline std::vector<int> twoOptRoute(const VRPInstance& inst, const std::vector<int>& route) {
    if (route.size() < 2) return route;
    std::vector<int> best = route;
    double bestDist = routeDistance(inst, best);
    bool improved = true;

    while (improved) {
        improved = false;
        int n = static_cast<int>(best.size());
        for (int i = 0; i < n - 1 && !improved; ++i) {
            for (int j = i + 2; j <= n; ++j) {
                std::vector<int> candidate = best;
                std::reverse(candidate.begin() + i, candidate.begin() + j);
                double d = routeDistance(inst, candidate);
                if (d + 1e-9 < bestDist) {
                    best = candidate;
                    bestDist = d;
                    improved = true;
                    break;
                }
            }
        }
    }
    return best;
}

inline Routes twoOptRoutes(const VRPInstance& inst, const Routes& routes) {
    Routes result;
    result.reserve(routes.size());
    for (const auto& r : routes) result.push_back(twoOptRoute(inst, r));
    return result;
}

// ── Route centroid ────────────────────────────────────────────────────────────
inline std::pair<double, double> routeCentroid(const VRPInstance& inst, const std::vector<int>& route) {
    if (route.empty())
        return {inst.xCoordOfCustomer[0], inst.yCoordOfCustomer[0]};
    double sx = 0.0, sy = 0.0;
    for (int c : route) {
        sx += inst.xCoordOfCustomer[c];
        sy += inst.yCoordOfCustomer[c];
    }
    double n = static_cast<double>(route.size());
    return {sx / n, sy / n};
}
