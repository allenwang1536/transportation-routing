#!/bin/bash

########################################
############# CSCI 2951-O ##############
########################################

# Compile the C++ VRP solver.
# Run from the cpp/ directory: bash compile.sh

set -e
g++ -std=c++17 -O2 -o solver          src/main.cpp
g++ -std=c++17 -O2 -o validate        src/validate.cpp
g++ -std=c++17 -O2 -o parallel_solver src/parallel_main.cpp
g++ -std=c++17 -O2 -o ga_solver       src/ga_main.cpp
echo "Build successful: solver  validate  parallel_solver  ga_solver"
