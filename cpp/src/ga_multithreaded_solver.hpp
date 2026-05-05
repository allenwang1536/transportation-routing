#pragma once
#include "constructors/farthest_nearest.hpp"
#include "constructors/regret_bidding.hpp"
#include "ga/crossover.hpp"
#include "ga/population.hpp"
#include "improvers/adaptive_destroy_repair.hpp"
#include "improvers/ejection_chains.hpp"
#include "improvers/relocate_swap.hpp"
#include "route_utils.hpp"
#include "solver_config.hpp"
#include "vrpinstance.hpp"
#include <algorithm>
#include <atomic>
#include <cmath>
#include <limits>
#include <memory>
#include <mutex>
#include <optional>
#include <string>
#include <thread>
#include <unordered_set>
#include <vector>

#ifdef __APPLE__
#include <mach/mach.h>
#include <mach/thread_policy.h>
inline void pinGaMtThreadToCore(int coreId) {
    thread_affinity_policy_data_t policy{coreId + 1};
    thread_policy_set(mach_thread_self(), THREAD_AFFINITY_POLICY,
                      reinterpret_cast<thread_policy_t>(&policy),
                      THREAD_AFFINITY_POLICY_COUNT);
}
#elif defined(__linux__)
#include <pthread.h>
#include <sched.h>
inline void pinGaMtThreadToCore(int coreId) {
    cpu_set_t cpuset;
    CPU_ZERO(&cpuset);
    CPU_SET(coreId, &cpuset);
    pthread_setaffinity_np(pthread_self(), sizeof(cpu_set_t), &cpuset);
}
#else
inline void pinGaMtThreadToCore(int) {}
#endif

enum class GaMtModel {
    Independent,
    OneWay,
    Bidirectional,
};

enum class PoolInsertSource {
    Seed,
    Child,
    Migrant,
};

struct GaMtStats {
    int poolSize = 0;
    long acceptedSeeds = 0;
    long rejectedSeeds = 0;
    long acceptedChildren = 0;
    long rejectedChildren = 0;
    long acceptedMigrants = 0;
    long rejectedMigrants = 0;
    long pullsAttempted = 0;
    long pullsAccepted = 0;
};

class SharedGAPool {
public:
    SharedGAPool(int minSize, int maxSize, int numCustomers, double tau)
        : population_(minSize, maxSize, numCustomers), tau_(tau) {}

    bool insertCandidate(const Routes& routes, double obj, PoolInsertSource source) {
        std::lock_guard<std::mutex> lk(mtx_);
        bool accepted = population_.tryInject({normalizeRoutes(routes, numVehicles_), obj}, tau_);
        incrementInsertStats(source, accepted);
        return accepted;
    }

    void setNumVehicles(int numVehicles) {
        std::lock_guard<std::mutex> lk(mtx_);
        numVehicles_ = numVehicles;
    }

    int size() const {
        std::lock_guard<std::mutex> lk(mtx_);
        return population_.size();
    }

    std::optional<Individual> best() const {
        std::lock_guard<std::mutex> lk(mtx_);
        if (population_.empty()) return std::nullopt;
        return population_.best();
    }

    std::optional<Individual> sampleBiased(RNG& rng) const {
        std::lock_guard<std::mutex> lk(mtx_);
        return population_.qualityDiversitySample(rng);
    }

    GaMtStats stats() const {
        std::lock_guard<std::mutex> lk(mtx_);
        GaMtStats copy = stats_;
        copy.poolSize = population_.size();
        return copy;
    }

    void recordPullAttempt() {
        std::lock_guard<std::mutex> lk(mtx_);
        ++stats_.pullsAttempted;
    }

    void recordPullAccepted() {
        std::lock_guard<std::mutex> lk(mtx_);
        ++stats_.pullsAccepted;
    }

private:
    mutable std::mutex mtx_;
    Population population_;
    double tau_;
    int numVehicles_ = 0;
    GaMtStats stats_;

    void incrementInsertStats(PoolInsertSource source, bool accepted) {
        if (source == PoolInsertSource::Seed) {
            accepted ? ++stats_.acceptedSeeds : ++stats_.rejectedSeeds;
        } else if (source == PoolInsertSource::Child) {
            accepted ? ++stats_.acceptedChildren : ++stats_.rejectedChildren;
        } else {
            accepted ? ++stats_.acceptedMigrants : ++stats_.rejectedMigrants;
        }
    }
};

struct WorkerResult {
    Routes routes;
    double objectiveValue = std::numeric_limits<double>::infinity();
    std::string source;
};

struct GaMtOptions {
    GaMtModel model = GaMtModel::Bidirectional;
    double timeLimit = 120.0;
    int seed = 42;
    double tau = 0.10;
    double pPull = 0.10;
    double migrationInterval = 5.0;
    int popMin = 25;
    int popMax = 50;
};

