#include "ga_multithreaded_solver.hpp"
#include "timer.hpp"
#include "vrpinstance.hpp"
#include <cstdio>
#include <cstring>
#include <stdexcept>
#include <string>

static void usage(const char* prog) {
    std::fprintf(stderr,
        "Usage: %s <input_file> [--time-limit SECS] [--seed N]\n",
        prog);
}

static std::string basenameOf(const std::string& path) {
    std::size_t pos = path.find_last_of("/\\");
    return (pos == std::string::npos) ? path : path.substr(pos + 1);
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
    opts.model = GaMtModel::Bidirectional;
    opts.timeLimit = 295.0;
    opts.seed = 42;

    for (int i = 1; i < argc; ++i) {
        if (std::strcmp(argv[i], "--time-limit") == 0 && i + 1 < argc) {
            opts.timeLimit = std::stod(argv[++i]);
        } else if (std::strcmp(argv[i], "--seed") == 0 && i + 1 < argc) {
            opts.seed = std::stoi(argv[++i]);
        } else if (argv[i][0] != '-') {
            inputFile = argv[i];
        } else {
            std::fprintf(stderr, "Unknown flag: %s\n", argv[i]);
            usage(argv[0]);
            return 1;
        }
    }

    if (inputFile.empty() || opts.timeLimit <= 0.0) {
        std::fprintf(stderr, "Error: input file and positive time limit are required.\n");
        usage(argv[0]);
        return 1;
    }

    std::string filename = basenameOf(inputFile);
    Timer timer;
    timer.start();

    try {
        VRPInstance inst(inputFile);
        GaMtResult result = gaMtSolve(inst, opts);
        timer.stop();

        std::printf(
            "{\"Instance\": \"%s\", \"Time\": \"%.2f\", \"Result\": %.10g, \"Solution\": \"%s\"}\n",
            filename.c_str(),
            timer.getTime(),
            result.objectiveValue,
            jsonEscape(result.solution).c_str());
    } catch (const std::exception& e) {
        timer.stop();
        std::fprintf(stderr, "Error: %s\n", e.what());
        return 1;
    }

    return 0;
}
