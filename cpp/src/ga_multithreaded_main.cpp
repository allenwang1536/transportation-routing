#include "ga_multithreaded_solver.hpp"
#include "timer.hpp"
#include "vrpinstance.hpp"
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <stdexcept>
#include <string>

static void usage(const char* prog) {
    std::fprintf(stderr,
        "Usage: %s <input_file> --model independent|one_way|bidirectional --time-limit SECS [options]\n"
        "Options:\n"
        "  --seed N                  default 42\n"
        "  --tau X                   diversity threshold, default 0.10\n"
        "  --p-pull X                bidirectional pull probability, default 0.10\n"
        "  --migration-interval X    worker restart checkpoint seconds, default 5.0\n"
        "  --pop-min N               default 25\n"
        "  --pop-max N               default 50\n",
        prog);
}

static GaMtModel parseModel(const std::string& value) {
    if (value == "independent") return GaMtModel::Independent;
    if (value == "one_way") return GaMtModel::OneWay;
    if (value == "bidirectional") return GaMtModel::Bidirectional;
    throw std::runtime_error("unknown model: " + value);
}

static std::string modelName(GaMtModel model) {
    if (model == GaMtModel::Independent) return "independent";
    if (model == GaMtModel::OneWay) return "one_way";
    return "bidirectional";
}

static std::string jsonEscape(const std::string& value) {
    std::string out;
    out.reserve(value.size());
    for (char ch : value) {
        if (ch == '\\') out += "\\\\";
        else if (ch == '"') out += "\\\"";
        else if (ch == '\n') out += "\\n";
        else out += ch;
    }
    return out;
}

int main(int argc, char* argv[]) {
    if (argc < 2) {
        usage(argv[0]);
        return 1;
    }

    std::string inputFile;
    GaMtOptions opts;

    for (int i = 1; i < argc; ++i) {
        if (std::strcmp(argv[i], "--model") == 0 && i + 1 < argc) {
            opts.model = parseModel(argv[++i]);
        } else if (std::strcmp(argv[i], "--time-limit") == 0 && i + 1 < argc) {
            opts.timeLimit = std::stod(argv[++i]);
        } else if (std::strcmp(argv[i], "--seed") == 0 && i + 1 < argc) {
            opts.seed = std::stoi(argv[++i]);
        } else if (std::strcmp(argv[i], "--tau") == 0 && i + 1 < argc) {
            opts.tau = std::stod(argv[++i]);
        } else if (std::strcmp(argv[i], "--p-pull") == 0 && i + 1 < argc) {
            opts.pPull = std::stod(argv[++i]);
        } else if (std::strcmp(argv[i], "--migration-interval") == 0 && i + 1 < argc) {
            opts.migrationInterval = std::stod(argv[++i]);
        } else if (std::strcmp(argv[i], "--pop-min") == 0 && i + 1 < argc) {
            opts.popMin = std::stoi(argv[++i]);
        } else if (std::strcmp(argv[i], "--pop-max") == 0 && i + 1 < argc) {
            opts.popMax = std::stoi(argv[++i]);
        } else if (argv[i][0] != '-') {
            inputFile = argv[i];
        } else {
            std::fprintf(stderr, "Unknown flag: %s\n", argv[i]);
            usage(argv[0]);
            return 1;
        }
    }

    if (inputFile.empty() || opts.timeLimit <= 0.0) {
        std::fprintf(stderr, "Error: input file and positive --time-limit are required.\n");
        usage(argv[0]);
        return 1;
    }
    if (opts.popMin < 2 || opts.popMax < opts.popMin) {
        std::fprintf(stderr, "Error: require 2 <= --pop-min <= --pop-max.\n");
        return 1;
    }
    if (opts.tau < 0.0 || opts.tau > 1.0 || opts.pPull < 0.0 || opts.pPull > 1.0) {
        std::fprintf(stderr, "Error: --tau and --p-pull must be in [0, 1].\n");
        return 1;
    }

    std::string filename = std::filesystem::path(inputFile).filename().string();
    Timer timer;
    timer.start();

    try {
        VRPInstance inst(inputFile);
        GaMtResult result = gaMtSolve(inst, opts);
        timer.stop();
        const GaMtStats& s = result.stats;

        std::printf(
            "{\"Instance\": \"%s\", \"Model\": \"%s\", \"Time\": \"%.2f\", "
            "\"Result\": %.10g, \"Valid\": %s, \"BestSource\": \"%s\", "
            "\"PoolSize\": %d, \"AcceptedSeeds\": %ld, \"RejectedSeeds\": %ld, "
            "\"AcceptedChildren\": %ld, \"RejectedChildren\": %ld, "
            "\"AcceptedMigrants\": %ld, \"RejectedMigrants\": %ld, "
            "\"PullsAttempted\": %ld, \"PullsAccepted\": %ld, "
            "\"Solution\": \"%s\"}\n",
            filename.c_str(),
            modelName(opts.model).c_str(),
            timer.getTime(),
            result.objectiveValue,
            result.valid ? "true" : "false",
            result.bestSource.c_str(),
            s.poolSize,
            s.acceptedSeeds,
            s.rejectedSeeds,
            s.acceptedChildren,
            s.rejectedChildren,
            s.acceptedMigrants,
            s.rejectedMigrants,
            s.pullsAttempted,
            s.pullsAccepted,
            jsonEscape(result.solution).c_str());
    } catch (const std::exception& e) {
        timer.stop();
        std::fprintf(stderr, "Error: %s\n", e.what());
        return 1;
    }

    return 0;
}
