#pragma once
#include <map>
#include <tuple>
#include <vector>

// Remembers recent customer-reassignment moves and forbids their reversal
// for `tenure` iterations, implementing a basic tabu search memory.
class TabuMemory {
    int tenure_;
    int iteration_;
    std::map<std::tuple<int,int,int>, int> tabuUntil_; // key: (customer, from_v, to_v) → expiry iter

public:
    explicit TabuMemory(int tenure = 20)
        : tenure_(std::max(1, tenure)), iteration_(0) {}

    void nextIteration() { ++iteration_; }

    void forbidReverseMove(int customer, int fromVehicle, int toVehicle) {
        auto reverseKey = std::make_tuple(customer, toVehicle, fromVehicle);
        tabuUntil_[reverseKey] = iteration_ + tenure_;
    }

    bool isTabu(int customer, int fromVehicle, int toVehicle, bool aspiration = false) const {
        if (aspiration) return false;
        auto key = std::make_tuple(customer, fromVehicle, toVehicle);
        auto it = tabuUntil_.find(key);
        if (it == tabuUntil_.end()) return false;
        return it->second > iteration_;
    }

    void prune() {
        for (auto it = tabuUntil_.begin(); it != tabuUntil_.end(); ) {
            if (it->second <= iteration_)
                it = tabuUntil_.erase(it);
            else
                ++it;
        }
    }
};
