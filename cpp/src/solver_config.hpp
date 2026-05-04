#pragma once
#include <string>

struct SolverConfig {
    std::string constructor   = "farthest_nearest";
    std::string improver      = "none";
    bool        granular      = false;
    bool        tabu          = false;
    double      timeLimit     = 0.0;
    int         seed          = 0;
    int         neighborCount = 20;
    int         tabuTenure    = 25;
    double      destroyFraction = 0.15;
    int         maxEjectionDepth = 2;

    std::string modeName() const {
        std::string name = constructor;
        if (improver != "none") name += "+" + improver;
        if (granular) name += "+granular";
        if (tabu)     name += "+tabu";
        return name;
    }
};
