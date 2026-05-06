#pragma once
#include "../route_utils.hpp"
#include "population.hpp"
#include <array>
#include <fstream>
#include <mutex>
#include <string>
#include <vector>

// ── DiagnosticsLogger ─────────────────────────────────────────────────────────
// Thread-safe event collector for the GA + worker run.
// All timestamps are seconds elapsed since the logger was constructed.
//
// Produces three CSV files when writeLogs() is called:
//   <prefix>_worker_diversity.csv  — pairwise broken-pairs distance between workers over time
//   <prefix>_injections.csv        — every pool insertion attempt (source, accepted, diversity, obj)
//   <prefix>_pop_snapshots.csv     — periodic population health snapshots (diversity + obj)

class DiagnosticsLogger {
public:
    explicit DiagnosticsLogger(int numCustomers)
        : numCustomers_(numCustomers), startTime_(now()) {
        hasRoutes_.fill(false);
    }

    // ── Worker push ───────────────────────────────────────────────────────────
    // Called by each worker thread when it publishes a new personal best.
    // Updates per-worker latest routes and emits a pairwise distance sample.
    void logWorkerPush(int workerId, const Routes& routes, double obj) {
        std::lock_guard<std::mutex> lk(mtx_);
        workerPushes_.push_back({elapsed(), workerId, obj});

        lastRoutes_[workerId] = routes;
        hasRoutes_[workerId] = true;

        // Emit a diversity point whenever at least two workers have published.
        int seen = (int)hasRoutes_[0] + (int)hasRoutes_[1] + (int)hasRoutes_[2];
        if (seen >= 2) {
            DivPoint pt;
            pt.time  = elapsed();
            pt.d[0]  = (hasRoutes_[0] && hasRoutes_[1])
                       ? Population::distance(lastRoutes_[0], lastRoutes_[1], numCustomers_)
                       : -1.0;
            pt.d[1]  = (hasRoutes_[0] && hasRoutes_[2])
                       ? Population::distance(lastRoutes_[0], lastRoutes_[2], numCustomers_)
                       : -1.0;
            pt.d[2]  = (hasRoutes_[1] && hasRoutes_[2])
                       ? Population::distance(lastRoutes_[1], lastRoutes_[2], numCustomers_)
                       : -1.0;
            divTimeline_.push_back(pt);
        }
    }

    // ── Pool injection ────────────────────────────────────────────────────────
    // Called from SharedGAPool::insertCandidate for every insertion attempt.
    // source: "worker_0" / "worker_1" / "worker_2" / "hgs_child" / "seed"
    // diversityScore: minDistanceTo(routes) at the moment of insertion
    // poolBestObj: best objective in the pool at that moment
    void logInjection(const std::string& source, bool accepted,
                      double diversityScore, double obj, double poolBestObj) {
        std::lock_guard<std::mutex> lk(mtx_);
        injections_.push_back({elapsed(), source, accepted, diversityScore, obj, poolBestObj});
    }

    // ── Population snapshot ───────────────────────────────────────────────────
    // Called periodically from the GA thread.
    void logPopSnapshot(int popSize, double avgPairwiseDist,
                        double bestObj, double worstObj) {
        std::lock_guard<std::mutex> lk(mtx_);
        popSnapshots_.push_back({elapsed(), popSize, avgPairwiseDist, bestObj, worstObj});
    }

    // ── Output ────────────────────────────────────────────────────────────────
    void writeLogs(const std::string& prefix) const {
        writeWorkerDiversity(prefix + "_worker_diversity.csv");
        writeInjections(prefix + "_injections.csv");
        writePopSnapshots(prefix + "_pop_snapshots.csv");
    }

private:
    mutable std::mutex mtx_;
    int numCustomers_;
    double startTime_;

    struct WorkerPush { double time; int workerId; double obj; };
    struct DivPoint   { double time; double d[3]; }; // d[0]=W0W1, d[1]=W0W2, d[2]=W1W2
    struct Injection  {
        double time; std::string source; bool accepted;
        double diversityScore, obj, poolBestObj;
    };
    struct PopSnap    { double time; int sz; double avgDiv, bestObj, worstObj; };

    std::vector<WorkerPush> workerPushes_;
    std::vector<DivPoint>   divTimeline_;
    std::vector<Injection>  injections_;
    std::vector<PopSnap>    popSnapshots_;

    Routes lastRoutes_[3];
    std::array<bool, 3> hasRoutes_;

    double elapsed() const { return now() - startTime_; }

    // ── CSV writers ───────────────────────────────────────────────────────────
    void writeWorkerDiversity(const std::string& path) const {
        std::ofstream f(path);
        f << "time_s,dist_W0_W1,dist_W0_W2,dist_W1_W2\n";
        for (const auto& pt : divTimeline_)
            f << pt.time << ',' << pt.d[0] << ',' << pt.d[1] << ',' << pt.d[2] << '\n';
    }

    void writeInjections(const std::string& path) const {
        std::ofstream f(path);
        f << "time_s,source,accepted,diversity_score,objective,pool_best_obj\n";
        for (const auto& ev : injections_)
            f << ev.time << ',' << ev.source << ',' << (ev.accepted ? 1 : 0) << ','
              << ev.diversityScore << ',' << ev.obj << ',' << ev.poolBestObj << '\n';
    }

    void writePopSnapshots(const std::string& path) const {
        std::ofstream f(path);
        f << "time_s,pop_size,avg_pairwise_dist,best_obj,worst_obj\n";
        for (const auto& sn : popSnapshots_)
            f << sn.time << ',' << sn.sz << ',' << sn.avgDiv
              << ',' << sn.bestObj << ',' << sn.worstObj << '\n';
    }
};
