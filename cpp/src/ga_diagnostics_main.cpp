#include "ga/diagnostics.hpp"
#include "ga_multithreaded_solver.hpp"
#include "timer.hpp"
#include "vrpinstance.hpp"
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <string>

static void usage(const char* prog) {
    std::fprintf(stderr,
        "Usage: %s <input_file> --time-limit SECS [--seed N] [--out-prefix PATH]\n"
        "  Always runs the bidirectional model (GA + 3 workers, full sharing).\n"
        "  Writes three diagnostic CSV files:\n"
        "    <prefix>_worker_diversity.csv   pairwise broken-pairs distances over time\n"
        "    <prefix>_injections.csv         every pool insertion attempt\n"
        "    <prefix>_pop_snapshots.csv      population health snapshots every 5 s\n",
        prog);
}

int main(int argc, char* argv[]) {
    if (argc < 2) { usage(argv[0]); return 1; }

    std::string inputFile;
    double timeLimit  = 0.0;
    int    seed       = 42;
    std::string outPrefix;

    for (int i = 1; i < argc; ++i) {
        if      (std::strcmp(argv[i], "--time-limit") == 0 && i + 1 < argc)
            timeLimit  = std::stod(argv[++i]);
        else if (std::strcmp(argv[i], "--seed")       == 0 && i + 1 < argc)
            seed       = std::stoi(argv[++i]);
        else if (std::strcmp(argv[i], "--out-prefix") == 0 && i + 1 < argc)
            outPrefix  = argv[++i];
        else if (argv[i][0] != '-')
            inputFile  = argv[i];
        else { std::fprintf(stderr, "Unknown flag: %s\n", argv[i]); usage(argv[0]); return 1; }
    }

    if (inputFile.empty() || timeLimit <= 0.0) {
        std::fprintf(stderr, "Error: input file and --time-limit required.\n");
        usage(argv[0]); return 1;
    }

    // Auto-generate output prefix: experiments/diag_<stem>_<timestamp>
    if (outPrefix.empty()) {
        namespace fs = std::filesystem;
        std::string stem = fs::path(inputFile).stem().string();
        // Use a simple timestamp: seconds since epoch mod 1e6 (enough for uniqueness).
        long ts = (long)now();
        outPrefix = "experiments/diag_" + stem + "_" + std::to_string(ts);
    }

    std::string filename = std::filesystem::path(inputFile).filename().string();

    Timer timer;
    timer.start();
    try {
        VRPInstance inst(inputFile);

        DiagnosticsLogger logger(inst.numCustomers);

        GaMtOptions opts;
        opts.model             = GaMtModel::Bidirectional;
        opts.timeLimit         = timeLimit;
        opts.seed              = seed;
        opts.tau               = 0.10;
        opts.pPull             = 0.10;
        opts.migrationInterval = 5.0;
        opts.popMin            = 25;
        opts.popMax            = 50;

        GaMtResult result = gaMtSolve(inst, opts, &logger);
        timer.stop();

        // Main JSON result (same format as ga_multithreaded_solver)
        std::printf("{\"Instance\": \"%s\", \"Model\": \"bidirectional\", "
                    "\"Time\": \"%.2f\", \"Result\": %g, \"Valid\": %s, "
                    "\"BestSource\": \"%s\", \"PoolSize\": %d, "
                    "\"AcceptedSeeds\": %ld, \"RejectedSeeds\": %ld, "
                    "\"AcceptedChildren\": %ld, \"RejectedChildren\": %ld, "
                    "\"AcceptedMigrants\": %ld, \"RejectedMigrants\": %ld, "
                    "\"PullsAttempted\": %ld, \"PullsAccepted\": %ld, "
                    "\"Solution\": \"%s\"}\n",
                    filename.c_str(), timer.getTime(),
                    result.objectiveValue, result.valid ? "true" : "false",
                    result.bestSource.c_str(),
                    result.stats.poolSize,
                    result.stats.acceptedSeeds,   result.stats.rejectedSeeds,
                    result.stats.acceptedChildren, result.stats.rejectedChildren,
                    result.stats.acceptedMigrants, result.stats.rejectedMigrants,
                    result.stats.pullsAttempted,   result.stats.pullsAccepted,
                    result.solution.c_str());

        // Write diagnostic CSVs
        logger.writeLogs(outPrefix);
        std::fprintf(stderr, "Diagnostics written to: %s_*.csv\n", outPrefix.c_str());
    } catch (const std::exception& e) {
        timer.stop();
        std::fprintf(stderr, "Error: %s\n", e.what());
        return 1;
    }
    return 0;
}
