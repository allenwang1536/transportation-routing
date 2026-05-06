#pragma once
#include "../constructors/regret_bidding.hpp"
#include "../route_utils.hpp"
#include "population.hpp"
#include <algorithm>
#include <numeric>
#include <unordered_set>
#include <vector>

// Route-subset crossover for VRP:
//   1. Inherit k randomly chosen routes from parentA intact.
//   2. Collect unclaimed customers in the order they appear in parentB.
//   3. Insert each unclaimed customer into the cheapest feasible slot.
//
// The child fuses parentA's route clusters with parentB's customer affinity.
inline Routes crossover(
    const VRPInstance& inst,
    const Individual& parentA,
    const Individual& parentB,
    RNG& rng)
{
    int nv = inst.numVehicles;

    // Shuffle route indices; take the first k to inherit from parentA.
    // k ∈ [1, nv-1] so at least one route is inherited and at least one
    // empty slot remains to absorb unclaimed customers.
    std::vector<int> idx(nv);
    std::iota(idx.begin(), idx.end(), 0);
    std::shuffle(idx.begin(), idx.end(), rng.gen);
    int k = std::uniform_int_distribution<int>(1, nv - 1)(rng.gen);

    Routes child(nv);
    std::unordered_set<int> claimed;

    for (int i = 0; i < k; ++i) {
        int ri = idx[i];
        child[ri] = parentA.routes[ri];
        for (int c : child[ri]) claimed.insert(c);
    }

    // Collect unclaimed customers in parentB's sequential order.
    // This transfers parentB's route-affinity structure into the repair step.
    for (const auto& route : parentB.routes)
        for (int c : route)
            if (!claimed.count(c))
                insertBestFeasible(inst, child, c);

    return normalizeRoutes(child, nv);
}
