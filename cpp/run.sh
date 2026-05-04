#!/bin/bash

########################################
############# CSCI 2951-O ##############
########################################
E_BADARGS=65
if [ $# -lt 1 ]; then
    echo "Usage: $(basename "$0") <input> [-- solver flags...]"
    exit $E_BADARGS
fi

# Resolve the directory of this script so it can be called from any location.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

"$SCRIPT_DIR/solver" "$@"
