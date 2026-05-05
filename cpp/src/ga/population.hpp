#pragma once
#include "../route_utils.hpp"
#include <algorithm>
#include <cassert>
#include <limits>
#include <numeric>
#include <optional>
#include <vector>

// ── Individual ────────────────────────────────────────────────────────────────
struct Individual {
    Routes routes;
    double objective;
    double biasedFitness = 0.0; // fitness_rank + diversity_rank; lower = better
};

// ── Population ────────────────────────────────────────────────────────────────
// Maintains a bounded pool of individuals and evolves their biased fitness
// (quality × diversity combined rank) after every insertion or eviction.
//
// Eviction policy: remove the individual with the worst biased fitness,
// never evicting the objective champion.  This preserves both good solutions
// AND diversity-providing outliers.
class Population {
public:
    const int minSize;
    const int maxSize;

    Population(int minSz, int maxSz, int numCustomers)
        : minSize(minSz), maxSize(maxSz), numCustomers_(numCustomers) {}

    // ── Insertion ─────────────────────────────────────────────────────────────
    void insert(Individual ind) {
        individuals_.push_back(std::move(ind));
        refresh();
        if ((int)individuals_.size() > maxSize) evictWorst();
    }

    // Diversity-gated insert for externally injected solutions.
    // Only accepts if the candidate's min broken-pairs distance to all
    // current members exceeds `threshold` (0 = always accept, 1 = reject all).
    bool tryInject(Individual ind, double threshold = 0.10) {
        if (!individuals_.empty() && minDistanceTo(ind.routes) < threshold)
            return false;
        insert(std::move(ind));
        return true;
    }

    // ── Selection ─────────────────────────────────────────────────────────────
    // Tournament selection: draw `tournamentSize` random candidates, return the
    // index of whichever has the lowest biasedFitness.
    int selectIdx(RNG& rng, int tournamentSize = 4) const {
        assert(!individuals_.empty());
        int best = randomIdx(rng);
        for (int i = 1; i < tournamentSize; ++i) {
            int cand = randomIdx(rng);
            if (individuals_[cand].biasedFitness < individuals_[best].biasedFitness)
                best = cand;
        }
        return best;
    }

    // ── Accessors ─────────────────────────────────────────────────────────────
    int size() const { return (int)individuals_.size(); }
    bool empty() const { return individuals_.empty(); }

    const Individual& operator[](int i) const { return individuals_[i]; }

    const std::vector<Individual>& individuals() const { return individuals_; }

    const Individual& best() const {
        return *std::min_element(individuals_.begin(), individuals_.end(),
            [](const Individual& a, const Individual& b) {
                return a.objective < b.objective;
            });
    }

    double minDistanceTo(const Routes& routes) const {
        double minD = std::numeric_limits<double>::infinity();
        for (const auto& ind : individuals_)
            minD = std::min(minD, distance(routes, ind.routes, numCustomers_));
        return minD;
    }

    std::optional<Individual> qualityDiversitySample(RNG& rng, int tournamentSize = 6) const {
        if (individuals_.empty()) return std::nullopt;
        int idx = selectIdx(rng, std::min(tournamentSize, (int)individuals_.size()));
        return individuals_[idx];
    }

    // ── Diversity metric: normalized broken-pairs distance ────────────────────
    // For each customer c, define successor(c) = next customer in its route
    // (0 = depot return).  Distance = fraction of customers whose successor
    // differs between the two solutions.  Range: [0, 1].
    static double distance(const Routes& a, const Routes& b, int numCustomers) {
        std::vector<int> succA(numCustomers, 0), succB(numCustomers, 0);
        for (const auto& route : a)
            for (int i = 0; i < (int)route.size(); ++i)
                succA[route[i]] = (i + 1 < (int)route.size()) ? route[i + 1] : 0;
        for (const auto& route : b)
            for (int i = 0; i < (int)route.size(); ++i)
                succB[route[i]] = (i + 1 < (int)route.size()) ? route[i + 1] : 0;
        int broken = 0;
        for (int c = 1; c < numCustomers; ++c)
            if (succA[c] != succB[c]) ++broken;
        return (numCustomers > 1) ? (double)broken / (numCustomers - 1) : 0.0;
    }

private:
    std::vector<Individual> individuals_;
    int numCustomers_;

    int randomIdx(RNG& rng) const {
        return std::uniform_int_distribution<int>(0, (int)individuals_.size() - 1)(rng.gen);
    }

    // Recompute biasedFitness = fitnessRank + diversityRank for all individuals.
    // fitnessRank: 1 = lowest objective (best).
    // diversityRank: 1 = highest nearest-neighbor distance (most diverse).
    void refresh() {
        int n = (int)individuals_.size();
        if (n == 0) return;

        // All-pairs distances (O(n² × numCustomers), fast for n ≤ 40)
        std::vector<std::vector<double>> dist(n, std::vector<double>(n, 0.0));
        for (int i = 0; i < n; ++i)
            for (int j = i + 1; j < n; ++j) {
                double d = distance(individuals_[i].routes, individuals_[j].routes, numCustomers_);
                dist[i][j] = dist[j][i] = d;
            }

        // Fitness ranks (ascending objective → ascending rank)
        std::vector<int> order(n);
        std::iota(order.begin(), order.end(), 0);
        std::sort(order.begin(), order.end(), [&](int a, int b) {
            return individuals_[a].objective < individuals_[b].objective;
        });
        std::vector<int> fitRank(n);
        for (int r = 0; r < n; ++r) fitRank[order[r]] = r + 1;

        // Diversity contribution: nearest-neighbor distance
        std::vector<double> divContrib(n, std::numeric_limits<double>::infinity());
        for (int i = 0; i < n; ++i)
            for (int j = 0; j < n; ++j)
                if (i != j) divContrib[i] = std::min(divContrib[i], dist[i][j]);

        // Diversity ranks (descending diversity → ascending rank)
        std::iota(order.begin(), order.end(), 0);
        std::sort(order.begin(), order.end(), [&](int a, int b) {
            return divContrib[a] > divContrib[b];
        });
        std::vector<int> divRank(n);
        for (int r = 0; r < n; ++r) divRank[order[r]] = r + 1;

        for (int i = 0; i < n; ++i)
            individuals_[i].biasedFitness = fitRank[i] + divRank[i];
    }

    // Evict the individual with the highest biasedFitness, never the best-objective one.
    void evictWorst() {
        int n = (int)individuals_.size();
        if (n <= 1) return;

        int champIdx = 0;
        for (int i = 1; i < n; ++i)
            if (individuals_[i].objective < individuals_[champIdx].objective)
                champIdx = i;

        int worstIdx = -1;
        for (int i = 0; i < n; ++i) {
            if (i == champIdx) continue;
            if (worstIdx < 0 ||
                individuals_[i].biasedFitness > individuals_[worstIdx].biasedFitness)
                worstIdx = i;
        }
        if (worstIdx >= 0)
            individuals_.erase(individuals_.begin() + worstIdx);
    }
};
