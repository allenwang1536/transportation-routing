#pragma once
#include "../route_utils.hpp"
#include <algorithm>
#include <set>
#include <unordered_set>
#include <vector>

// Restricts neighbourhood search to customers within a fixed-radius
// k-nearest list, reducing the number of moves evaluated per iteration.
class GranularNeighborhood {
    const VRPInstance& inst_;

public:
    int neighborCount;
    // neighbors[c] = set of the `neighborCount` closest other customers to c
    // (indexed 1..numCustomers-1; index 0 / depot unused)
    std::vector<std::unordered_set<int>> neighbors;

    GranularNeighborhood(const VRPInstance& inst, int neighborCount_ = 20)
        : inst_(inst), neighborCount(std::max(1, neighborCount_))
    {
        buildNeighbors();
    }

    bool routeIsRelevant(int customer, const std::vector<int>& route, bool allowEmpty = true) const {
        if (route.empty()) return allowEmpty;
        const auto& nearby = neighbors[customer];
        for (int other : route)
            if (nearby.count(other)) return true;
        return false;
    }

    std::vector<int> routesForCustomer(
        const Routes& routes, int customer, bool includeEmpty = true) const
    {
        std::vector<int> candidates;
        for (int v = 0; v < static_cast<int>(routes.size()); ++v)
            if (routeIsRelevant(customer, routes[v], includeEmpty))
                candidates.push_back(v);
        if (candidates.empty()) {
            // Fall back to all routes
            candidates.resize(routes.size());
            std::iota(candidates.begin(), candidates.end(), 0);
        }
        return candidates;
    }

    std::vector<int> customersNearCustomer(int customer, const std::vector<int>& candidates) const {
        const auto& nearby = neighbors[customer];
        std::vector<int> filtered;
        for (int other : candidates)
            if (nearby.count(other)) filtered.push_back(other);
        return filtered.empty() ? candidates : filtered;
    }

    std::set<std::pair<int,int>> neighboringRoutePairs(const Routes& routes) const {
        auto routeOf = customerToRoute(routes);
        std::set<std::pair<int,int>> pairs;
        for (const auto& [customer, routeA] : routeOf) {
            for (int neighbor : neighbors[customer]) {
                auto it = routeOf.find(neighbor);
                if (it == routeOf.end() || it->second == routeA) continue;
                int routeB = it->second;
                pairs.insert({std::min(routeA, routeB), std::max(routeA, routeB)});
            }
        }
        return pairs;
    }

private:
    void buildNeighbors() {
        int N = inst_.numCustomers;
        neighbors.resize(N);
        std::vector<int> customers;
        for (int i = 1; i < N; ++i) customers.push_back(i);

        for (int c : customers) {
            std::vector<int> others;
            for (int o : customers)
                if (o != c) others.push_back(o);

            std::sort(others.begin(), others.end(), [&](int a, int b) {
                return inst_.distance(c, a) < inst_.distance(c, b);
            });

            int take = std::min(neighborCount, static_cast<int>(others.size()));
            neighbors[c] = std::unordered_set<int>(others.begin(), others.begin() + take);
        }
    }
};
