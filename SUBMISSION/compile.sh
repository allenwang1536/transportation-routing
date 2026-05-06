#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

g++ -std=c++17 -O2 -pthread -o solver src/main.cpp
echo "Build successful: solver"
