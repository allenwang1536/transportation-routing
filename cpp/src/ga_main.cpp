#include "ga/hgs.hpp"
#include "timer.hpp"
#include "vrpinstance.hpp"
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <string>

static void usage(const char* prog) {
    std::fprintf(stderr,
        "Usage: %s <input_file> --time-limit SECS [--seed N] [--pop-min N] [--pop-max N]\n"
        "  Runs the Hybrid Genetic Search (HGS) VRP solver.\n"
        "  Default: --pop-min 25 --pop-max 50 --seed 0\n", prog);
}

int main(int argc, char* argv[]) {
    if (argc < 2) { usage(argv[0]); return 1; }

    std::string inputFile;
    double timeLimit = 0.0;
    int    seed      = 0;
    int    popMin    = 25;
    int    popMax    = 50;

    for (int i = 1; i < argc; ++i) {
        if      (std::strcmp(argv[i], "--time-limit") == 0 && i + 1 < argc)
            timeLimit = std::stod(argv[++i]);
        else if (std::strcmp(argv[i], "--seed")       == 0 && i + 1 < argc)
            seed      = std::stoi(argv[++i]);
        else if (std::strcmp(argv[i], "--pop-min")    == 0 && i + 1 < argc)
            popMin    = std::stoi(argv[++i]);
        else if (std::strcmp(argv[i], "--pop-max")    == 0 && i + 1 < argc)
            popMax    = std::stoi(argv[++i]);
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
        HGSResult result = hgsSolve(inst, timeLimit, seed, popMin, popMax);
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