struct GaMtResult {
    std::string solution;
    double objectiveValue = std::numeric_limits<double>::infinity();
    Routes routes;
    bool valid = false;
    std::string bestSource;
    GaMtStats stats;
};

inline SolverConfig gaMtWorkerConfig(int workerId, int seed) {
    SolverConfig c;
    c.constructor = "regret_bidding";
    c.granular = true;
    c.seed = seed + workerId * 1'000'003;

    if (workerId == 0) {
        c.improver = "destroy_repair";
        c.tabu = false;
    } else if (workerId == 1) {
        c.improver = "ejection_chains";
        c.tabu = false;
    } else {
        c.improver = "relocate_swap";
        c.tabu = true;
    }
    return c;
}

inline Routes gaMtChildLocalSearch(
    const VRPInstance& inst,
    const Routes& routes,
    double subDeadline,
    RNG& rng)
{
    SolverConfig cfg;
    cfg.improver = "relocate_swap";
    cfg.granular = false;
    cfg.tabu = false;
    Routes improved = twoOptRoutes(inst, normalizeRoutes(routes, inst.numVehicles));
    return relocateSwapImprove(inst, improved, cfg, rng, subDeadline);
}

inline Routes gaMtPerturb(
    const VRPInstance& inst,
    const Routes& routes,
    RNG& rng,
    double fraction = 0.03)
{
    Routes candidate = normalizeRoutes(cloneRoutes(routes), inst.numVehicles);
    std::vector<int> allCustomers;
    for (const auto& route : candidate)
        for (int customer : route) allCustomers.push_back(customer);
    if (allCustomers.empty()) return candidate;

    int removeCount = std::max(1, (int)std::round((inst.numCustomers - 1) * fraction));
    removeCount = std::min(removeCount, (int)allCustomers.size());
    std::vector<int> removed = rng.sample(allCustomers, removeCount);
    std::unordered_set<int> removedSet(removed.begin(), removed.end());

    for (auto& route : candidate) {
        std::vector<int> kept;
        kept.reserve(route.size());
        for (int customer : route)
            if (!removedSet.count(customer)) kept.push_back(customer);
        route = std::move(kept);
    }

    std::shuffle(removed.begin(), removed.end(), rng.gen);
    for (int customer : removed) {
        if (!insertBestFeasible(inst, candidate, customer))
            return normalizeRoutes(cloneRoutes(routes), inst.numVehicles);
    }

    candidate = twoOptRoutes(inst, candidate);
    if (validateRoutes(inst, candidate))
        return normalizeRoutes(cloneRoutes(routes), inst.numVehicles);
    return candidate;
}

inline void gaMtPublishIfImproved(
    SharedGAPool* pool,
    const Routes& routes,
    double obj,
    double& lastPushedObj)
{
    if (!pool) return;
    if (obj + 1e-9 < lastPushedObj) {
        pool->insertCandidate(routes, obj, PoolInsertSource::Migrant);
        lastPushedObj = obj;
    }
}

inline void gaMtWorkerRun(
    int workerId,
    const VRPInstance& inst,
    const GaMtOptions& opts,
    SharedGAPool* pool,
    WorkerResult& result,
    double deadline)
{
    pinGaMtThreadToCore(workerId);

    SolverConfig config = gaMtWorkerConfig(workerId, opts.seed);
    RNG rng(config.seed);

    Routes current = regretBiddingConstruct(inst, rng);
    current = normalizeRoutes(current, inst.numVehicles);
    if (validateRoutes(inst, current))
        current = farthestNearestConstruct(inst, rng);

    Routes personalBest = current;
    double personalBestObj = objective(inst, personalBest);
    double lastPushedObj = std::numeric_limits<double>::infinity();
    gaMtPublishIfImproved(pool, personalBest, personalBestObj, lastPushedObj);

    while (now() < deadline) {
        double cycleDeadline = std::min(now() + opts.migrationInterval, deadline);

        ImprovementCallback onImprovement = [&](const Routes& routes, double obj) {
            if (obj + 1e-9 < personalBestObj) {
                personalBest = normalizeRoutes(routes, inst.numVehicles);
                personalBestObj = obj;
            }
            gaMtPublishIfImproved(pool, routes, obj, lastPushedObj);
        };

        Routes improved;
        if (config.improver == "destroy_repair") {
            improved = adaptiveDestroyRepairImprove(
                inst, current, config, rng, cycleDeadline, nullptr, &onImprovement);
        } else if (config.improver == "ejection_chains") {
            improved = ejectionChainsImprove(
                inst, current, config, rng, cycleDeadline, nullptr, &onImprovement);
        } else {
            improved = relocateSwapImprove(
                inst, current, config, rng, cycleDeadline, nullptr, &onImprovement);
        }

        improved = normalizeRoutes(improved, inst.numVehicles);
        if (!validateRoutes(inst, improved)) {
            double improvedObj = objective(inst, improved);
            if (improvedObj + 1e-9 < personalBestObj) {
                personalBest = improved;
                personalBestObj = improvedObj;
            }
            gaMtPublishIfImproved(pool, improved, improvedObj, lastPushedObj);
        }

        current = personalBest;

        bool pulledSeed = false;
        if (opts.model == GaMtModel::Bidirectional && pool && now() < deadline) {
            if (rng.random() < opts.pPull) {
                pool->recordPullAttempt();
                auto pulled = pool->sampleBiased(rng);
                if (pulled) {
                    pool->recordPullAccepted();
                    current = gaMtPerturb(inst, pulled->routes, rng);
                    pulledSeed = true;
                }
            }
        }
        if (!pulledSeed && config.improver != "destroy_repair" && now() < deadline) {
            current = gaMtPerturb(inst, personalBest, rng);
        }
    }

    result.routes = personalBest;
    result.objectiveValue = personalBestObj;
    result.source = "worker_" + std::to_string(workerId + 1);
}

