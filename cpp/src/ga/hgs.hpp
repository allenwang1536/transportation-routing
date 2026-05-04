#pragma once
#include "../constructors/farthest_nearest.hpp"
#include "../constructors/regret_bidding.hpp"
#include "../improvers/relocate_swap.hpp"
#include "../route_utils.hpp"
#include "../shared_state.hpp"
#include "../solver_config.hpp"
#include "crossover.hpp"
#include "population.hpp"
#include <limits>
#include <string>

// ── HGS result ────────────────────────────────────────────────────────────────
struct HGSResult {
    std::string solution;
    double objectiveValue;
    Routes routes;
};

// ── Local search for a freshly constructed / crossed-over individual ─────────
// Applies 2-opt per route (fast) and then a brief relocate/swap pass.
static Routes childLocalSearch(
    const VRPInstance& inst,
    const Routes& routes,
    double subDeadline,
    RNG& rng)
{
    Routes improved = twoOptRoutes(inst, routes);
    SolverConfig cfg;
    cfg.granular = false;
    cfg.tabu     = false;
    return relocateSwapImprove(inst, improved, cfg, rng, subDeadline);
}

// ── Population seeding ────────────────────────────────────────────────────────
// Generates `n` initial individuals: alternates between regret_bidding and
// farthest_nearest constructors to maximise early diversity.
static void seedPopulation(
    Population& pop,
    const VRPInstance& inst,
    int n,
    double deadline,
    RNG& rng)
{
    for (int i = 0; i < n && now() < deadline; ++i) {
        Routes routes = (i % 2 == 0)
            ? regretBiddingConstruct(inst, rng)
            : farthestNearestConstruct(inst, rng);

        double subDeadline = std::min(now() + 0.1, deadline);
        routes = childLocalSearch(inst, routes, subDeadline, rng);

        if (!validateRoutes(inst, routes))
            pop.insert({routes, objective(inst, routes)});
    }
}

// ── Main HGS loop ─────────────────────────────────────────────────────────────
//
// SharedState integration (optional):
//   - Every `publishInterval` improvements the GA publishes its best to state.
//   - Every `injectInterval` generations it pulls the global best from state
//     and calls pop.tryInject() so worker-thread solutions can enter the pool.
inline HGSResult hgsSolve(
    const VRPInstance& inst,
    double timeLimit,
    int seed       = 0,
    int popMin     = 25,
    int popMax     = 50,
    SharedState*   state = nullptr)
{
    RNG rng(seed);
    double deadline = now() + timeLimit;

    Population pop(popMin, popMax, inst.numCustomers);
    seedPopulation(pop, inst, popMin, deadline, rng);

    Routes globalBestRoutes;
    double globalBestObj = std::numeric_limits<double>::infinity();

    // Update global best from seeded population.
    if (!pop.empty()) {
        const Individual& b = pop.best();
        globalBestObj    = b.objective;
        globalBestRoutes = b.routes;
        if (state) state->tryUpdate(globalBestRoutes, globalBestObj);
    }

    int generation      = 0;
    int improvementsSincePublish = 0;
    const int publishInterval = 3;
    const int injectInterval  = 10;

    while (now() < deadline) {
        if (pop.size() < 2) {
            // Population too small to select two distinct parents; seed more.
            double subDeadline = std::min(now() + 0.1, deadline);
            Routes r = regretBiddingConstruct(inst, rng);
            r = childLocalSearch(inst, r, subDeadline, rng);
            if (!validateRoutes(inst, r))
                pop.insert({r, objective(inst, r)});
            ++generation;
            continue;
        }

        // ── Select two distinct parents via tournament selection ──────────────
        int idxA = pop.selectIdx(rng);
        int idxB = idxA;
        for (int attempts = 0; attempts < 10 && idxB == idxA; ++attempts)
            idxB = pop.selectIdx(rng);

        const Individual& parentA = pop[idxA];
        const Individual& parentB = pop[idxB];

        // ── Crossover + local search ──────────────────────────────────────────
        Routes childRoutes = crossover(inst, parentA, parentB, rng);
        double subDeadline = std::min(now() + 0.1, deadline);
        childRoutes = childLocalSearch(inst, childRoutes, subDeadline, rng);

        if (validateRoutes(inst, childRoutes)) { ++generation; continue; }

        double childObj = objective(inst, childRoutes);
        pop.insert({childRoutes, childObj});

        // ── Track and publish global best ─────────────────────────────────────
        if (childObj < globalBestObj) {
            globalBestObj    = childObj;
            globalBestRoutes = childRoutes;
            ++improvementsSincePublish;
            if (state && improvementsSincePublish >= publishInterval) {
                state->tryUpdate(globalBestRoutes, globalBestObj);
                improvementsSincePublish = 0;
            }
        }

        // ── Inject external solutions from worker threads ─────────────────────
        if (state && (generation % injectInterval == 0)) {
            auto [extRoutes, extObj] = state->getBest();
            if (extObj < std::numeric_limits<double>::infinity()) {
                pop.tryInject({extRoutes, extObj});
                // If the external solution is better than our champion, record it.
                if (extObj < globalBestObj) {
                    globalBestObj    = extObj;
                    globalBestRoutes = extRoutes;
                }
            }
        }

        ++generation;
    }

    // Final 2-opt polish on the best individual found.
    if (!globalBestRoutes.empty()) {
        globalBestRoutes = twoOptRoutes(inst, normalizeRoutes(globalBestRoutes, inst.numVehicles));
        globalBestObj    = objective(inst, globalBestRoutes);
    }

    return {formatSolution(globalBestRoutes), globalBestObj, globalBestRoutes};
}
