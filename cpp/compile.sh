#!/bin/bash

########################################
############# CSCI 2951-O ##############
########################################

# Compile the C++ VRP solver.
# Run from the cpp/ directory: bash compile.sh

set -e
g++ -std=c++17 -O2 -o solver   src/main.cpp
g++ -std=c++17 -O2 -o validate src/validate.cpp
echo "Build successful: solver  validate"
