#pragma once
#include "../guidance/granular.hpp"
#include "../guidance/tabu_memory.hpp"
#include "../route_utils.hpp"
#include "../shared_state.hpp"
#include "../solver_config.hpp"
#include <algorithm>
#include <cmath>
#include <limits>
#include <memory>
#include <optional>
#include <string>
#include <tuple>
#include <unordered_map>
#include <vector>

// ── Operator names kept as constants for clarity ──────────────────────────────
static const std::vector<std::string> DESTROY_OPERATORS = {"random", "worst", "related", "route"};

// ── Operator selection (roulette wheel weighted by reward history) ────────────
inline std::string chooseOperator(
    const std::unordered_map<std::string, double>& weights, RNG& rng)
{
    double total = 0.0;
    for (const auto& op : DESTROY_OPERATORS) total += std::max(0.01, weights.at(op));
    double threshold = rng.random() * total;
    double cumulative = 0.0;
    for (const auto& op : DESTROY_OPERATORS) {
        cumulative += std::max(0.01, weights.at(op));
        if (cumulative >= threshold) return op;
    }
    return DESTROY_OPERATORS.back();
}

// ── Destroy heuristics ────────────────────────────────────────────────────────
inline std::vector<int> worstCustomers(
    const VRPInstance& inst, const Routes& routes, int count)
{
    std::vector<std::pair<double, int>> scored;
    for (const auto& route : routes) {
        std::vector<int> padded = {0};
        padded.insert(padded.end(), route.begin(), route.end());
        padded.push_back(0);
        for (int idx = 1; idx < static_cast<int>(padded.size()) - 1; ++idx) {
            int c = padded[idx];
            double marginal = inst.distance(padded[idx - 1], c)
                            + inst.distance(c, padded[idx + 1])
                            - inst.distance(padded[idx - 1], padded[idx + 1]);
            scored.push_back({marginal, c});
        }
    }
    std::sort(scored.begin(), scored.end(), [](const auto& a, const auto& b) {
        return a.first > b.first;
    });
    std::vector<int> result;
    int take = std::min(count, static_cast<int>(scored.size()));
    for (int i = 0; i < take; ++i) result.push_back(scored[i].second);
    return result;
}

inline std::vector<int> relatedCustomers(
    const VRPInstance& inst, const Routes& routes, int count, RNG& rng)
{
    std::vector<int> customers;
    for (const auto& r : routes)
        for (int c : r) customers.push_back(c);
    if (customers.empty()) return {};

    int seed = rng.choice(customers);
    std::sort(customers.begin(), customers.end(), [&](int a, int b) {
        return inst.distance(seed, a) < inst.distance(seed, b);
    });
    customers.resize(std::min(count, static_cast<int>(customers.size())));
    return customers;
}

inline std::vector<int> routeCustomers(
    const VRPInstance& inst, const Routes& routes, int count)
{
    std::vector<const std::vector<int>*> sortedRoutes;
    for (const auto& r : routes) sortedRoutes.push_back(&r);
    std::sort(sortedRoutes.begin(), sortedRoutes.end(), [&](const auto* a, const auto* b) {
        return routeDistance(inst, *a) > routeDistance(inst, *b);
    });
    std::vector<int> removed;
    for (const auto* r : sortedRoutes) {
        for (int c : *r) {
            removed.push_back(c);
            if (static_cast<int>(removed.size()) >= count) return removed;
        }
    }
    return removed;
}

struct DestroyResult {
    Routes partial;
    std::vector<int> removed;
    RouteMap originalRoutes;
};

