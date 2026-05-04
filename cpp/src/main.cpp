#include "solver_runner.hpp"
#include "solver_config.hpp"
#include "timer.hpp"
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <iostream>
#include <string>

static void printUsage(const char* prog) {
    std::fprintf(stderr,
        "Usage: %s <input_file> [--constructor NAME] [--improver NAME]\n"
        "       [--granular] [--tabu] [--time-limit SECS] [--seed N]\n", prog);
}

int main(int argc, char* argv[]) {
    if (argc < 2) { printUsage(argv[0]); return 1; }

    std::string inputFile;
    SolverConfig config;
    bool hasExplicitConfig = false;

    for (int i = 1; i < argc; ++i) {
        if (std::strcmp(argv[i], "--constructor") == 0 && i + 1 < argc) {
            config.constructor = argv[++i]; hasExplicitConfig = true;
        } else if (std::strcmp(argv[i], "--improver") == 0 && i + 1 < argc) {
            config.improver = argv[++i]; hasExplicitConfig = true;
        } else if (std::strcmp(argv[i], "--granular") == 0) {
            config.granular = true; hasExplicitConfig = true;
        } else if (std::strcmp(argv[i], "--tabu") == 0) {
            config.tabu = true; hasExplicitConfig = true;
        } else if (std::strcmp(argv[i], "--time-limit") == 0 && i + 1 < argc) {
            config.timeLimit = std::stod(argv[++i]); hasExplicitConfig = true;
        } else if (std::strcmp(argv[i], "--seed") == 0 && i + 1 < argc) {
            config.seed = std::stoi(argv[++i]); hasExplicitConfig = true;
        } else if (argv[i][0] != '-') {
            inputFile = argv[i];
        } else {
            std::fprintf(stderr, "Unknown flag: %s\n", argv[i]);
            printUsage(argv[0]); return 1;
        }
    }

    if (inputFile.empty()) { printUsage(argv[0]); return 1; }

    std::string filename = std::filesystem::path(inputFile).filename().string();

    Timer timer;
    timer.start();

    try {
        VRPInstance inst(inputFile);
        SolveResult result = solveInstance(inst, hasExplicitConfig ? &config : nullptr);
        timer.stop();

        // Output JSON matching Python's format exactly
        std::printf("{\"Instance\": \"%s\", \"Time\": \"%.2f\", \"Result\": %g, \"Solution\": \"%s\"}\n",
                    filename.c_str(),
                    timer.getTime(),
                    result.objectiveValue,
                    result.solution.c_str());
    } catch (const std::exception& e) {
        timer.stop();
        std::fprintf(stderr, "Error: %s\n", e.what());
        return 1;
    }

    return 0;
}