inline void gaMtSeedPool(
    SharedGAPool& pool,
    const VRPInstance& inst,
    int count,
    double deadline,
    RNG& rng)
{
    int attempts = 0;
    int maxAttempts = std::max(count * 4, count + 5);
    while (pool.size() < count && attempts < maxAttempts && now() < deadline) {
        Routes routes = (attempts % 2 == 0)
            ? regretBiddingConstruct(inst, rng)
            : farthestNearestConstruct(inst, rng);
        double subDeadline = std::min(now() + 0.1, deadline);
        routes = gaMtChildLocalSearch(inst, routes, subDeadline, rng);
        if (!validateRoutes(inst, routes))
            pool.insertCandidate(routes, objective(inst, routes), PoolInsertSource::Seed);
        ++attempts;
    }
}

inline void gaMtGaRun(
    const VRPInstance& inst,
    const GaMtOptions& opts,
    SharedGAPool& pool,
    double deadline)
{
    pinGaMtThreadToCore(3);
    RNG rng(opts.seed + 9'000'021);
    gaMtSeedPool(pool, inst, opts.popMin, deadline, rng);

    while (now() < deadline) {
        if (pool.size() < 2) {
            gaMtSeedPool(pool, inst, 2, deadline, rng);
            continue;
        }

        auto parentA = pool.sampleBiased(rng);
        auto parentB = pool.sampleBiased(rng);
        if (!parentA || !parentB) continue;

        Routes child = crossover(inst, *parentA, *parentB, rng);
        double subDeadline = std::min(now() + 0.1, deadline);
        child = gaMtChildLocalSearch(inst, child, subDeadline, rng);
        child = normalizeRoutes(child, inst.numVehicles);
        if (validateRoutes(inst, child)) continue;

        pool.insertCandidate(child, objective(inst, child), PoolInsertSource::Child);
    }
}

inline GaMtResult gaMtSolve(const VRPInstance& inst, const GaMtOptions& opts) {
    double deadline = now() + opts.timeLimit;

    std::unique_ptr<SharedGAPool> pool;
    if (opts.model != GaMtModel::Independent) {
        pool = std::make_unique<SharedGAPool>(
            opts.popMin, opts.popMax, inst.numCustomers, opts.tau);
        pool->setNumVehicles(inst.numVehicles);
    }

    std::vector<WorkerResult> workers(3);
    std::vector<std::thread> threads;
    threads.reserve(opts.model == GaMtModel::Independent ? 3 : 4);

    for (int workerId = 0; workerId < 3; ++workerId) {
        threads.emplace_back(
            gaMtWorkerRun,
            workerId,
            std::cref(inst),
            std::cref(opts),
            pool.get(),
            std::ref(workers[workerId]),
            deadline);
    }

    if (pool) {
        threads.emplace_back(gaMtGaRun, std::cref(inst), std::cref(opts),
                             std::ref(*pool), deadline);
    }

    for (auto& thread : threads) thread.join();

    GaMtResult result;
    for (const auto& worker : workers) {
        if (worker.objectiveValue < result.objectiveValue) {
            result.routes = worker.routes;
            result.objectiveValue = worker.objectiveValue;
            result.bestSource = worker.source;
        }
    }

    if (pool) {
        auto poolBest = pool->best();
        result.stats = pool->stats();
        if (poolBest && poolBest->objective < result.objectiveValue) {
            result.routes = poolBest->routes;
            result.objectiveValue = poolBest->objective;
            result.bestSource = "ga_pool";
        }
    }

    result.routes = normalizeRoutes(result.routes, inst.numVehicles);
    if (!result.routes.empty()) {
        result.routes = twoOptRoutes(inst, result.routes);
        result.objectiveValue = objective(inst, result.routes);
    }
    result.valid = !validateRoutes(inst, result.routes);
    result.solution = formatSolution(result.routes);
    return result;
}