inline DestroyResult destroy(
    const VRPInstance& inst, const Routes& routes,
    const std::string& op, double fraction, RNG& rng)
{
    int count = std::max(1, static_cast<int>((inst.numCustomers - 1) * fraction));
    count = std::min(count, inst.numCustomers - 1);

    std::vector<int> removed;
    if (op == "worst") {
        removed = worstCustomers(inst, routes, count);
    } else if (op == "related") {
        removed = relatedCustomers(inst, routes, count, rng);
    } else if (op == "route") {
        removed = routeCustomers(inst, routes, count);
    } else { // "random"
        std::vector<int> all;
        for (const auto& r : routes) for (int c : r) all.push_back(c);
        removed = rng.sample(all, std::min(count, static_cast<int>(all.size())));
    }

    RouteMap originalRoutes = customerToRoute(routes);
    std::unordered_set<int> removeSet(removed.begin(), removed.end());
    Routes partial = cloneRoutes(routes);
    for (auto& r : partial) {
        std::vector<int> filtered;
        for (int c : r) if (!removeSet.count(c)) filtered.push_back(c);
        r = filtered;
    }
    return {partial, removed, originalRoutes};
}

// ── Repair: greedily re-insert removed customers using regret heuristic ───────
struct RepairChoice { int customer, vehicle, position; };

inline std::optional<RepairChoice> chooseRepairCustomer(
    const VRPInstance& inst,
    const Routes& routes,
    const std::unordered_set<int>& remaining,
    const RouteMap& originalRoutes,
    const GranularNeighborhood* granular,
    TabuMemory* tabu)
{
    using Priority = std::tuple<double, int, double>;
    std::optional<Priority> bestPriority;
    std::optional<RepairChoice> bestChoice;

    for (int customer : remaining) {
        std::vector<int> candidateVehicles;
        if (granular) {
            candidateVehicles = granular->routesForCustomer(routes, customer);
        } else {
            candidateVehicles.resize(routes.size());
            std::iota(candidateVehicles.begin(), candidateVehicles.end(), 0);
        }

        std::vector<Insertion> bids;
        for (int v : candidateVehicles) {
            int original = -1;
            auto it = originalRoutes.find(customer);
            if (it != originalRoutes.end()) original = it->second;
            if (tabu && tabu->isTabu(customer, original, v)) continue;
            std::vector<int> single = {v};
            auto ins = bestFeasibleInsertion(inst, routes, customer, &single);
            if (ins) bids.push_back(*ins);
        }

        // Aspiration: retry without tabu if all moves were blocked
        if (bids.empty() && tabu) {
            for (int v : candidateVehicles) {
                std::vector<int> single = {v};
                auto ins = bestFeasibleInsertion(inst, routes, customer, &single);
                if (ins) bids.push_back(*ins);
            }
        }
        if (bids.empty()) continue;

        std::sort(bids.begin(), bids.end(), [](const Insertion& a, const Insertion& b) {
            return a.delta < b.delta;
        });
        const Insertion& best = bids[0];
        double secondDelta = (bids.size() > 1) ? bids[1].delta : best.delta + 1'000'000.0;
        double regret = secondDelta - best.delta;
        Priority priority{regret, inst.demandOfCustomer[customer], -best.delta};

        if (!bestPriority || priority > *bestPriority) {
            bestPriority = priority;
            bestChoice = RepairChoice{customer, best.vehicle, best.position};
        }
    }
    return bestChoice;
}

inline std::optional<Routes> repair(
    const VRPInstance& inst,
    const Routes& partialRoutes,
    const std::vector<int>& removed,
    const RouteMap& originalRoutes,
    const GranularNeighborhood* granular,
    TabuMemory* tabu)
{
    Routes repaired = cloneRoutes(partialRoutes);
    std::unordered_set<int> remaining(removed.begin(), removed.end());

    while (!remaining.empty()) {
        auto choice = chooseRepairCustomer(inst, repaired, remaining, originalRoutes, granular, tabu);
        if (!choice) return std::nullopt;
        repaired[choice->vehicle] = insertCustomer(repaired[choice->vehicle], choice->customer, choice->position);
        remaining.erase(choice->customer);
    }
    return repaired;
}

