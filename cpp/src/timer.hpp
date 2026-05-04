#pragma once
#include <chrono>

class Timer {
    using Clock = std::chrono::steady_clock;
    using TimePoint = Clock::time_point;

    TimePoint startTime_;
    TimePoint endTime_;
    bool running_ = false;

public:
    void start() {
        startTime_ = Clock::now();
        running_ = true;
    }

    void stop() {
        if (running_) {
            endTime_ = Clock::now();
            running_ = false;
        }
    }

    double getTime() const {
        auto endpoint = running_ ? Clock::now() : endTime_;
        return std::chrono::duration<double>(endpoint - startTime_).count();
    }
};
