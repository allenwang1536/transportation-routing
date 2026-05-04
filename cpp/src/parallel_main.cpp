#include "parallel_solver.hpp"
#include "solver_runner.hpp"   // for single-threaded baseline via solveInstance
#include "timer.hpp"
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <string>

static void usage(const char* prog) {
    std::fprintf(stderr,
        "Usage: %s <input_file> --time-limit SECS [--seed N] [--share-threshold N]\n"
        "  Runs 4 threads in parallel:\n"
        "    thread 0  regret_bidding + destroy_repair + granular\n"
        "    thread 1  regret_bidding + destroy_repair + granular + tabu\n"
        "    thread 2  regret_bidding + ejection_chains + granular\n"
        "    thread 3  regret_bidding + relocate_swap\n", prog);
}

int main(int argc, char* argv[]) {
    if (argc < 2) { usage(argv[0]); return 1; }

    std::string inputFile;
    double timeLimit = 0.0;
    int    seed      = 0;
    int    shareTh   = 3;

    for (int i = 1; i < argc; ++i) {
        if (std::strcmp(argv[i], "--time-limit") == 0 && i + 1 < argc)
            timeLimit = std::stod(argv[++i]);
        else if (std::strcmp(argv[i], "--seed") == 0 && i + 1 < argc)
            seed = std::stoi(argv[++i]);
        else if (std::strcmp(argv[i], "--share-threshold") == 0 && i + 1 < argc)
            shareTh = std::stoi(argv[++i]);
        else if (argv[i][0] != '-')
            inputFile = argv[i];
        else { std::fprintf(stderr, "Unknown flag: %s\n", argv[i]); usage(argv[0]); return 1; }
    }

    if (inputFile.empty() || timeLimit <= 0.0) {
        std::fprintf(stderr, "Error: input file and --time-limit are required.\n");
        usage(argv[0]); return 1;
    }

    std::string filename = std::filesystem::path(inputFile).filename().string();

    Timer timer;
    timer.start();
    try {
        VRPInstance inst(inputFile);
        ParallelResult result = parallelSolve(inst, timeLimit, seed, shareTh);
        timer.stop();

        std::printf("{\"Instance\": \"%s\", \"Time\": \"%.2f\", \"Result\": %g, \"Solution\": \"%s\"}\n",
                    filename.c_str(), timer.getTime(),
                    result.objectiveValue, result.solution.c_str());
    } catch (const std::exception& e) {
        timer.stop();
        std::fprintf(stderr, "Error: %s\n", e.what());
        return 1;
    }
    return 0;
}
