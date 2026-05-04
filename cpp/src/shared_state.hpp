#pragma once
#include "route_utils.hpp"
#include <limits>
#include <mutex>
#include <utility>

// Thread-safe pool holding the best solution found across all parallel threads.
//
// Design: accept a shared solution only when it beats the personal best
// (not "better than current state" or "last N states").
//
// For destroy_repair (SA-based): bidirectional — threads both publish and read
// every shareThreshold personal improvements.  SA's own acceptance criterion
// already handles "don't cut off exploration"; injecting the global best as the
// new current just gives SA a better starting point.
//
// For ejection_chains / relocate_swap (greedy): publish-only — threads emit
// every improvement immediately so destroy_repair threads benefit, but reading
// is deferred to the outer restart loop in parallel_solver.hpp (these methods
// converge to a local optimum quickly and are simply restarted from the global
// best by the thread runner).
struct SharedState {
    // Number of personal improvements before a destroy_repair thread checks
    // and updates the pool.
    int shareThreshold;

    explicit SharedState(int threshold = 3) : shareThreshold(threshold) {}

    // Publish a solution.  Returns true if it became the new global best.
    bool tryUpdate(const Routes& routes, double obj) {
        std::lock_guard<std::mutex> lk(mtx_);
        if (obj < bestObj_) {
            bestObj_   = obj;
            bestRoutes_ = routes;
            return true;
        }
        return false;
    }

    std::pair<Routes, double> getBest() const {
        std::lock_guard<std::mutex> lk(mtx_);
        return {bestRoutes_, bestObj_};
    }

    double getBestObj() const {
        std::lock_guard<std::mutex> lk(mtx_);
        return bestObj_;
    }

private:
    mutable std::mutex mtx_;
    Routes bestRoutes_;
    double bestObj_ = std::numeric_limits<double>::infinity();
};
