#pragma once
#include "constructors/farthest_nearest.hpp"
#include "constructors/regret_bidding.hpp"
#include "improvers/adaptive_destroy_repair.hpp"
#include "improvers/ejection_chains.hpp"
#include "improvers/relocate_swap.hpp"
#include "route_utils.hpp"
#include "shared_state.hpp"
#include "solver_config.hpp"
#include "vrpinstance.hpp"
#include <string>
#include <thread>
#include <vector>

// ── Platform thread-affinity hints ───────────────────────────────────────────
// macOS: THREAD_AFFINITY_POLICY assigns each thread a unique affinity tag so
// the scheduler tends to keep it on a dedicated core.  It is advisory, not a
// hard binding (hard pinning via cpu_set is not available on Darwin).
// Linux: pthread_setaffinity_np does hard-pin to the given core.
#ifdef __APPLE__
#include <mach/mach.h>
#include <mach/thread_policy.h>
inline void pinThreadToCore(int coreId) {
    thread_affinity_policy_data_t policy{coreId + 1}; // tag ≠ 0
    thread_policy_set(mach_thread_self(), THREAD_AFFINITY_POLICY,
                      reinterpret_cast<thread_policy_t>(&policy),
                      THREAD_AFFINITY_POLICY_COUNT);
}
#elif defined(__linux__)
#include <pthread.h>
#include <sched.h>
inline void pinThreadToCore(int coreId) {
    cpu_set_t cpuset;
    CPU_ZERO(&cpuset);
    CPU_SET(coreId, &cpuset);
    pthread_setaffinity_np(pthread_self(), sizeof(cpu_set_t), &cpuset);
}
#else
inline void pinThreadToCore(int) {}
#endif

// ── The four fixed thread configurations ─────────────────────────────────────
inline std::vector<SolverConfig> parallelConfigs(int baseSeed) {
    auto make = [&](const std::string& imp, bool gran, bool tab) {
        SolverConfig c;
        c.constructor = "regret_bidding";
        c.improver    = imp;
        c.granular    = gran;
        c.tabu        = tab;
        c.seed        = baseSeed;
        return c;
    };
    return {
        make("destroy_repair",  true,  false), // thread 0
        make("destroy_repair",  true,  true),  // thread 1
        make("ejection_chains", true,  false), // thread 2
        make("relocate_swap",   false, false), // thread 3
    };
}

// ── Per-thread runner ─────────────────────────────────────────────────────────
// destroy_repair: runs to the deadline with inline bidirectional sharing.
// ejection_chains / relocate_swap: greedy descent — converges fast, so this
//   function restarts the improver from the global best each time it plateaus.
//   The publish-only SharedState hooks emit improvements to other threads
//   immediately even within a single greedy pass.
static void threadRun(
    int threadId,
    const VRPInstance& inst,
    SolverConfig config,
    SharedState& state,
    double deadline)
{
    pinThreadToCore(threadId);

    // Each thread gets a different seed so they explore different trajectories.
    config.seed += threadId * 1'000'003;
    RNG rng(config.seed);

    // ── Initial construction ──────────────────────────────────────────────────
    Routes current = regretBiddingConstruct(inst, rng);
    current = normalizeRoutes(current, inst.numVehicles);
    if (validateRoutes(inst, current))
        current = farthestNearestConstruct(inst, rng);

    state.tryUpdate(current, objective(inst, current));

    // ── Improvement loop ──────────────────────────────────────────────────────
    while (now() < deadline) {
        Routes improved;

        if (config.improver == "destroy_repair") {
            // Runs to deadline internally; inline bidirectional sharing via state.
            improved = adaptiveDestroyRepairImprove(inst, current, config, rng, deadline, &state);
        } else if (config.improver == "ejection_chains") {
            improved = ejectionChainsImprove(inst, current, config, rng, deadline, &state);
        } else {
            improved = relocateSwapImprove(inst, current, config, rng, deadline, &state);
        }

        state.tryUpdate(improved, objective(inst, improved));

        if (now() >= deadline) break;

        // Greedy methods (ejection_chains, relocate_swap) plateau quickly.
        // Restart from the current global best so they benefit from progress
        // made by destroy_repair threads during their run.
        auto [globalBest, globalObj] = state.getBest();
        current = globalBest;
        (void)globalObj;
    }
}

// ── Public API ────────────────────────────────────────────────────────────────
struct ParallelResult {
    std::string solution;
    double objectiveValue;
    Routes routes;
};

inline ParallelResult parallelSolve(
    const VRPInstance& inst,
    double timeLimit,
    int seed = 0,
    int shareThreshold = 3)
{
    SharedState state(shareThreshold);
    double deadline = now() + timeLimit;

    auto configs = parallelConfigs(seed);
    std::vector<std::thread> threads;
    threads.reserve(configs.size());

    for (int i = 0; i < static_cast<int>(configs.size()); ++i)
        threads.emplace_back(threadRun, i, std::cref(inst), configs[i],
                             std::ref(state), deadline);

    for (auto& t : threads) t.join();

    auto [bestRoutes, bestObj] = state.getBest();

    // Final 2-opt polish on the winning solution
    bestRoutes = twoOptRoutes(inst, normalizeRoutes(bestRoutes, inst.numVehicles));
    bestObj    = objective(inst, bestRoutes);

    return {formatSolution(bestRoutes), bestObj, bestRoutes};
}
