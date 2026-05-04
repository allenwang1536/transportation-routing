#pragma once
#include "../guidance/granular.hpp"
#include "../guidance/tabu_memory.hpp"
#include "../route_utils.hpp"
#include "../shared_state.hpp"
#include "../solver_config.hpp"
#include <limits>
#include <memory>
#include <optional>

// Represents a three-route chain move: move a customer from source into
// target (evicting one customer there), then place the evicted customer
// into a third rescue route.
struct ChainMove {
    double delta;
    int sourceRoute, sourcePos;
    int targetRoute, targetPos;
    int ejectedPos;
    int rescueRoute, rescuePos;
    int movedCustomer, ejectedCustomer;
};

inline std::optional<ChainMove> findBestChain(
    const VRPInstance& inst,
    const Routes& routes,
    double currentObj,
    double bestObj,
    const GranularNeighborhood* granular,
    TabuMemory* tabu,
    double deadline)
{
    std::optional<ChainMove> bestMove;

    for (int srcR = 0; srcR < static_cast<int>(routes.size()); ++srcR) {
        double oldSrcDist = routeDistance(inst, routes[srcR]);
        int nSrc = static_cast<int>(routes[srcR].size());

        for (int srcPos = 0; srcPos < nSrc; ++srcPos) {
            int movedCustomer = routes[srcR][srcPos];
            auto reducedSrc = removeCustomer(routes[srcR], srcPos);
            double reducedSrcDist = routeDistance(inst, reducedSrc);

            std::vector<int> targetRoutes;
            if (granular) {
                targetRoutes = granular->routesForCustomer(routes, movedCustomer);
            } else {
                targetRoutes.resize(routes.size());
                std::iota(targetRoutes.begin(), targetRoutes.end(), 0);
            }

            for (int tgtR : targetRoutes) {
                if (tgtR == srcR || routes[tgtR].empty()) continue;
                if (now() >= deadline) return bestMove;

                if (tabu && tabu->isTabu(movedCustomer, srcR, tgtR, currentObj < bestObj))
                    continue;

                int targetLoad = routeLoad(inst, routes[tgtR]);
                int movedDemand = inst.demandOfCustomer[movedCustomer];

                // Only do ejection when target is too full to accept directly
                if (targetLoad + movedDemand <= inst.vehicleCapacity) continue;

                int nTgt = static_cast<int>(routes[tgtR].size());
                for (int ejPos = 0; ejPos < nTgt; ++ejPos) {
                    int ejCustomer = routes[tgtR][ejPos];

                    if (granular && !granular->neighbors[movedCustomer].count(ejCustomer))
                        continue;

                    int ejDemand = inst.demandOfCustomer[ejCustomer];
                    if (targetLoad + movedDemand - ejDemand > inst.vehicleCapacity) continue;

                    auto targetWithoutEj = removeCustomer(routes[tgtR], ejPos);
                    auto [tgtInsPos, _tgtDelta] = bestInsertionInRoute(inst, targetWithoutEj, movedCustomer);
                    auto targetAfter = insertCustomer(targetWithoutEj, movedCustomer, tgtInsPos);

                    std::vector<int> rescueRoutes;
                    if (granular) {
                        rescueRoutes = granular->routesForCustomer(routes, ejCustomer);
                    } else {
                        rescueRoutes.resize(routes.size());
                        std::iota(rescueRoutes.begin(), rescueRoutes.end(), 0);
                    }

                    for (int resR : rescueRoutes) {
                        if (resR == srcR || resR == tgtR) continue;
                        if (now() >= deadline) return bestMove;

                        if (tabu && tabu->isTabu(ejCustomer, tgtR, resR, currentObj < bestObj))
                            continue;

                        if (routeLoad(inst, routes[resR]) + ejDemand > inst.vehicleCapacity)
                            continue;

                        auto [resPos, rescueDelta] = bestInsertionInRoute(inst, routes[resR], ejCustomer);
                        double delta = reducedSrcDist - oldSrcDist
                                     + routeDistance(inst, targetAfter) - routeDistance(inst, routes[tgtR])
                                     + rescueDelta;

                        if (!bestMove || delta < bestMove->delta)
                            bestMove = ChainMove{delta,
                                                 srcR, srcPos,
                                                 tgtR, tgtInsPos, ejPos,
                                                 resR, resPos,
                                                 movedCustomer, ejCustomer};
                    }
                }
            }
        }
    }
    return bestMove;
}

inline Routes applyChain(const VRPInstance& inst, Routes routes, const ChainMove& move) {
    int movedCustomer = routes[move.sourceRoute][move.sourcePos];
    routes[move.sourceRoute] = removeCustomer(routes[move.sourceRoute], move.sourcePos);

    int ejectedCustomer = routes[move.targetRoute][move.ejectedPos];
    routes[move.targetRoute] = removeCustomer(routes[move.targetRoute], move.ejectedPos);

    int tgtPos = std::min(move.targetPos, static_cast<int>(routes[move.targetRoute].size()));
    routes[move.targetRoute] = insertCustomer(routes[move.targetRoute], movedCustomer, tgtPos);

    int resPos = std::min(move.rescuePos, static_cast<int>(routes[move.rescueRoute].size()));
    routes[move.rescueRoute] = insertCustomer(routes[move.rescueRoute], ejectedCustomer, resPos);

    for (int v : {move.sourceRoute, move.targetRoute, move.rescueRoute})
        routes[v] = twoOptRoute(inst, routes[v]);

    return routes;
}

// state: publish-only — improvements are emitted immediately so destroy_repair
// threads can benefit.  Reading/restart from global best is handled by the
// outer loop in parallel_solver (greedy descent converges fast, full restarts
// are more useful than mid-run injection).
inline Routes ejectionChainsImprove(
    const VRPInstance& inst,
    const Routes& initialRoutes,
    const SolverConfig& config,
    RNG& /*rng*/,
    double deadline,
    SharedState* state = nullptr)
{
    Routes current = cloneRoutes(initialRoutes);
    double bestObj = objective(inst, current);

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

        double currentObj = objective(inst, current);
        auto move = findBestChain(inst, current, currentObj, bestObj, granular, tabu, deadline);
        if (!move || move->delta >= -1e-9) break;

        current = applyChain(inst, current, *move);
        currentObj = objective(inst, current);
        if (currentObj < bestObj) {
            bestObj = currentObj;
            if (state) state->tryUpdate(current, bestObj); // publish-only
        }

        if (tabu) {
            tabu->forbidReverseMove(move->movedCustomer, move->sourceRoute, move->targetRoute);
            tabu->forbidReverseMove(move->ejectedCustomer, move->targetRoute, move->rescueRoute);
        }
    }
    return current;
}
