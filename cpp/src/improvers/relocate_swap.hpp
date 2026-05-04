#pragma once
#include "../guidance/granular.hpp"
#include "../guidance/tabu_memory.hpp"
#include "../route_utils.hpp"
#include "../shared_state.hpp"
#include "../solver_config.hpp"
#include <algorithm>
#include <limits>
#include <optional>
#include <string>

// A single inter-route move: either relocate a customer or swap two customers.
struct Move {
    std::string kind; // "relocate" or "swap"
    double delta;
    int routeA, posA;
    int routeB, posB;
    int customerA;
    int customerB = -1; // used only for "swap"
};

inline std::optional<Move> findBestMove(
    const VRPInstance& inst,
    const Routes& routes,
    double currentObj,
    double bestObj,
    const GranularNeighborhood* granular,
    TabuMemory* tabu,
    double deadline)
{
    std::optional<Move> bestMove;
    int checks = 0;

    // ── Relocate pass ─────────────────────────────────────────────────────────
    for (int routeA = 0; routeA < static_cast<int>(routes.size()); ++routeA) {
        double oldA = routeDistance(inst, routes[routeA]);
        int nA = static_cast<int>(routes[routeA].size());

        for (int posA = 0; posA < nA; ++posA) {
            int customer = routes[routeA][posA];
            auto reduced = removeCustomer(routes[routeA], posA);
            double newADist = routeDistance(inst, reduced);

            std::vector<int> targetRoutes;
            if (granular) {
                targetRoutes = granular->routesForCustomer(routes, customer);
            } else {
                targetRoutes.resize(routes.size());
                std::iota(targetRoutes.begin(), targetRoutes.end(), 0);
            }

            for (int routeB : targetRoutes) {
                if (routeA == routeB) continue;
                if (now() >= deadline) return bestMove;

                if (routeLoad(inst, routes[routeB]) + inst.demandOfCustomer[customer]
                    > inst.vehicleCapacity)
                    continue;

                auto [pos, insertDelta] = bestInsertionInRoute(inst, routes[routeB], customer);
                double delta = newADist - oldA + insertDelta;
                bool aspiration = currentObj + delta < bestObj;
                if (tabu && tabu->isTabu(customer, routeA, routeB, aspiration)) continue;

                if (!bestMove || delta < bestMove->delta)
                    bestMove = Move{"relocate", delta, routeA, posA, routeB, pos, customer};
            }

            ++checks;
            if (checks % 500 == 0 && now() >= deadline) return bestMove;
        }
    }

    // ── Swap pass ─────────────────────────────────────────────────────────────
    int nv = static_cast<int>(routes.size());
    for (int routeA = 0; routeA < nv; ++routeA) {
        for (int routeB = routeA + 1; routeB < nv; ++routeB) {
            if (granular) {
                auto pairs = granular->neighboringRoutePairs(routes);
                if (!pairs.count({routeA, routeB})) continue;
            }

            double oldDist = routeDistance(inst, routes[routeA])
                           + routeDistance(inst, routes[routeB]);
            int loadA = routeLoad(inst, routes[routeA]);
            int loadB = routeLoad(inst, routes[routeB]);

            for (int posA = 0; posA < static_cast<int>(routes[routeA].size()); ++posA) {
                for (int posB = 0; posB < static_cast<int>(routes[routeB].size()); ++posB) {
                    if (now() >= deadline) return bestMove;

                    int cA = routes[routeA][posA];
                    int cB = routes[routeB][posB];

                    if (granular && !granular->neighbors[cA].count(cB)) continue;

                    int dA = inst.demandOfCustomer[cA];
                    int dB = inst.demandOfCustomer[cB];
                    if (loadA - dA + dB > inst.vehicleCapacity) continue;
                    if (loadB - dB + dA > inst.vehicleCapacity) continue;

                    std::vector<int> newRouteA = routes[routeA];
                    std::vector<int> newRouteB = routes[routeB];
                    newRouteA[posA] = cB;
                    newRouteB[posB] = cA;
                    double delta = routeDistance(inst, newRouteA)
                                 + routeDistance(inst, newRouteB)
                                 - oldDist;

                    bool aspiration = currentObj + delta < bestObj;
                    if (tabu && (tabu->isTabu(cA, routeA, routeB, aspiration)
                              || tabu->isTabu(cB, routeB, routeA, aspiration)))
                        continue;

                    if (!bestMove || delta < bestMove->delta)
                        bestMove = Move{"swap", delta, routeA, posA, routeB, posB, cA, cB};
                }
            }
        }
    }
    return bestMove;
}

inline Routes applyMove(const VRPInstance& inst, Routes routes, const Move& move) {
    if (move.kind == "relocate") {
        int customer = routes[move.routeA][move.posA];
        routes[move.routeA] = removeCustomer(routes[move.routeA], move.posA);
        routes[move.routeB] = insertCustomer(routes[move.routeB], customer, move.posB);
    } else {
        routes[move.routeA][move.posA] = move.customerB;
        routes[move.routeB][move.posB] = move.customerA;
    }
    routes[move.routeA] = twoOptRoute(inst, routes[move.routeA]);
    routes[move.routeB] = twoOptRoute(inst, routes[move.routeB]);
    return routes;
}

// state: publish-only (same rationale as ejection_chains).
inline Routes relocateSwapImprove(
    const VRPInstance& inst,
    const Routes& initialRoutes,
    const SolverConfig& config,
    RNG& /*rng*/,
    double deadline,
    SharedState* state = nullptr)
{
    Routes current = cloneRoutes(initialRoutes);
    double bestObj = objective(inst, current);

    GranularNeighborhood* granular = nullptr;
    TabuMemory* tabu = nullptr;
    std::unique_ptr<GranularNeighborhood> granularOwner;
    std::unique_ptr<TabuMemory> tabuOwner;

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

        double currentObj = objective(inst, current);
        auto move = findBestMove(inst, current, currentObj, bestObj, granular, tabu, deadline);
        if (!move || move->delta >= -1e-9) break;

        current = applyMove(inst, current, *move);
        currentObj = objective(inst, current);
        if (currentObj < bestObj) {
            bestObj = currentObj;
            if (state) state->tryUpdate(current, bestObj); // publish-only
        }

        if (tabu) {
            if (move->kind == "relocate")
                tabu->forbidReverseMove(move->customerA, move->routeA, move->routeB);
            else {
                tabu->forbidReverseMove(move->customerA, move->routeA, move->routeB);
                tabu->forbidReverseMove(move->customerB, move->routeB, move->routeA);
            }
        }
    }
    return current;
}