// ── Simulated-annealing acceptance criterion ──────────────────────────────────
inline bool shouldAccept(
    double currentObj, double candidateObj, double /*bestObj*/, double /*deadline*/, RNG& rng)
{
    if (candidateObj <= currentObj) return true;
    double temperature = std::max(1e-9, 0.02 * currentObj);
    double probability  = std::exp(-(candidateObj - currentObj) / temperature);
    return rng.random() < probability;
}

// ── Tabu update after a move ──────────────────────────────────────────────────
inline void rememberReassignments(TabuMemory& tabu, const Routes& before, const Routes& after) {
    auto beforeRoute = customerToRoute(before);
    auto afterRoute  = customerToRoute(after);
    for (const auto& [customer, oldVehicle] : beforeRoute) {
        auto it = afterRoute.find(customer);
        if (it != afterRoute.end() && it->second != oldVehicle)
            tabu.forbidReverseMove(customer, oldVehicle, it->second);
    }
}

// ── Main improve loop ─────────────────────────────────────────────────────────
// state: optional shared pool for cooperative parallel search.  When non-null,
//   every shareThreshold personal improvements the thread publishes its best
//   and imports the global best if it's better (bidirectional sharing).
inline Routes adaptiveDestroyRepairImprove(
    const VRPInstance& inst,
    const Routes& initialRoutes,
    const SolverConfig& config,
    RNG& rng,
    double deadline,
    SharedState* state = nullptr,
    const ImprovementCallback* onImprovement = nullptr)
{
    Routes current = cloneRoutes(initialRoutes);
    Routes best    = cloneRoutes(current);
    double currentObj = objective(inst, current);
    double bestObj    = currentObj;
    int improveCount = 0;

    std::unordered_map<std::string, double> weights;
    for (const auto& op : DESTROY_OPERATORS) weights[op] = 1.0;

    std::unique_ptr<GranularNeighborhood> granularOwner;
    std::unique_ptr<TabuMemory> tabuOwner;
    GranularNeighborhood* granular = nullptr;
    TabuMemory* tabu = nullptr;

    if (config.granular) {
        granularOwner = std::make_unique<GranularNeighborhood>(inst, config.neighborCount);
        granular = granularOwner.get();
    }
    if (config.tabu) {
        tabuOwner = std::make_unique<TabuMemory>(config.tabuTenure);
        tabu = tabuOwner.get();
    }

    while (now() < deadline) {
        if (tabu) { tabu->nextIteration(); tabu->prune(); }

        std::string op = chooseOperator(weights, rng);
        auto [partial, removed, origRoutes] = destroy(inst, current, op, config.destroyFraction, rng);
        auto candidate = repair(inst, partial, removed, origRoutes, granular, tabu);

        if (!candidate || validateRoutes(inst, *candidate)) {
            weights[op] *= 0.95;
            continue;
        }

        *candidate = twoOptRoutes(inst, *candidate);
        double candidateObj = objective(inst, *candidate);
        bool accepted = shouldAccept(currentObj, candidateObj, bestObj, deadline, rng);

        if (candidateObj < bestObj) {
            best    = cloneRoutes(*candidate);
            bestObj = candidateObj;
            weights[op] += 5.0;
            accepted = true;

            if (onImprovement)
                (*onImprovement)(best, bestObj);

            // Bidirectional sharing: publish our improvement, then check if
            // another thread found something even better.
            if (state) {
                state->tryUpdate(best, bestObj);
                if (++improveCount >= state->shareThreshold) {
                    improveCount = 0;
                    auto [sharedRoutes, sharedObj] = state->getBest();
                    if (sharedObj < bestObj) {
                        best      = sharedRoutes;
                        bestObj   = sharedObj;
                        current   = sharedRoutes;
                        currentObj = sharedObj;
                    }
                }
            }
        } else if (accepted && candidateObj < currentObj) {
            weights[op] += 1.0;
        } else {
            weights[op] *= 0.98;
        }

        if (accepted) {
            if (tabu) rememberReassignments(*tabu, current, *candidate);
            current    = *candidate;
            currentObj = candidateObj;
        }
    }
    return best;
}
