#pragma once
#include "constructors/farthest_nearest.hpp"
#include "constructors/regret_bidding.hpp"
#include "constructors/sweep.hpp"
#include "improvers/adaptive_destroy_repair.hpp"
#include "improvers/ejection_chains.hpp"
#include "improvers/relocate_swap.hpp"
#include "route_utils.hpp"
#include "solver_config.hpp"
#include "vrpinstance.hpp"
#include <cstdlib>
#include <functional>
#include <stdexcept>
#include <string>
#include <tuple>
#include <unordered_map>

using ConstructorFn = std::function<Routes(const VRPInstance&, RNG&)>;
using ImproverFn    = std::function<Routes(const VRPInstance&, const Routes&, const SolverConfig&, RNG&, double)>;

inline const std::unordered_map<std::string, ConstructorFn>& constructors() {
    static const std::unordered_map<std::string, ConstructorFn> table = {
        {"farthest_nearest", farthestNearestConstruct},
        {"sweep",            sweepConstruct},
        {"regret_bidding",   regretBiddingConstruct},
    };
    return table;
}

inline const std::unordered_map<std::string, ImproverFn>& improvers() {
    static const std::unordered_map<std::string, ImproverFn> table = {
        {"relocate_swap",  [](const VRPInstance& i, const Routes& r, const SolverConfig& c, RNG& g, double d) {
            return relocateSwapImprove(i, r, c, g, d); }},
        {"destroy_repair", [](const VRPInstance& i, const Routes& r, const SolverConfig& c, RNG& g, double d) {
            return adaptiveDestroyRepairImprove(i, r, c, g, d); }},
        {"ejection_chains",[](const VRPInstance& i, const Routes& r, const SolverConfig& c, RNG& g, double d) {
            return ejectionChainsImprove(i, r, c, g, d); }},
    };
    return table;
}

// Read env var as string, return default if not set.
inline std::string envStr(const char* name, const char* def) {
    const char* val = std::getenv(name);
    return val ? std::string(val) : std::string(def);
}

inline bool envBool(const char* name, bool def = false) {
    const char* val = std::getenv(name);
    if (!val) return def;
    std::string s(val);
    return s == "1" || s == "true" || s == "yes" || s == "on";
}

inline SolverConfig configFromEnv() {
    SolverConfig c;
    c.constructor    = envStr("VRP_CONSTRUCTOR", "farthest_nearest");
    c.improver       = envStr("VRP_IMPROVER", "none");
    c.granular       = envBool("VRP_GRANULAR");
    c.tabu           = envBool("VRP_TABU");
    c.timeLimit      = std::stod(envStr("VRP_TIME_LIMIT", "0"));
    c.seed           = std::stoi(envStr("VRP_SEED", "0"));
    c.neighborCount  = std::stoi(envStr("VRP_NEIGHBOR_COUNT", "20"));
    c.tabuTenure     = std::stoi(envStr("VRP_TABU_TENURE", "25"));
    return c;
}

struct SolveResult {
    std::string solution;
    double objectiveValue;
    Routes routes;
};

inline SolveResult solveInstance(const VRPInstance& inst, const SolverConfig* cfgPtr = nullptr) {
    SolverConfig cfg = cfgPtr ? *cfgPtr : configFromEnv();
    RNG rng(cfg.seed);

    double deadline = (cfg.timeLimit > 0.0) ? now() + cfg.timeLimit : -1.0;

    // ── Construction ──────────────────────────────────────────────────────────
    auto ctIt = constructors().find(cfg.constructor);
    if (ctIt == constructors().end())
        throw std::runtime_error("Unknown constructor: " + cfg.constructor);

    Routes routes = ctIt->second(inst, rng);
    routes = normalizeRoutes(routes, inst.numVehicles);
    if (validateRoutes(inst, routes))
        routes = farthestNearestConstruct(inst, rng);

    // ── Improvement ───────────────────────────────────────────────────────────
    if (cfg.improver != "none" && deadline > 0.0 && now() < deadline) {
        auto impIt = improvers().find(cfg.improver);
        if (impIt == improvers().end())
            throw std::runtime_error("Unknown improver: " + cfg.improver);
        routes = impIt->second(inst, routes, cfg, rng, deadline);
        routes = normalizeRoutes(routes, inst.numVehicles);
        routes = twoOptRoutes(inst, routes);
    }

    if (validateRoutes(inst, routes))
        routes = farthestNearestConstruct(inst, rng);

    std::string solution = formatSolution(routes);
    double obj = objective(inst, routes);
    return {solution, obj, routes};
}
