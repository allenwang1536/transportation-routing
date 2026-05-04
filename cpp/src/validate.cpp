#include "vrpinstance.hpp"
#include "route_utils.hpp"
#include <cmath>
#include <cstdio>
#include <filesystem>
#include <iostream>
#include <sstream>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

// ── Solution parsing ──────────────────────────────────────────────────────────
// Parses a depot-bounded token string: "0 1 2 0 0 3 4 0 ..."
static Routes parseSolution(const std::string& s) {
    std::istringstream ss(s);
    std::vector<int> tokens;
    int t;
    while (ss >> t) tokens.push_back(t);

    Routes routes;
    int i = 0;
    while (i < static_cast<int>(tokens.size())) {
        if (tokens[i] != 0)
            throw std::runtime_error("solution token stream: expected depot 0, got " + std::to_string(tokens[i]));
        ++i;
        std::vector<int> route;
        while (i < static_cast<int>(tokens.size()) && tokens[i] != 0)
            route.push_back(tokens[i++]);
        if (i == static_cast<int>(tokens.size()) && !route.empty())
            throw std::runtime_error("solution token stream: route not closed with depot 0");
        ++i; // consume closing 0
        routes.push_back(route);
    }
    return routes;
}

// ── Minimal JSON field extraction (no library needed for our fixed format) ────
// Extracts the string value of a JSON key from a single-line flat JSON object.
static std::string jsonStr(const std::string& json, const std::string& key) {
    std::string needle = "\"" + key + "\": \"";
    auto pos = json.find(needle);
    if (pos == std::string::npos) return "";
    pos += needle.size();
    auto end = json.find('"', pos);
    return json.substr(pos, end - pos);
}

// Extracts a numeric (unquoted) JSON value.
static std::string jsonNum(const std::string& json, const std::string& key) {
    std::string needle = "\"" + key + "\": ";
    auto pos = json.find(needle);
    if (pos == std::string::npos) return "";
    pos += needle.size();
    auto end = json.find_first_of(",}", pos);
    std::string raw = json.substr(pos, end - pos);
    // trim whitespace
    while (!raw.empty() && (raw.back() == ' ' || raw.back() == '\n')) raw.pop_back();
    return raw;
}

// ── Validation with detailed error reporting ──────────────────────────────────
struct ValidationResult {
    bool valid = true;
    std::vector<std::string> errors;
    std::vector<int> loads;
    double recomputedObj = 0.0;
};

static ValidationResult validate(const VRPInstance& inst, const Routes& routes) {
    ValidationResult r;

    // Collect all visited customers
    std::vector<int> seen;
    for (const auto& route : routes)
        for (int c : route) seen.push_back(c);

    // Route count
    if (static_cast<int>(routes.size()) != inst.numVehicles)
        r.errors.push_back("expected " + std::to_string(inst.numVehicles)
                         + " routes, found " + std::to_string(routes.size()));

    // Coverage
    std::unordered_set<int> expected;
    for (int i = 1; i < inst.numCustomers; ++i) expected.insert(i);
    std::unordered_set<int> seenSet(seen.begin(), seen.end());

    std::vector<int> missing, extra;
    for (int c : expected) if (!seenSet.count(c)) missing.push_back(c);
    for (int c : seenSet) if (!expected.count(c)) extra.push_back(c);
    std::sort(missing.begin(), missing.end());
    std::sort(extra.begin(), extra.end());

    if (!missing.empty()) {
        std::string msg = "missing customers:";
        for (int c : missing) msg += " " + std::to_string(c);
        r.errors.push_back(msg);
    }
    if (!extra.empty()) {
        std::string msg = "unknown customers:";
        for (int c : extra) msg += " " + std::to_string(c);
        r.errors.push_back(msg);
    }

    // Duplicates
    std::unordered_map<int, int> counts;
    for (int c : seen) ++counts[c];
    std::vector<int> dups;
    for (const auto& [c, cnt] : counts) if (cnt > 1) dups.push_back(c);
    std::sort(dups.begin(), dups.end());
    if (!dups.empty()) {
        std::string msg = "duplicate customers:";
        for (int c : dups) msg += " " + std::to_string(c);
        r.errors.push_back(msg);
    }

    // Capacity
    for (int v = 0; v < static_cast<int>(routes.size()); ++v) {
        int load = routeLoad(inst, routes[v]);
        r.loads.push_back(load);
        if (load > inst.vehicleCapacity)
            r.errors.push_back("vehicle " + std::to_string(v) + " load "
                             + std::to_string(load) + " exceeds capacity "
                             + std::to_string(inst.vehicleCapacity));
    }

    r.recomputedObj = objective(inst, routes);
    r.valid = r.errors.empty();
    return r;
}

// ── Entry point ───────────────────────────────────────────────────────────────
int main(int argc, char* argv[]) {
    if (argc < 2) {
        std::fprintf(stderr,
            "Usage: %s <instance.vrp> [solution_json_or_string]\n"
            "  If no second argument is given, JSON is read from stdin.\n"
            "  Example: ./solver instance.vrp | ./validate instance.vrp\n",
            argv[0]);
        return 1;
    }

    std::string instancePath = argv[1];

    // Read the JSON / solution string from argv[2] or stdin
    std::string input;
    if (argc >= 3) {
        input = argv[2];
    } else {
        std::getline(std::cin, input); // read one line from stdin
    }

    // Decide if input is JSON (starts with '{') or a bare solution string
    std::string solutionStr;
    std::string reportedResultStr;
    bool isJson = !input.empty() && input.front() == '{';

    if (isJson) {
        solutionStr      = jsonStr(input, "Solution");
        reportedResultStr = jsonNum(input, "Result");
    } else {
        solutionStr = input;
    }

    if (solutionStr.empty()) {
        std::fprintf(stderr, "Error: could not extract solution string from input.\n");
        return 1;
    }

    // Load instance
    VRPInstance inst(instancePath);
    std::string filename = std::filesystem::path(instancePath).filename().string();

    // Parse and validate
    Routes routes;
    try {
        routes = parseSolution(solutionStr);
    } catch (const std::exception& e) {
        std::fprintf(stderr, "Error parsing solution: %s\n", e.what());
        return 1;
    }

    ValidationResult vr = validate(inst, routes);

    // ── Print report ──────────────────────────────────────────────────────────
    std::printf("Instance: %s\n", filename.c_str());
    std::printf("  valid:               %s\n", vr.valid ? "YES" : "NO");
    std::printf("  routes:              %d / %d vehicles\n",
                static_cast<int>(routes.size()), inst.numVehicles);
    std::printf("  objective (reported):%s\n",
                reportedResultStr.empty() ? " --" : (" " + reportedResultStr).c_str());
    std::printf("  objective (computed):%g\n", vr.recomputedObj);

    if (!reportedResultStr.empty()) {
        double reported = std::stod(reportedResultStr);
        double diff = std::abs(reported - vr.recomputedObj);
        if (diff > 0.005)
            std::printf("  WARNING: reported vs computed differ by %.4f\n", diff);
    }

    // Per-route loads
    std::printf("  route loads:        ");
    for (int i = 0; i < static_cast<int>(vr.loads.size()); ++i)
        std::printf(" %d", vr.loads[i]);
    std::printf("  (capacity %d)\n", inst.vehicleCapacity);

    if (vr.errors.empty()) {
        std::printf("  errors:              none\n");
    } else {
        for (const auto& err : vr.errors)
            std::printf("  ERROR: %s\n", err.c_str());
    }

    return vr.valid ? 0 : 1;
}
