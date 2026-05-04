#pragma once
#include <cmath>
#include <fstream>
#include <stdexcept>
#include <string>
#include <vector>

struct VRPInstance {
    int numCustomers;
    int numVehicles;
    int vehicleCapacity;
    std::vector<int> demandOfCustomer;
    std::vector<double> xCoordOfCustomer;
    std::vector<double> yCoordOfCustomer;

    explicit VRPInstance(const std::string& filename) {
        loadFromFile(filename);
        buildDistanceCache();
    }

    double distance(int i, int j) const {
        return distCache_[i * numCustomers + j];
    }

private:
    std::vector<double> distCache_;

    void loadFromFile(const std::string& filename) {
        std::ifstream f(filename);
        if (!f.is_open())
            throw std::runtime_error("Cannot open: " + filename);
        if (!(f >> numCustomers >> numVehicles >> vehicleCapacity))
            throw std::runtime_error("Bad header in: " + filename);
        demandOfCustomer.resize(numCustomers);
        xCoordOfCustomer.resize(numCustomers);
        yCoordOfCustomer.resize(numCustomers);
        for (int i = 0; i < numCustomers; ++i) {
            if (!(f >> demandOfCustomer[i] >> xCoordOfCustomer[i] >> yCoordOfCustomer[i]))
                throw std::runtime_error("Truncated data in: " + filename);
        }
    }

    void buildDistanceCache() {
        int N = numCustomers;
        distCache_.assign(N * N, 0.0);
        for (int i = 0; i < N; ++i) {
            for (int j = i + 1; j < N; ++j) {
                double dx = xCoordOfCustomer[i] - xCoordOfCustomer[j];
                double dy = yCoordOfCustomer[i] - yCoordOfCustomer[j];
                double d = std::sqrt(dx * dx + dy * dy);
                distCache_[i * N + j] = d;
                distCache_[j * N + i] = d;
            }
        }
    }
};
